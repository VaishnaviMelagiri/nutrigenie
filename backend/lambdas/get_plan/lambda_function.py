"""
Lambda: get_plan
Fetches the active meal plan for a patient by kit_id.
Triggered via API Gateway GET /plan/{kit_id}.
"""

import json
import os
import logging
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key, Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
MEAL_PLANS_TABLE = os.environ.get("MEAL_PLANS_TABLE", "MealPlans")


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def lambda_handler(event, context):
    try:
        kit_id = event.get("pathParameters", {}).get("kit_id", "")
        if not kit_id:
            return _response(400, {"error": "kit_id path parameter is required"})

        table = dynamodb.Table(MEAL_PLANS_TABLE)

        # Query for the most recent active plan
        result = table.query(
            KeyConditionExpression=Key("kit_id").eq(kit_id),
            FilterExpression=Attr("status").eq("ACTIVE"),
            ScanIndexForward=False,  # newest first
            Limit=1
        )

        items = result.get("Items", [])
        if not items:
            return _response(404, {"error": f"No active meal plan found for kit_id: {kit_id}"})

        plan = items[0]

        return _response(200, {
            "kit_id": kit_id,
            "plan_id": plan.get("plan_id"),
            "created_at": plan.get("created_at"),
            "status": plan.get("status"),
            "meal_plan": plan.get("meals", {}),
            "nutrition_summary": plan.get("nutrition_summary", {}),
            "validation": plan.get("validation_result", {})
        })

    except Exception as e:
        logger.error(f"Error fetching plan: {e}", exc_info=True)
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
