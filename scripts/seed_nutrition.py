"""
Seed Script: Load Indian nutrition dataset into DynamoDB NutritionData table.
Run this ONCE after deploying the infrastructure.

Usage:
    python scripts/seed_nutrition.py
"""

import json
import os
import sys
import boto3
from decimal import Decimal

# ── Configuration ──
TABLE_NAME = os.environ.get("NUTRITION_DATA_TABLE", "NutritionData")
REGION = os.environ.get("AWS_REGION", "us-east-1")
DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "backend", "data", "indian_nutrition_dataset.json")


def decimal_default(obj):
    """Convert floats to Decimal for DynamoDB compatibility."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def convert_to_dynamodb_format(item):
    """Recursively convert all floats/ints in a dict to Decimal for DynamoDB."""
    if isinstance(item, dict):
        return {k: convert_to_dynamodb_format(v) for k, v in item.items()}
    elif isinstance(item, list):
        return [convert_to_dynamodb_format(i) for i in item]
    elif isinstance(item, float):
        return Decimal(str(item))
    elif isinstance(item, int):
        return Decimal(str(item))
    return item


def main():
    print(f"🔧 Seeding DynamoDB table: {TABLE_NAME}")
    print(f"📁 Data file: {DATA_FILE}")
    print(f"🌍 Region: {REGION}")
    print()

    # Load dataset
    if not os.path.exists(DATA_FILE):
        print(f"❌ Error: Data file not found at {DATA_FILE}")
        print("   Make sure you're running from the project root directory.")
        sys.exit(1)

    with open(DATA_FILE, "r") as f:
        foods = json.loads(f.read())

    print(f"📊 Found {len(foods)} food items in dataset")

    # Connect to DynamoDB
    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)

    # Verify table exists
    try:
        table.load()
        print(f"✅ Table '{TABLE_NAME}' exists")
    except Exception as e:
        print(f"❌ Error: Table '{TABLE_NAME}' not found. Deploy infrastructure first!")
        print(f"   Error details: {e}")
        sys.exit(1)

    # Batch write items
    success_count = 0
    error_count = 0

    with table.batch_writer() as batch:
        for food in foods:
            try:
                # Convert all numbers to Decimal
                item = convert_to_dynamodb_format(food)
                batch.put_item(Item=item)
                success_count += 1
                print(f"  ✓ [{food['food_id']}] {food['name_en']}")
            except Exception as e:
                error_count += 1
                print(f"  ✗ [{food.get('food_id', '?')}] Error: {e}")

    print()
    print(f"{'='*50}")
    print(f"✅ Successfully loaded: {success_count} items")
    if error_count > 0:
        print(f"❌ Errors: {error_count} items")
    print(f"{'='*50}")
    print()
    print("Next step: Run the embedding indexer to create the nutrition vector index.")
    print("You can invoke the embedding Lambda with:")
    print(f'  aws lambda invoke --function-name nutrigenie-generate-embeddings \\')
    print(f'    --payload \'{{"action": "index_nutrition"}}\' \\')
    print(f'    --region {REGION} output.json')


if __name__ == "__main__":
    main()
