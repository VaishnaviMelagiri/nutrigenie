"""
Lambda: generate_embeddings
Generates vector embeddings for patient report chunks and nutrition data
using Amazon Bedrock Titan Embeddings V2. Builds FAISS index and stores in S3.
"""

import json
import os
import struct
import logging
from datetime import datetime

import boto3
import numpy as np

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── AWS Clients ──
s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime")
dynamodb = boto3.resource("dynamodb")

PATIENT_TABLE = os.environ.get("PATIENT_PROFILES_TABLE", "PatientProfiles")
NUTRITION_TABLE = os.environ.get("NUTRITION_DATA_TABLE", "NutritionData")
VECTORS_BUCKET = os.environ.get("VECTORS_BUCKET", "meal-plan-vectors")
EMBEDDING_MODEL_ID = os.environ.get("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")
EMBEDDING_DIM = 768


def lambda_handler(event, context):
    """
    Invoked asynchronously after report extraction.
    Input: {"kit_id": "KIT-2024-00142"}
    
    Also handles one-time nutrition dataset indexing:
    Input: {"action": "index_nutrition"}
    """
    try:
        action = event.get("action", "index_patient")

        if action == "index_nutrition":
            return _index_nutrition_data()

        kit_id = event.get("kit_id")
        if not kit_id:
            return {"statusCode": 400, "body": "kit_id is required"}

        logger.info(f"Generating embeddings for kit_id={kit_id}")

        # ── Fetch patient chunks from DynamoDB ──
        table = dynamodb.Table(PATIENT_TABLE)
        response = table.get_item(Key={"kit_id": kit_id})
        patient = response.get("Item")

        if not patient:
            return {"statusCode": 404, "body": f"Patient {kit_id} not found"}

        chunks = patient.get("report_chunks", [])
        if not chunks:
            return {"statusCode": 400, "body": "No report chunks found for embedding"}

        # ── Generate embeddings for each chunk ──
        embeddings = []
        metadata = []

        for chunk in chunks:
            text = chunk.get("text", "")
            if not text.strip():
                continue

            embedding = _generate_embedding(text)
            embeddings.append(embedding)
            metadata.append({
                "chunk_index": chunk.get("chunk_index", 0),
                "text": text[:200],  # Store truncated text for reference
                "char_count": chunk.get("char_count", len(text))
            })

        if not embeddings:
            return {"statusCode": 400, "body": "No valid embeddings generated"}

        # ── Build and upload FAISS index ──
        embeddings_array = np.array(embeddings, dtype=np.float32)
        index_bytes = _build_simple_index(embeddings_array)

        # Upload index to S3
        index_key = f"patients/{kit_id}/patient_index.faiss"
        metadata_key = f"patients/{kit_id}/patient_metadata.json"

        s3.put_object(
            Bucket=VECTORS_BUCKET,
            Key=index_key,
            Body=index_bytes
        )
        s3.put_object(
            Bucket=VECTORS_BUCKET,
            Key=metadata_key,
            Body=json.dumps(metadata).encode()
        )

        # ── Update DynamoDB with index location ──
        table.update_item(
            Key={"kit_id": kit_id},
            UpdateExpression="SET vector_index_key = :key, updated_at = :now",
            ExpressionAttributeValues={
                ":key": index_key,
                ":now": datetime.utcnow().isoformat() + "Z"
            }
        )

        logger.info(f"Generated {len(embeddings)} embeddings for kit_id={kit_id}")
        return {
            "statusCode": 200,
            "body": json.dumps({
                "kit_id": kit_id,
                "embeddings_count": len(embeddings),
                "index_key": index_key
            })
        }

    except Exception as e:
        logger.error(f"Embedding error: {str(e)}", exc_info=True)
        return {"statusCode": 500, "body": f"Error: {str(e)}"}


def _index_nutrition_data():
    """
    One-time indexing of the IFCT nutrition dataset.
    Reads all items from NutritionData table, generates embeddings, builds FAISS index.
    """
    logger.info("Starting nutrition dataset indexing...")
    table = dynamodb.Table(NUTRITION_TABLE)

    # Scan all nutrition data
    items = []
    response = table.scan()
    items.extend(response.get("Items", []))
    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        items.extend(response.get("Items", []))

    logger.info(f"Found {len(items)} nutrition items to index")

    embeddings = []
    metadata = []

    for item in items:
        # Create a rich text representation for embedding
        text = _nutrition_to_text(item)
        embedding = _generate_embedding(text)
        embeddings.append(embedding)
        metadata.append({
            "food_id": item.get("food_id", ""),
            "name_en": item.get("name_en", ""),
            "category": item.get("category", ""),
            "text_preview": text[:200]
        })

    if not embeddings:
        return {"statusCode": 400, "body": "No nutrition items to index"}

    embeddings_array = np.array(embeddings, dtype=np.float32)
    index_bytes = _build_simple_index(embeddings_array)

    # Upload to S3
    s3.put_object(
        Bucket=VECTORS_BUCKET,
        Key="base/nutrition_index.faiss",
        Body=index_bytes
    )
    s3.put_object(
        Bucket=VECTORS_BUCKET,
        Key="base/nutrition_metadata.json",
        Body=json.dumps(metadata).encode()
    )

    logger.info(f"Indexed {len(embeddings)} nutrition items")
    return {
        "statusCode": 200,
        "body": json.dumps({
            "items_indexed": len(embeddings),
            "index_key": "base/nutrition_index.faiss"
        })
    }


def _nutrition_to_text(item: dict) -> str:
    """Convert a nutrition database item to a natural language text for embedding."""
    per_100g = item.get("per_100g", {})
    parts = [
        f"{item.get('name_en', 'Unknown food')}",
        f"Category: {item.get('category', 'Unknown')}",
        f"Hindi name: {item.get('name_hi', 'N/A')}",
        f"Per 100g: {per_100g.get('calories', 0)} kcal, "
        f"protein {per_100g.get('protein_g', 0)}g, "
        f"carbs {per_100g.get('carbs_g', 0)}g, "
        f"fat {per_100g.get('fat_g', 0)}g, "
        f"fiber {per_100g.get('fiber_g', 0)}g",
    ]

    micronutrients = item.get("micronutrients", {})
    if micronutrients:
        micro_parts = [f"{k}: {v}" for k, v in micronutrients.items()]
        parts.append(f"Micronutrients: {', '.join(micro_parts)}")

    common_dishes = item.get("common_dishes", [])
    if common_dishes:
        parts.append(f"Used in: {', '.join(common_dishes[:5])}")

    allergens = item.get("allergen_tags", [])
    if allergens:
        parts.append(f"Allergens: {', '.join(allergens)}")

    parts.append(f"Season: {item.get('season', 'year-round')}")

    return ". ".join(parts)


def _generate_embedding(text: str) -> list[float]:
    """Generate a single embedding using Bedrock Titan Embeddings V2."""
    response = bedrock.invoke_model(
        modelId=EMBEDDING_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "inputText": text[:8000],  # Titan V2 max input
            "dimensions": EMBEDDING_DIM,
            "normalize": True
        })
    )
    result = json.loads(response["body"].read())
    return result["embedding"]


def _build_simple_index(embeddings: np.ndarray) -> bytes:
    """
    Build a simple brute-force flat index (no FAISS dependency needed).
    Stores embeddings as a simple binary format that can be searched with numpy.

    Custom format:
    - 4 bytes: number of vectors (uint32)
    - 4 bytes: dimension (uint32)
    - N * D * 4 bytes: float32 embeddings
    """
    n, d = embeddings.shape
    header = struct.pack("II", n, d)
    data = embeddings.tobytes()
    return header + data


def search_index(index_bytes: bytes, query_embedding: np.ndarray, top_k: int = 5) -> list[tuple[int, float]]:
    """
    Search the simple flat index. Returns list of (index, cosine_similarity) tuples.
    This function is used by other Lambdas.
    """
    # Parse header
    n, d = struct.unpack("II", index_bytes[:8])
    embeddings = np.frombuffer(index_bytes[8:], dtype=np.float32).reshape(n, d)

    # Cosine similarity (vectors are already L2-normalized)
    query = query_embedding.reshape(1, -1).astype(np.float32)
    similarities = np.dot(embeddings, query.T).flatten()

    # Get top-k
    top_indices = np.argsort(similarities)[::-1][:top_k]
    results = [(int(idx), float(similarities[idx])) for idx in top_indices]

    return results
