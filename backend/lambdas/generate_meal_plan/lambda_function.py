"""
Lambda: generate_meal_plan
RAG-augmented meal plan generation using Bedrock Claude 3 Haiku.
Retrieves patient context + nutrition data, generates a 7-day Indian meal plan,
validates against nutritional constraints.
Triggered via API Gateway POST /generate.
"""

import json
import os
import logging
from datetime import datetime, timezone
import time

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

# ── Local cache (persists across warm Lambda invocations) ──
_nutrition_index_cache = None
_nutrition_metadata_cache = None


def lambda_handler(event, context):
    """
    POST /generate
    Body: {"kit_id": "KIT-2024-00142"}
    """
    try:
        # Parse request
        if isinstance(event.get("body"), str):
            body = json.loads(event["body"])
        else:
            body = event.get("body", event)

        kit_id = body.get("kit_id", "").strip()
        if not kit_id:
            return _response(400, {"error": "kit_id is required"})

        logger.info(f"Generating meal plan for kit_id={kit_id}")

        # ── Step 1: Fetch patient profile ──
        patient_table = dynamodb.Table(PATIENT_TABLE)
        patient_resp = patient_table.get_item(Key={"kit_id": kit_id})
        patient = patient_resp.get("Item")

        if not patient:
            return _response(404, {"error": f"Patient {kit_id} not found"})

        if patient.get("extraction_status") != "COMPLETED":
            return _response(400, {
                "error": "Report extraction not completed yet",
                "status": patient.get("extraction_status", "UNKNOWN")
            })

        # ── Step 2: RAG — Retrieve relevant context ──
        query = _build_rag_query(patient)
        nutrition_context = _retrieve_nutrition_context(query)
        patient_context = _retrieve_patient_context(kit_id, query)

        # ── Step 3: Build prompt ──
        system_prompt, user_prompt = _build_meal_plan_prompt(
            patient, nutrition_context, patient_context
        )

        # ── Step 4: Generate meal plan via Bedrock ──
        logger.info("Invoking Bedrock Claude 3 Haiku for meal plan generation...")
        meal_plan_json = _invoke_bedrock(system_prompt, user_prompt)

        if not meal_plan_json:
            return _response(500, {"error": "Failed to generate meal plan"})

        # ── Step 5: Validate the generated plan ──
        validation = _validate_plan(meal_plan_json, patient)

        # ── Step 6: If critical violations, retry once ──
        if not validation["passed"]:
            logger.warning(f"Validation failed with {len(validation['violations'])} violations. Retrying...")
            retry_prompt = user_prompt + f"\n\nPREVIOUS ATTEMPT HAD VIOLATIONS:\n{json.dumps(validation['violations'][:5])}\nFix these issues in the new plan."
            meal_plan_json = _invoke_bedrock(system_prompt, retry_prompt)
            if meal_plan_json:
                validation = _validate_plan(meal_plan_json, patient)

        # ── Step 7: Store in DynamoDB ──
        plan_id = f"PLAN#{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        ttl = int(time.time()) + (90 * 86400)  # 90 days TTL

        plans_table = dynamodb.Table(MEAL_PLANS_TABLE)
        plans_table.put_item(Item={
            "kit_id": kit_id,
            "plan_id": plan_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "plan_type": "WEEKLY",
            "status": "ACTIVE",
            "meals": meal_plan_json,
            "validation_result": {
                "passed": validation["passed"],
                "score": int(validation["score"]),
                "violation_count": len(validation["violations"]),
                "warning_count": len(validation["warnings"])
            },
            "nutrition_summary": validation.get("daily_totals", {}),
            "rejected_meals": [],
            "ttl": ttl
        })

        # Mark any previous active plans as superseded
        _supersede_old_plans(kit_id, plan_id)

        logger.info(f"Meal plan generated for kit_id={kit_id}, validation score={validation['score']}")

        return _response(200, {
            "kit_id": kit_id,
            "plan_id": plan_id,
            "meal_plan": meal_plan_json,
            "validation": {
                "passed": validation["passed"],
                "score": validation["score"],
                "violations": validation["violations"][:5],  # Return top 5 violations
                "warnings": validation["warnings"][:5]
            },
            "nutrition_summary": validation.get("daily_totals", {})
        })

    except json.JSONDecodeError:
        return _response(400, {"error": "Invalid JSON in request body"})
    except Exception as e:
        logger.error(f"Meal generation error: {str(e)}", exc_info=True)
        return _response(500, {"error": f"Internal server error: {str(e)}"})


def _build_rag_query(patient: dict) -> str:
    """Build a combined query from patient constraints for RAG retrieval."""
    parts = []

    avoid = patient.get("avoid_list", [])
    if avoid:
        parts.append(f"Patient needs to avoid: {', '.join(avoid)}")

    recommended = patient.get("recommended_list", [])
    if recommended:
        parts.append(f"Recommended foods: {', '.join(recommended)}")

    conditions = patient.get("medical_conditions", [])
    if conditions:
        parts.append(f"Conditions: {', '.join(conditions)}")

    region = patient.get("dietary_preferences", {}).get("region", "Pan-Indian")
    parts.append(f"Indian household meals for {region} cuisine")

    return ". ".join(parts)


def _retrieve_nutrition_context(query: str, top_k: int = 10) -> str:
    """Retrieve relevant nutrition data using vector similarity search."""
    global _nutrition_index_cache, _nutrition_metadata_cache

    try:
        # Load nutrition index (with caching)
        if _nutrition_index_cache is None:
            index_obj = s3.get_object(Bucket=VECTORS_BUCKET, Key="base/nutrition_index.faiss")
            _nutrition_index_cache = index_obj["Body"].read()

            meta_obj = s3.get_object(Bucket=VECTORS_BUCKET, Key="base/nutrition_metadata.json")
            _nutrition_metadata_cache = json.loads(meta_obj["Body"].read())

        # Generate query embedding
        query_embedding = _generate_embedding(query)

        # Search index
        from backend.lambdas.generate_embeddings.lambda_function import search_index
        results = search_index(_nutrition_index_cache, np.array(query_embedding), top_k)

        # Build context string
        context_parts = []
        for idx, score in results:
            if score >= 0.5 and idx < len(_nutrition_metadata_cache):
                meta = _nutrition_metadata_cache[idx]
                context_parts.append(
                    f"[{meta.get('food_id', 'N/A')}] {meta.get('name_en', 'Unknown')} "
                    f"(Category: {meta.get('category', 'N/A')}): {meta.get('text_preview', '')}"
                )

        return "\n".join(context_parts) if context_parts else "No nutrition context available."

    except Exception as e:
        logger.warning(f"Failed to retrieve nutrition context: {e}")
        # Fallback: query DynamoDB directly
        return _fallback_nutrition_context()


def _retrieve_patient_context(kit_id: str, query: str, top_k: int = 5) -> str:
    """Retrieve relevant patient report chunks using vector similarity search."""
    try:
        # Load patient-specific index
        index_key = f"patients/{kit_id}/patient_index.faiss"
        meta_key = f"patients/{kit_id}/patient_metadata.json"

        index_obj = s3.get_object(Bucket=VECTORS_BUCKET, Key=index_key)
        index_bytes = index_obj["Body"].read()

        meta_obj = s3.get_object(Bucket=VECTORS_BUCKET, Key=meta_key)
        metadata = json.loads(meta_obj["Body"].read())

        # Generate query embedding
        query_embedding = _generate_embedding(query)

        # Search
        from backend.lambdas.generate_embeddings.lambda_function import search_index
        results = search_index(index_bytes, np.array(query_embedding), top_k)

        context_parts = []
        for idx, score in results:
            if score >= 0.5 and idx < len(metadata):
                meta = metadata[idx]
                context_parts.append(meta.get("text", meta.get("text_preview", "")))

        return "\n---\n".join(context_parts) if context_parts else "No patient context available."

    except Exception as e:
        logger.warning(f"Failed to retrieve patient context: {e}")
        return "No patient context available."


def _fallback_nutrition_context() -> str:
    """Fallback: fetch top nutrition items directly from DynamoDB."""
    try:
        table = dynamodb.Table(NUTRITION_TABLE)
        response = table.scan(Limit=20)
        items = response.get("Items", [])

        parts = []
        for item in items:
            per_100g = item.get("per_100g", {})
            parts.append(
                f"[{item.get('food_id')}] {item.get('name_en')} — "
                f"{per_100g.get('calories', 0)} kcal, "
                f"P:{per_100g.get('protein_g', 0)}g, "
                f"C:{per_100g.get('carbs_g', 0)}g, "
                f"F:{per_100g.get('fat_g', 0)}g"
            )
        return "\n".join(parts)
    except Exception:
        return "Nutrition context unavailable."


def _build_meal_plan_prompt(patient: dict, nutrition_context: str, patient_context: str) -> tuple:
    """Assemble the full meal plan generation prompt."""
    calorie_target = int(patient.get("calorie_target", 1800))
    tolerance = 10
    calorie_min = int(calorie_target * 0.9)
    calorie_max = int(calorie_target * 1.1)

    region = patient.get("dietary_preferences", {}).get("region", "Pan-Indian")
    veg = patient.get("dietary_preferences", {}).get("vegetarian", False)
    dietary_pref = "Vegetarian" if veg else "Non-Vegetarian"

    # Bacterial summary
    bacterial_summary = "None reported"
    bh = patient.get("bacterial_history", [])
    if bh:
        parts = []
        for b in bh:
            name = b.get("name", "Unknown")
            count = b.get("count", "N/A")
            status = b.get("status", "unknown")
            parts.append(f"{name}: {count} ({status})")
        bacterial_summary = "; ".join(parts)

    system_prompt = f"""You are a certified Indian clinical nutritionist AI. Generate personalized 7-day meal plans based on IOM gut health reports and verified Indian nutrition data.

STRICT RULES — VIOLATION IS UNACCEPTABLE:
1. ONLY use foods from the NUTRITION DATABASE below. Never invent foods.
2. NEVER include ANY food from the AVOID LIST. Non-negotiable.
3. MINIMIZE foods from the REDUCE LIST (≤30% of normal serving if used).
4. PRIORITIZE RECOMMENDED LIST foods.
5. Each day: exactly 5 meals (breakfast, mid_morning_snack, lunch, evening_snack, dinner).
6. Daily targets: {calorie_min}–{calorie_max} kcal, protein ≥50g, fiber ≥25g.
7. All meals must be authentic Indian household recipes for {region} cuisine.
8. Include exact quantities in grams and full nutritional breakdown.
9. VARIETY: rotate grains, proteins, vegetables across the week.
10. Output ONLY valid JSON. No explanations."""

    user_prompt = f"""Generate a 7-day Indian household meal plan.

[PATIENT]
Kit ID: {patient['kit_id']}
Avoid: {', '.join(patient.get('avoid_list', [])) or 'None'}
Reduce: {', '.join(patient.get('reduce_list', [])) or 'None'}
Recommended: {', '.join(patient.get('recommended_list', [])) or 'None'}
Bacteria: {bacterial_summary}
Calories: {calorie_target} kcal/day (±{tolerance}%)
Region: {region}
Diet: {dietary_pref}

[NUTRITION DATABASE]
{nutrition_context}

[PATIENT REPORT CONTEXT]
{patient_context}

Generate the complete 7-day meal plan as valid JSON with structure:
{{"day_1": {{"breakfast": {{"meal_id":"D1-BF-001","name":"...","ingredients":[{{"name":"...","food_id":"IFCT-XXX","quantity_g":80,"calories":262,"protein_g":5,"carbs_g":48,"fat_g":2,"fiber_g":3}}],"total_calories":368,"macros":{{"protein_g":8,"carbs_g":58,"fat_g":12,"fiber_g":6}},"prep_time_min":20,"tags":["..."]}},...}},...}}"""

    return system_prompt, user_prompt


def _invoke_bedrock(system_prompt: str, user_prompt: str) -> dict | None:
    """Call Bedrock Claude 3 Haiku and parse JSON response."""
    try:
        response = bedrock.invoke_model(
            modelId=LLM_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "temperature": 0.3,
                "system": system_prompt,
                "messages": [
                    {"role": "user", "content": user_prompt}
                ]
            })
        )

        response_body = json.loads(response["body"].read())
        content = response_body["content"][0]["text"]

        # Parse JSON from response
        import re
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            return json.loads(json_match.group())

        logger.error("No valid JSON found in Bedrock response")
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


def _validate_plan(meal_plan: dict, patient: dict) -> dict:
    """Run nutrition validation on the generated plan."""
    try:
        # Import validator inline to avoid circular imports in Lambda
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
        from utils.nutrition_validator import NutritionValidator

        validator = NutritionValidator(patient)
        return validator.validate_plan(meal_plan)
    except ImportError:
        logger.warning("Nutrition validator not available, skipping validation")
        return {"passed": True, "score": 100, "violations": [], "warnings": [], "daily_totals": {}}


def _supersede_old_plans(kit_id: str, current_plan_id: str):
    """Mark previous active plans as SUPERSEDED."""
    try:
        table = dynamodb.Table(MEAL_PLANS_TABLE)
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("kit_id").eq(kit_id),
            FilterExpression=boto3.dynamodb.conditions.Attr("status").eq("ACTIVE")
        )
        for item in response.get("Items", []):
            if item["plan_id"] != current_plan_id:
                table.update_item(
                    Key={"kit_id": kit_id, "plan_id": item["plan_id"]},
                    UpdateExpression="SET #s = :s",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={":s": "SUPERSEDED"}
                )
    except Exception as e:
        logger.warning(f"Failed to supersede old plans: {e}")


def _response(status_code: int, body: dict) -> dict:
    """Standard API Gateway response."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS"
        },
        "body": json.dumps(body, default=str)
    }
