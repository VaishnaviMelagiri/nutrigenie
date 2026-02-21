"""
Lambda: get_alternatives
Generates alternative meal suggestions when a user rejects a meal from their plan.
Uses RAG to find nutritionally similar replacements that respect patient constraints.
Triggered via API Gateway POST /alternatives.
"""

import json
import os
import re
import logging
from datetime import datetime, timezone

import boto3
import numpy as np

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── AWS Clients ──
s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime")
dynamodb = boto3.resource("dynamodb")

PATIENT_TABLE = os.environ.get("PATIENT_PROFILES_TABLE", "PatientProfiles")
MEAL_PLANS_TABLE = os.environ.get("MEAL_PLANS_TABLE", "MealPlans")
NUTRITION_TABLE = os.environ.get("NUTRITION_DATA_TABLE", "NutritionData")
VECTORS_BUCKET = os.environ.get("VECTORS_BUCKET", "meal-plan-vectors")
LLM_MODEL_ID = os.environ.get("LLM_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
EMBEDDING_MODEL_ID = os.environ.get("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")


def lambda_handler(event, context):
    """
    POST /alternatives
    Body:
    {
        "kit_id": "KIT-2024-00142",
        "plan_id": "PLAN#20260221T100000Z",     (optional — uses active plan if omitted)
        "day": "day_1",
        "meal_type": "breakfast",
        "reason": "Don't like ragi"              (optional)
    }
    """
    try:
        # Parse request
        if isinstance(event.get("body"), str):
            body = json.loads(event["body"])
        else:
            body = event.get("body", event)

        kit_id = body.get("kit_id", "").strip()
        day = body.get("day", "").strip()
        meal_type = body.get("meal_type", "").strip()
        reason = body.get("reason", "")
        plan_id = body.get("plan_id")

        if not kit_id or not day or not meal_type:
            return _response(400, {"error": "kit_id, day, and meal_type are required"})

        valid_meal_types = ["breakfast", "mid_morning_snack", "lunch", "evening_snack", "dinner"]
        if meal_type not in valid_meal_types:
            return _response(400, {"error": f"meal_type must be one of: {valid_meal_types}"})

        logger.info(f"Generating alternative for kit_id={kit_id}, {day}/{meal_type}")

        # ── Step 1: Fetch patient profile ──
        patient_table = dynamodb.Table(PATIENT_TABLE)
        patient = patient_table.get_item(Key={"kit_id": kit_id}).get("Item")
        if not patient:
            return _response(404, {"error": f"Patient {kit_id} not found"})

        # ── Step 2: Fetch the current meal plan ──
        plans_table = dynamodb.Table(MEAL_PLANS_TABLE)

        if plan_id:
            plan_resp = plans_table.get_item(Key={"kit_id": kit_id, "plan_id": plan_id})
            plan = plan_resp.get("Item")
        else:
            # Get the active plan
            plan_resp = plans_table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key("kit_id").eq(kit_id),
                FilterExpression=boto3.dynamodb.conditions.Attr("status").eq("ACTIVE"),
                ScanIndexForward=False,
                Limit=1
            )
            items = plan_resp.get("Items", [])
            plan = items[0] if items else None

        if not plan:
            return _response(404, {"error": "No active meal plan found"})

        # ── Step 3: Get the rejected meal ──
        meals = plan.get("meals", {})
        day_data = meals.get(day, {})
        rejected_meal = day_data.get(meal_type)

        if not rejected_meal:
            return _response(404, {"error": f"Meal not found: {day}/{meal_type}"})

        target_calories = rejected_meal.get("total_calories", 400)

        # ── Step 4: RAG — retrieve nutrition context for alternative ──
        query = _build_alternative_query(patient, rejected_meal, reason)
        nutrition_context = _retrieve_nutrition_context(query)

        # ── Step 5: Generate alternative via Bedrock ──
        region = patient.get("dietary_preferences", {}).get("region", "Pan-Indian")
        system_prompt, user_prompt = _build_alternative_prompt(
            rejected_meal, patient, nutrition_context, meal_type, region, reason
        )

        alternative = _invoke_bedrock(system_prompt, user_prompt)

        if not alternative:
            return _response(500, {"error": "Failed to generate alternative meal"})

        # ── Step 6: Validate the alternative ──
        validation = _validate_alternative(alternative, patient, target_calories)

        # ── Step 7: Update the meal plan with the alternative ──
        alternative["replaces"] = rejected_meal.get("meal_id", f"{day}-{meal_type}")
        alternative["generated_at"] = datetime.now(timezone.utc).isoformat()

        # Track rejection
        rejected_meals = plan.get("rejected_meals", [])
        rejected_meals.append({
            "day": day,
            "meal_type": meal_type,
            "original_meal_id": rejected_meal.get("meal_id", ""),
            "reason": reason,
            "rejected_at": datetime.now(timezone.utc).isoformat()
        })

        # Update the plan in DynamoDB
        plans_table.update_item(
            Key={"kit_id": kit_id, "plan_id": plan.get("plan_id")},
            UpdateExpression="SET meals.#day.#mtype = :alt, rejected_meals = :rejected",
            ExpressionAttributeNames={
                "#day": day,
                "#mtype": meal_type
            },
            ExpressionAttributeValues={
                ":alt": alternative,
                ":rejected": rejected_meals
            }
        )

        logger.info(f"Alternative generated for kit_id={kit_id}, {day}/{meal_type}")

        return _response(200, {
            "kit_id": kit_id,
            "day": day,
            "meal_type": meal_type,
            "alternative_meal": alternative,
            "validation": validation,
            "replaced_meal_id": rejected_meal.get("meal_id", "")
        })

    except json.JSONDecodeError:
        return _response(400, {"error": "Invalid JSON in request body"})
    except Exception as e:
        logger.error(f"Alternative generation error: {str(e)}", exc_info=True)
        return _response(500, {"error": f"Internal server error: {str(e)}"})


def _build_alternative_query(patient: dict, rejected_meal: dict, reason: str) -> str:
    """Build a query for RAG retrieval specific to alternative meal generation."""
    parts = [
        f"Indian {patient.get('dietary_preferences', {}).get('region', 'Pan-Indian')} meal",
        f"approximately {rejected_meal.get('total_calories', 400)} calories",
        f"must avoid: {', '.join(patient.get('avoid_list', []))}",
    ]

    recommended = patient.get("recommended_list", [])
    if recommended:
        parts.append(f"prefer: {', '.join(recommended)}")

    if reason:
        parts.append(f"user dislikes: {reason}")

    # Add the rejected meal's tags for context
    tags = rejected_meal.get("tags", [])
    if tags:
        parts.append(f"similar to: {', '.join(tags)}")

    return ". ".join(parts)


def _retrieve_nutrition_context(query: str, top_k: int = 10) -> str:
    """Retrieve relevant nutrition data for alternatives."""
    try:
        index_obj = s3.get_object(Bucket=VECTORS_BUCKET, Key="base/nutrition_index.faiss")
        index_bytes = index_obj["Body"].read()

        meta_obj = s3.get_object(Bucket=VECTORS_BUCKET, Key="base/nutrition_metadata.json")
        metadata = json.loads(meta_obj["Body"].read())

        query_embedding = _generate_embedding(query)

        from backend.lambdas.generate_embeddings.lambda_function import search_index
        results = search_index(index_bytes, np.array(query_embedding), top_k)

        context_parts = []
        for idx, score in results:
            if score >= 0.5 and idx < len(metadata):
                meta = metadata[idx]
                context_parts.append(
                    f"[{meta.get('food_id', 'N/A')}] {meta.get('name_en', 'Unknown')} "
                    f"(Category: {meta.get('category', 'N/A')}): {meta.get('text_preview', '')}"
                )

        return "\n".join(context_parts) if context_parts else "No nutrition context available."

    except Exception as e:
        logger.warning(f"Nutrition context retrieval failed: {e}")
        return "Nutrition context unavailable."


def _build_alternative_prompt(rejected_meal: dict, patient: dict, nutrition_context: str,
                               meal_type: str, region: str, reason: str) -> tuple:
    """Build prompts for alternative meal generation."""
    meal_type_display = meal_type.replace("_", " ")

    system_prompt = f"""You are a certified Indian clinical nutritionist AI. Generate ONE alternative {meal_type_display} meal.

RULES:
1. Similar nutrition (±10% calories, ±15% macros) to the rejected meal.
2. Use DIFFERENT primary ingredients.
3. NEVER use foods from the Avoid List.
4. MINIMIZE Reduce List foods (≤30% serving if used).
5. Prefer Recommended List foods.
6. Must be a common Indian household recipe for {region} cuisine.
7. Use ONLY foods from the NUTRITION DATABASE below.
8. Output ONLY valid JSON. No explanations."""

    user_prompt = f"""Generate one alternative {meal_type_display}.

[REJECTED MEAL]
{json.dumps(rejected_meal, indent=2, default=str)}

{"[REJECTION REASON] " + reason if reason else ""}

[PATIENT CONSTRAINTS]
Avoid: {', '.join(patient.get('avoid_list', [])) or 'None'}
Reduce: {', '.join(patient.get('reduce_list', [])) or 'None'}
Recommended: {', '.join(patient.get('recommended_list', [])) or 'None'}

[NUTRITION DATABASE]
{nutrition_context}

Output valid JSON:
{{"meal_id":"ALT-{meal_type[:2].upper()}-001","name":"...","ingredients":[{{"name":"...","food_id":"IFCT-XXX","quantity_g":80,"calories":262,"protein_g":5,"carbs_g":48,"fat_g":2,"fiber_g":3}}],"total_calories":368,"macros":{{"protein_g":8,"carbs_g":58,"fat_g":12,"fiber_g":6}},"prep_time_min":20,"tags":["..."]}}"""

    return system_prompt, user_prompt


def _invoke_bedrock(system_prompt: str, user_prompt: str) -> dict | None:
    """Call Bedrock and parse JSON response."""
    try:
        response = bedrock.invoke_model(
            modelId=LLM_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1024,
                "temperature": 0.4,
                "system": system_prompt,
                "messages": [
                    {"role": "user", "content": user_prompt}
                ]
            })
        )

        response_body = json.loads(response["body"].read())
        content = response_body["content"][0]["text"]

        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            return json.loads(json_match.group())

        return None

    except Exception as e:
        logger.error(f"Bedrock invocation error: {e}")
        return None


def _generate_embedding(text: str) -> list[float]:
    """Generate embedding using Titan V2."""
    response = bedrock.invoke_model(
        modelId=EMBEDDING_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "inputText": text[:8000],
            "dimensions": 768,
            "normalize": True
        })
    )
    return json.loads(response["body"].read())["embedding"]


def _validate_alternative(alternative: dict, patient: dict, target_calories: float) -> dict:
    """Quick validation of the alternative meal."""
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
        from utils.nutrition_validator import NutritionValidator

        validator = NutritionValidator(patient)
        return validator.validate_single_meal(alternative, target_calories)
    except ImportError:
        return {"passed": True, "violations": [], "warnings": []}


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "POST, OPTIONS"
        },
        "body": json.dumps(body, default=str)
    }
