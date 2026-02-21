"""
Lambda: get_profile
Simple read-only function to fetch a patient profile by kit_id.
Triggered via API Gateway GET /profile/{kit_id}.
"""

import json
import os
import logging
from decimal import Decimal

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
PATIENT_TABLE = os.environ.get("PATIENT_PROFILES_TABLE", "PatientProfiles")


class DecimalEncoder(json.JSONEncoder):
    """Handle DynamoDB Decimal types in JSON output."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def lambda_handler(event, context):
    try:
        kit_id = event.get("pathParameters", {}).get("kit_id", "")
        if not kit_id:
            return _response(400, {"error": "kit_id path parameter is required"})

        table = dynamodb.Table(PATIENT_TABLE)
        result = table.get_item(Key={"kit_id": kit_id})
        item = result.get("Item")

        if not item:
            return _response(404, {"error": f"Patient profile not found for kit_id: {kit_id}"})

        # Remove large fields from response to keep it lightweight
        item.pop("report_chunks", None)

        return _response(200, item)

    except Exception as e:
        logger.error(f"Error fetching profile: {e}", exc_info=True)
        return _response(500, {"error": str(e)})


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "GET, OPTIONS"
        },
        "body": json.dumps(body, cls=DecimalEncoder)
    }
