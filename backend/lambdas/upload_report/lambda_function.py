"""
Lambda: upload_report
Handles IOM report PDF upload to S3 and creates initial patient record in DynamoDB.
Triggered via API Gateway POST /upload.
"""

import json
import os
import uuid
import base64
import logging
from datetime import datetime

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── AWS Clients ──
s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

REPORTS_BUCKET = os.environ.get("REPORTS_BUCKET", "meal-plan-reports")
PATIENT_TABLE = os.environ.get("PATIENT_PROFILES_TABLE", "PatientProfiles")


def lambda_handler(event, context):
    """
    Expects:
        POST body (JSON):
        {
            "kit_id": "KIT-2024-00142",
            "file_name": "report.pdf",
            "file_content_base64": "<base64-encoded PDF>"   # For direct upload
        }

    OR (pre-signed URL flow):
        {
            "kit_id": "KIT-2024-00142",
            "file_name": "report.pdf",
            "action": "get_upload_url"
        }
    """
    try:
        # Parse request body
        if isinstance(event.get("body"), str):
            body = json.loads(event["body"])
        else:
            body = event.get("body", event)

        kit_id = body.get("kit_id", "").strip()
        file_name = body.get("file_name", "report.pdf")
        action = body.get("action", "upload")

        if not kit_id:
            return _response(400, {"error": "kit_id is required"})

        # Sanitize kit_id
        kit_id = kit_id.replace("/", "_").replace("\\", "_")
        s3_key = f"{kit_id}/{file_name}"

        # ── Flow 1: Return pre-signed upload URL ──
        if action == "get_upload_url":
            presigned_url = s3.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": REPORTS_BUCKET,
                    "Key": s3_key,
                    "ContentType": "application/pdf"
                },
                ExpiresIn=300  # 5 minutes
            )

            # Create initial DynamoDB record
            _create_patient_record(kit_id, s3_key)

            return _response(200, {
                "message": "Upload URL generated",
                "upload_url": presigned_url,
                "kit_id": kit_id,
                "s3_key": s3_key,
                "expires_in_seconds": 300
            })

        # ── Flow 2: Direct base64 upload ──
        file_content_b64 = body.get("file_content_base64", "")
        if not file_content_b64:
            return _response(400, {"error": "file_content_base64 is required for direct upload"})

        # Decode and upload to S3
        file_bytes = base64.b64decode(file_content_b64)

        # Validate it's a PDF (check magic bytes)
        if not file_bytes[:5] == b"%PDF-":
            return _response(400, {"error": "File does not appear to be a valid PDF"})

        # Check file size (max 10 MB to stay within Lambda limits)
        max_size = 10 * 1024 * 1024
        if len(file_bytes) > max_size:
            return _response(400, {"error": f"File too large. Maximum size is {max_size // (1024*1024)} MB"})

        s3.put_object(
            Bucket=REPORTS_BUCKET,
            Key=s3_key,
            Body=file_bytes,
            ContentType="application/pdf",
            Metadata={
                "kit_id": kit_id,
                "uploaded_at": datetime.utcnow().isoformat()
            }
        )

        logger.info(f"Uploaded report for kit_id={kit_id} to s3://{REPORTS_BUCKET}/{s3_key}")

        # Create initial DynamoDB record
        _create_patient_record(kit_id, s3_key)

        return _response(200, {
            "message": "Report uploaded successfully",
            "kit_id": kit_id,
            "s3_key": s3_key,
            "status": "PENDING"
        })

    except json.JSONDecodeError:
        return _response(400, {"error": "Invalid JSON in request body"})
    except Exception as e:
        logger.error(f"Upload error: {str(e)}", exc_info=True)
        return _response(500, {"error": f"Internal server error: {str(e)}"})


def _create_patient_record(kit_id: str, s3_key: str):
    """Create or update the initial patient profile record in DynamoDB."""
    table = dynamodb.Table(PATIENT_TABLE)
    now = datetime.utcnow().isoformat() + "Z"

    table.put_item(
        Item={
            "kit_id": kit_id,
            "created_at": now,
            "updated_at": now,
            "report_s3_key": s3_key,
            "extraction_status": "PENDING",
            "avoid_list": [],
            "reduce_list": [],
            "recommended_list": [],
            "bacterial_history": [],
            "allergies": [],
            "medical_conditions": []
        },
        ConditionExpression="attribute_not_exists(kit_id)"  # Don't overwrite existing profiles
    )


def _response(status_code: int, body: dict) -> dict:
    """Standard API Gateway response."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "POST, OPTIONS"
        },
        "body": json.dumps(body)
    }
