"""
Lambda: generate_meal
RAG-based meal plan generation using Amazon Titan Text Express.
Reads patient data from S3, uses Indian nutrition dataset for RAG context,
generates a personalized 7-day meal plan with full nutrition breakdown.

API: POST /meal
Body: {"kit_id": "IOM_KIT001"}
"""

import json
import os
import logging
import struct
from datetime import datetime

import boto3
import numpy as np

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime")

DATA_BUCKET = os.environ.get("DATA_BUCKET", "nutrigenie-data")
LLM_MODEL_ID = os.environ.get("LLM_MODEL_ID", "amazon.nova-micro-v1:0")
EMBEDDING_MODEL_ID = os.environ.get("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")

# Cache for nutrition data (persists across warm Lambda invocations)
_nutrition_cache = {"data": None, "embeddings": None, "texts": None}


def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body", "{}")) if isinstance(event.get("body"), str) else event.get("body", {})
        kit_id = body.get("kit_id", "").strip()

        if not kit_id:
            return _response(400, {"error": "kit_id is required"})

        logger.info(f"Generating meal plan for kit_id: {kit_id}")

        # Step 1: Load patient data
        patient = _load_patient_data(kit_id)
        if not patient:
            return _response(404, {"error": f"No patient data found for {kit_id}"})

        # Step 2: Load nutrition dataset
        nutrition_data = _load_nutrition_data()

        # Step 3: RAG — find relevant foods based on patient constraints
        relevant_foods = _rag_retrieve(patient, nutrition_data)

        # Step 4: Generate meal plan via Bedrock
        meal_plan = _generate_meal_plan(patient, relevant_foods)

        # Step 5: Enrich with nutrition data
        enriched_plan = _enrich_with_nutrition(meal_plan, nutrition_data)

        return _response(200, {
            "kit_id": kit_id,
            "generated_at": datetime.utcnow().isoformat(),
            "patient_summary": {
                "name": patient.get("name", ""),
                "diet_type": patient.get("diet_type", ""),
                "avoid_list": patient.get("avoid_list", []),
                "bmi": patient.get("bmi", ""),
                "ibs_type": patient.get("ibs_info", {}).get("subtype", ""),
            },
            "meal_plan": enriched_plan,
        })

    except Exception as e:
        logger.error(f"Error generating meal plan: {e}", exc_info=True)
        return _response(500, {"error": str(e)})


# ═══════════════════════════════════════════════════════════
# Data Loading
# ═══════════════════════════════════════════════════════════

def _load_patient_data(kit_id: str) -> dict:
    """Load and parse patient iom_data from S3."""
    try:
        obj = s3.get_object(Bucket=DATA_BUCKET, Key=f"patients/{kit_id}.json")
        raw_data = json.loads(obj["Body"].read().decode("utf-8"))
        return _parse_iom_data(raw_data, kit_id)
    except Exception as e:
        logger.error(f"Failed to load patient {kit_id}: {e}")
        return None


def _parse_iom_data(data: dict, kit_id: str) -> dict:
    """Extract key fields from iom_data.json."""
    metadata = data.get("metadata", {})
    tokens = data.get("tokens", {})

    allergies_raw = metadata.get(
        "Do you have food allergies or intolerances?",
        metadata.get("Do you have any food allergies or intolerances?", "")
    )
    avoid_list = []
    if allergies_raw and allergies_raw.lower() not in ["no", "none", ""]:
        avoid_list = [item.strip().lower() for item in allergies_raw.replace("(legumes)", "").split(",") if item.strip()]

    # Parse bacteria targets
    bacteria_increase = []
    bacteria_decrease = []
    try:
        bacteria_raw = json.loads(tokens.get("#TID009", "[]"))
        for b in bacteria_raw:
            if b.get("Category") != "Bacteria":
                continue
            entry = {"name": b.get("Token_name", ""), "description": b.get("Description", "")}
            if b.get("Type") == "increase":
                bacteria_increase.append(entry)
            elif b.get("Type") == "decrease":
                bacteria_decrease.append(entry)
    except (json.JSONDecodeError, TypeError):
        pass

    return {
        "kit_id": kit_id,
        "name": metadata.get("Name", ""),
        "gender": metadata.get("Gender", ""),
        "age": metadata.get("Age", ""),
        "weight_kg": metadata.get("Weight", ""),
        "height_cm": metadata.get("Height", ""),
        "bmi": metadata.get("BMI", ""),
        "location": metadata.get("Location", ""),
        "diet_type": metadata.get("Which best describes your usual diet", "Veg"),
        "avoid_list": avoid_list,
        "ibs_info": {
            "subtype": metadata.get("Do you know which subtype of IBS you have?", ""),
            "severity_level": metadata.get("IBS Severity Level", ""),
        },
        "prebiotics": metadata.get("Prebiotics - Gut affectors", ""),
        "bacteria_to_increase": bacteria_increase,
        "bacteria_to_decrease": bacteria_decrease,
        "symptoms": {
            field: metadata.get(field, "Not Severe")
            for field in ["Anxiety", "Stress", "Flatulence/Bloating", "Acid Reflux", "Disturbed Sleep"]
        },
    }


def _load_nutrition_data() -> list:
    """Load Indian nutrition dataset from S3 (cached)."""
    if _nutrition_cache["data"]:
        return _nutrition_cache["data"]

    try:
        obj = s3.get_object(Bucket=DATA_BUCKET, Key="nutrition/indian_nutrition_dataset.json")
        data = json.loads(obj["Body"].read().decode("utf-8"))
        _nutrition_cache["data"] = data
        return data
    except Exception as e:
        logger.error(f"Failed to load nutrition data: {e}")
        return []


# ═══════════════════════════════════════════════════════════
# RAG Retrieval
# ═══════════════════════════════════════════════════════════

def _generate_embedding(text: str) -> list:
    """Generate embedding using Titan Embeddings V2."""
    try:
        response = bedrock.invoke_model(
            modelId=EMBEDDING_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({"inputText": text[:2000]})
        )
        result = json.loads(response["body"].read())
        return result.get("embedding", [])
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return []


def _rag_retrieve(patient: dict, nutrition_data: list) -> list:
    """Find the most relevant foods for this patient using semantic search + filtering."""

    # Build query from patient context
    query_parts = [
        f"Indian {patient['diet_type']} meals for IBS patient",
        f"Avoid: {', '.join(patient['avoid_list'])}" if patient['avoid_list'] else "",
        f"Location: {patient.get('location', '')}",
        f"BMI: {patient.get('bmi', '')} — {'underweight, needs high-calorie foods' if float(patient.get('bmi', '20') or '20') < 18.5 else 'normal weight'}",
    ]
    # Add bacteria context
    increase_names = [b["name"] for b in patient.get("bacteria_to_increase", []) if "Other" not in b["name"]]
    decrease_names = [b["name"] for b in patient.get("bacteria_to_decrease", []) if "Other" not in b["name"]]
    if increase_names:
        query_parts.append(f"Foods that support: {', '.join(increase_names[:3])}")
    if decrease_names:
        query_parts.append(f"Reduce bacteria: {', '.join(decrease_names[:3])}")

    query = ". ".join([p for p in query_parts if p])

    # Generate query embedding
    query_embedding = _generate_embedding(query)

    if not query_embedding:
        # Fallback: filter by category without embeddings
        logger.warning("Embedding generation failed, using category-based filtering")
        return _filter_by_constraints(nutrition_data, patient)

    # Generate embeddings for each food item (or use cached)
    if _nutrition_cache["embeddings"] is None:
        food_texts = []
        for food in nutrition_data:
            text = f"{food['name_en']} ({food['category']}). "
            text += f"Calories: {food['per_100g']['calories']}, Protein: {food['per_100g']['protein_g']}g. "
            text += f"Common dishes: {', '.join(food.get('common_dishes', [])[:3])}. "
            text += f"Allergens: {', '.join(food.get('allergen_tags', []))}." if food.get('allergen_tags') else ""
            food_texts.append(text)

        embeddings = []
        for text in food_texts:
            emb = _generate_embedding(text)
            if emb:
                embeddings.append(emb)
            else:
                embeddings.append([0.0] * 1024)  # fallback zero vector

        _nutrition_cache["embeddings"] = np.array(embeddings, dtype=np.float32)
        _nutrition_cache["texts"] = food_texts

    # Cosine similarity search
    query_vec = np.array(query_embedding, dtype=np.float32)
    query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-8)

    food_embeddings = _nutrition_cache["embeddings"]
    norms = np.linalg.norm(food_embeddings, axis=1, keepdims=True) + 1e-8
    food_normed = food_embeddings / norms

    similarities = np.dot(food_normed, query_norm)

    # Get top 30 most relevant foods
    top_indices = np.argsort(similarities)[::-1][:30]

    # Filter out foods in avoid list
    relevant_foods = []
    for idx in top_indices:
        food = nutrition_data[idx]
        food_name_lower = food["name_en"].lower()

        # Check avoid list
        is_avoided = False
        for avoid_item in patient.get("avoid_list", []):
            if avoid_item in food_name_lower or food_name_lower in avoid_item:
                is_avoided = True
                break

        # Check allergen tags against avoid list
        for tag in food.get("allergen_tags", []):
            if tag.lower() in " ".join(patient.get("avoid_list", [])):
                is_avoided = True
                break

        if not is_avoided:
            food_copy = dict(food)
            food_copy["relevance_score"] = float(similarities[idx])
            relevant_foods.append(food_copy)

    return relevant_foods[:20]


def _filter_by_constraints(nutrition_data: list, patient: dict) -> list:
    """Fallback: filter foods by constraints without embeddings."""
    avoid_set = set(patient.get("avoid_list", []))
    result = []
    for food in nutrition_data:
        name_lower = food["name_en"].lower()
        skip = False
        for avoid in avoid_set:
            if avoid in name_lower:
                skip = True
                break
        if not skip:
            result.append(food)
    return result[:20]


# ═══════════════════════════════════════════════════════════
# Meal Plan Generation via Bedrock
# ═══════════════════════════════════════════════════════════

def _generate_meal_plan(patient: dict, relevant_foods: list) -> dict:
    """Generate a 7-day meal plan using Amazon Titan Text Express with RAG context."""

    # Build food context for the prompt
    food_context = "\n".join([
        f"- {f['name_en']} ({f['category']}): {f['per_100g']['calories']} kcal, "
        f"protein {f['per_100g']['protein_g']}g, carbs {f['per_100g']['carbs_g']}g, "
        f"fat {f['per_100g']['fat_g']}g, fiber {f['per_100g']['fiber_g']}g per 100g. "
        f"Dishes: {', '.join(f.get('common_dishes', [])[:3])}"
        for f in relevant_foods[:15]
    ])

    # Build bacteria context
    increase_context = "\n".join([
        f"- Increase {b['name']}: {b['description'][:100]}..."
        for b in patient.get("bacteria_to_increase", [])[:5]
        if "Other" not in b["name"]
    ])
    decrease_context = "\n".join([
        f"- Decrease {b['name']}: {b['description'][:100]}..."
        for b in patient.get("bacteria_to_decrease", [])[:5]
        if "Other" not in b["name"]
    ])

    # Determine calorie target based on BMI
    bmi = float(patient.get("bmi", "20") or "20")
    if bmi < 18.5:
        calorie_target = 2200
        weight_note = "UNDERWEIGHT (BMI {:.1f}). Prioritize calorie-dense, nutrient-rich foods.".format(bmi)
    elif bmi > 25:
        calorie_target = 1600
        weight_note = "OVERWEIGHT (BMI {:.1f}). Focus on low-calorie, high-fiber foods.".format(bmi)
    else:
        calorie_target = 1800
        weight_note = f"NORMAL weight (BMI {bmi:.1f})."

    prompt = f"""You are a certified Indian clinical nutritionist AI. Generate a personalized 7-day Indian household meal plan.

STRICT RULES:
1. NEVER use any food from the AVOID LIST.
2. Use ONLY foods from the PROVIDED NUTRITION DATABASE.
3. Every meal must include exact quantities in grams.
4. Every meal must include calories, protein_g, carbs_g, fat_g, fiber_g.
5. Daily total must be close to the calorie target (±10%).
6. All meals must be traditional Indian household recipes.
7. Output ONLY valid JSON. No explanations.
8. Each day has 5 meals: breakfast, mid_morning_snack, lunch, evening_snack, dinner.
9. For IBS patients: avoid gas-producing foods, prefer easy-to-digest meals.

PATIENT PROFILE:
- Diet: {patient['diet_type']}
- Location: {patient.get('location', 'India')}
- Weight status: {weight_note}
- IBS: {patient['ibs_info'].get('subtype', 'N/A')} ({patient['ibs_info'].get('severity_level', 'N/A')})
- Daily calorie target: {calorie_target} kcal

AVOID LIST (NEVER USE THESE): {', '.join(patient['avoid_list']) if patient['avoid_list'] else 'None'}

BACTERIA GOALS:
{increase_context or 'None specified'}
{decrease_context or 'None specified'}

AVAILABLE FOODS FROM IFCT DATABASE:
{food_context}

OUTPUT JSON SCHEMA:
{{
  "calorie_target": {calorie_target},
  "day_1": {{
    "breakfast": {{"name": "...", "ingredients": [{{"name": "...", "quantity_g": 100}}], "total_calories": 400, "protein_g": 12, "carbs_g": 50, "fat_g": 10, "fiber_g": 5, "prep_time_min": 15, "benefits": "..."}},
    "mid_morning_snack": {{...}},
    "lunch": {{...}},
    "evening_snack": {{...}},
    "dinner": {{...}}
  }},
  "day_2": {{...}},
  ... (all 7 days)
}}

Generate the complete 7-day meal plan now. Output ONLY valid JSON."""

    try:
        response = bedrock.invoke_model(
            modelId=LLM_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "messages": [{"role": "user", "content": [{"text": prompt}]}],
                "inferenceConfig": {
                    "maxTokens": 8000,
                    "temperature": 0.3,
                    "topP": 0.9,
                }
            })
        )

        result = json.loads(response["body"].read())
        content = result.get("output", {}).get("message", {}).get("content", [{}])[0].get("text", "")

        # Extract JSON from response
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            meal_plan = json.loads(content[json_start:json_end])
            return meal_plan

        logger.error(f"No valid JSON found in LLM response: {content[:200]}")
        return _generate_fallback_plan(patient, relevant_foods, calorie_target)

    except Exception as e:
        logger.error(f"Bedrock invocation failed: {e}", exc_info=True)
        return _generate_fallback_plan(patient, relevant_foods, calorie_target)


def _generate_fallback_plan(patient: dict, foods: list, calorie_target: int) -> dict:
    """Generate a simple fallback meal plan if Bedrock fails."""
    plan = {"calorie_target": calorie_target, "note": "Fallback plan — AI was unavailable"}
    safe_foods = [f for f in foods if f["category"] in ["Cereals", "Pulses", "Vegetables", "Fruits", "Dairy"]][:10]

    for day_num in range(1, 8):
        day_key = f"day_{day_num}"
        plan[day_key] = {}
        for meal_type in ["breakfast", "mid_morning_snack", "lunch", "evening_snack", "dinner"]:
            food = safe_foods[day_num % len(safe_foods)] if safe_foods else {"name_en": "Rice", "per_100g": {"calories": 345, "protein_g": 7, "carbs_g": 78, "fat_g": 0.5, "fiber_g": 0.2}}
            plan[day_key][meal_type] = {
                "name": f"{food['name_en']} {meal_type.replace('_', ' ')}",
                "ingredients": [{"name": food["name_en"], "quantity_g": 100}],
                "total_calories": food["per_100g"]["calories"],
                "protein_g": food["per_100g"]["protein_g"],
                "carbs_g": food["per_100g"]["carbs_g"],
                "fat_g": food["per_100g"]["fat_g"],
                "fiber_g": food["per_100g"]["fiber_g"],
            }
    return plan


# ═══════════════════════════════════════════════════════════
# Nutrition Enrichment
# ═══════════════════════════════════════════════════════════

def _enrich_with_nutrition(plan: dict, nutrition_data: list) -> dict:
    """Add detailed nutrition data for each ingredient from IFCT database."""
    food_lookup = {f["food_id"]: f for f in nutrition_data}
    name_lookup = {f["name_en"].lower(): f for f in nutrition_data}

    for day_key in [f"day_{i}" for i in range(1, 8)]:
        day = plan.get(day_key, {})
        if not isinstance(day, dict):
            continue

        daily_totals = {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "fiber_g": 0}

        for meal_type in ["breakfast", "mid_morning_snack", "lunch", "evening_snack", "dinner"]:
            meal = day.get(meal_type, {})
            if not isinstance(meal, dict):
                continue

            # Enrich ingredients with nutrition data
            for ing in meal.get("ingredients", []):
                food_id = ing.get("food_id", "")
                food_name = ing.get("name", "").lower()

                nutrition_info = food_lookup.get(food_id)
                if not nutrition_info:
                    nutrition_info = name_lookup.get(food_name)

                if nutrition_info:
                    qty = ing.get("quantity_g", 100)
                    multiplier = qty / 100.0
                    ing["nutrition_per_serving"] = {
                        "calories": round(nutrition_info["per_100g"]["calories"] * multiplier, 1),
                        "protein_g": round(nutrition_info["per_100g"]["protein_g"] * multiplier, 1),
                        "carbs_g": round(nutrition_info["per_100g"]["carbs_g"] * multiplier, 1),
                        "fat_g": round(nutrition_info["per_100g"]["fat_g"] * multiplier, 1),
                        "fiber_g": round(nutrition_info["per_100g"]["fiber_g"] * multiplier, 1),
                    }
                    if nutrition_info.get("micronutrients"):
                        ing["micronutrients"] = {
                            k: round(v * multiplier, 2)
                            for k, v in nutrition_info["micronutrients"].items()
                        }

            # Accumulate daily totals
            daily_totals["calories"] += meal.get("total_calories", 0)
            daily_totals["protein_g"] += meal.get("protein_g", 0)
            daily_totals["carbs_g"] += meal.get("carbs_g", 0)
            daily_totals["fat_g"] += meal.get("fat_g", 0)
            daily_totals["fiber_g"] += meal.get("fiber_g", 0)

        plan[day_key]["daily_totals"] = daily_totals

    return plan


# ═══════════════════════════════════════════════════════════
# HTTP Response
# ═══════════════════════════════════════════════════════════

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
