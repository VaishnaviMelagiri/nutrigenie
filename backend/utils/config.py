"""
Centralized configuration for the Meal Plan Generator.
All AWS resource names, model IDs, and system constants.
"""

import os

# ─── AWS Region ───────────────────────────────────────────────
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# ─── S3 Buckets ───────────────────────────────────────────────
REPORTS_BUCKET = os.environ.get("REPORTS_BUCKET", "meal-plan-reports")
VECTORS_BUCKET = os.environ.get("VECTORS_BUCKET", "meal-plan-vectors")
FRONTEND_BUCKET = os.environ.get("FRONTEND_BUCKET", "meal-plan-frontend")

# ─── DynamoDB Tables ──────────────────────────────────────────
PATIENT_PROFILES_TABLE = os.environ.get("PATIENT_PROFILES_TABLE", "PatientProfiles")
MEAL_PLANS_TABLE = os.environ.get("MEAL_PLANS_TABLE", "MealPlans")
NUTRITION_DATA_TABLE = os.environ.get("NUTRITION_DATA_TABLE", "NutritionData")

# ─── Bedrock Models ───────────────────────────────────────────
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
LLM_MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"

# ─── Embedding Config ────────────────────────────────────────
EMBEDDING_DIMENSIONS = 768
EMBEDDING_NORMALIZE = True

# ─── LLM Config ──────────────────────────────────────────────
LLM_MAX_TOKENS = 4096
LLM_TEMPERATURE_GENERATION = 0.3      # Balanced: factual but varied meals
LLM_TEMPERATURE_EXTRACTION = 0.1      # Very deterministic for data extraction
LLM_TEMPERATURE_ALTERNATIVES = 0.4    # Slightly more creative for variety

# ─── Chunking Config ─────────────────────────────────────────
MAX_CHUNK_SIZE_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 50

# ─── RAG Retrieval Config ────────────────────────────────────
RAG_TOP_K_PATIENT = 5       # Top-K patient report chunks
RAG_TOP_K_NUTRITION = 10    # Top-K nutrition items
RAG_SIMILARITY_THRESHOLD = 0.7

# ─── Nutrition Defaults ──────────────────────────────────────
DEFAULT_CALORIE_TARGET = 1800
CALORIE_TOLERANCE_PERCENT = 10  # ±10% of target
MIN_PROTEIN_G = 50
MIN_FIBER_G = 25
MAX_SODIUM_MG = 2300

# ─── Meal Structure ──────────────────────────────────────────
MEALS_PER_DAY = 5
MEAL_TYPES = ["breakfast", "mid_morning_snack", "lunch", "evening_snack", "dinner"]
PLAN_DAYS = 7

# ─── Calorie Distribution per Meal (% of daily target) ──────
CALORIE_DISTRIBUTION = {
    "breakfast": 0.25,
    "mid_morning_snack": 0.10,
    "lunch": 0.30,
    "evening_snack": 0.10,
    "dinner": 0.25
}

# ─── TTL for DynamoDB (seconds) ──────────────────────────────
MEAL_PLAN_TTL_DAYS = 90
MEAL_PLAN_TTL_SECONDS = MEAL_PLAN_TTL_DAYS * 86400

# ─── FAISS Index Paths in S3 ─────────────────────────────────
NUTRITION_INDEX_KEY = "base/nutrition_index.faiss"
NUTRITION_METADATA_KEY = "base/nutrition_metadata.json"
PATIENT_INDEX_PREFIX = "patients"

# ─── Report Extraction Sections ──────────────────────────────
REPORT_SECTIONS = [
    "patient_demographics",
    "bacterial_analysis",
    "food_sensitivity",
    "avoid_recommendations",
    "reduce_recommendations",
    "supplement_recommendations",
    "gut_health_summary"
]

# ─── Lambda /tmp cache ───────────────────────────────────────
LAMBDA_TMP_DIR = "/tmp"
FAISS_CACHE_DIR = f"{LAMBDA_TMP_DIR}/faiss_cache"
