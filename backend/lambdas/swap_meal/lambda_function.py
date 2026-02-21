"""
Lambda: swap_meal
Generates a replacement meal when user rejects one.
Uses RAG to find a nutritionally similar alternative.

API: POST /swap
Body: {"kit_id": "IOM_KIT001", "day": "day_1", "meal_type": "breakfast", "current_meal": "Ragi Dosa", "reason": "optional"}
"""

import json
import os
import logging

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime")

DATA_BUCKET = os.environ.get("DATA_BUCKET", "nutrigenie-data")
LLM_MODEL_ID = os.environ.get("LLM_MODEL_ID", "amazon.titan-text-express-v1")


def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body", "{}")) if isinstance(event.get("body"), str) else event.get("body", {})
        kit_id = body.get("kit_id", "").strip()
        day = body.get("day", "")
        meal_type = body.get("meal_type", "")
        current_meal = body.get("current_meal", "")
        reason = body.get("reason", "")

        if not kit_id or not day or not meal_type:
            return _response(400, {"error": "kit_id, day, and meal_type are required"})

        logger.info(f"Swap meal for {kit_id}: {day}/{meal_type} (current: {current_meal})")

        # Load patient data
        patient = _load_patient(kit_id)
        if not patient:
            return _response(404, {"error": f"No patient data for {kit_id}"})

        # Load nutrition data for context
        nutrition_data = _load_nutrition_data()

        # Build food context (exclude current meal ingredients)
        food_context = "\n".join([
            f"- {f['name_en']} ({f['category']}): {f['per_100g']['calories']} kcal, "
            f"protein {f['per_100g']['protein_g']}g, carbs {f['per_100g']['carbs_g']}g, "
            f"fat {f['per_100g']['fat_g']}g, fiber {f['per_100g']['fiber_g']}g per 100g"
            for f in nutrition_data[:20]
            if f['name_en'].lower() not in current_meal.lower()
        ])

        avoid_list = _get_avoid_list(patient)

        # Generate replacement via Bedrock
        system_prompt = """You are a certified Indian clinical nutritionist AI. Generate exactly ONE replacement meal.
RULES:
1. NEVER use foods from the AVOID LIST.
2. Use DIFFERENT primary ingredients from the rejected meal.
3. Keep similar calorie count (±15%) and nutritional profile.
4. Must be a traditional Indian household recipe.
5. Output ONLY valid JSON. No explanations."""

        meal_labels = {
            "breakfast": "breakfast (7-8 AM)",
            "mid_morning_snack": "mid-morning snack (10-11 AM)",
            "lunch": "lunch (12:30-1:30 PM)",
            "evening_snack": "evening snack (4-5 PM)",
            "dinner": "dinner (7-8 PM)"
        }

        user_prompt = f"""PATIENT:
- Diet: {patient.get('diet_type', 'Veg')}
- IBS: {patient.get('ibs_subtype', 'IBS Diarrhoea')}

AVOID LIST (NEVER USE):
{', '.join(avoid_list) if avoid_list else 'None'}

REJECTED MEAL: {current_meal} (for {meal_labels.get(meal_type, meal_type)})
REJECTION REASON: {reason or 'User preference'}

AVAILABLE FOODS FROM IFCT DATABASE:
{food_context}

Generate ONE replacement {meal_labels.get(meal_type, meal_type)} meal.

OUTPUT JSON:
{{
  "name": "...",
  "ingredients": [{{"name": "...", "quantity_g": 100}}],
  "total_calories": 400,
  "protein_g": 12,
  "carbs_g": 50,
  "fat_g": 10,
  "fiber_g": 5,
  "prep_time_min": 15,
  "benefits": "Why this is good for the patient"
}}"""

        full_prompt = system_prompt + "\n\n" + user_prompt

        response = bedrock.invoke_model(
            modelId=LLM_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "inputText": full_prompt,
                "textGenerationConfig": {
                    "maxTokenCount": 1500,
                    "temperature": 0.5,
                    "topP": 0.9,
                }
            })
        )

        result = json.loads(response["body"].read())
        content = result.get("results", [{}])[0].get("outputText", "")

        # Parse JSON
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            new_meal = json.loads(content[json_start:json_end])
        else:
            return _response(500, {"error": "AI failed to generate valid replacement"})

        return _response(200, {
            "day": day,
            "meal_type": meal_type,
            "replaced": current_meal,
            "new_meal": new_meal,
        })

    except Exception as e:
        logger.error(f"Swap error: {e}", exc_info=True)
        return _response(500, {"error": str(e)})


def _load_patient(kit_id):
    try:
        obj = s3.get_object(Bucket=DATA_BUCKET, Key=f"patients/{kit_id}.json")
        data = json.loads(obj["Body"].read().decode("utf-8"))
        meta = data.get("metadata", {})
        return {
            "diet_type": meta.get("Which best describes your usual diet", "Veg"),
            "ibs_subtype": meta.get("Do you know which subtype of IBS you have?", ""),
            "allergies": meta.get("Do you have food allergies or intolerances?",
                                  meta.get("Do you have any food allergies or intolerances?", "")),
        }
    except Exception:
        return None


def _get_avoid_list(patient):
    raw = patient.get("allergies", "")
    if raw and raw.lower() not in ["no", "none", ""]:
        return [i.strip() for i in raw.replace("(legumes)", "").split(",") if i.strip()]
    return []


def _load_nutrition_data():
    try:
        obj = s3.get_object(Bucket=DATA_BUCKET, Key="nutrition/indian_nutrition_dataset.json")
        return json.loads(obj["Body"].read().decode("utf-8"))
    except Exception:
        return []


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        },
        "body": json.dumps(body, default=str),
    }
