"""
Lambda: extract_report
Triggered by S3 event when a new PDF is uploaded.
Uses Amazon Textract to extract text, then parses structured data
(avoid list, reduce list, recommendations, bacterial history)
using Bedrock Claude 3 Haiku.
"""

import json
import os
import re
import logging
from datetime import datetime

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── AWS Clients ──
s3 = boto3.client("s3")
textract = boto3.client("textract")
bedrock = boto3.client("bedrock-runtime")
dynamodb = boto3.resource("dynamodb")
lambda_client = boto3.client("lambda")

PATIENT_TABLE = os.environ.get("PATIENT_PROFILES_TABLE", "PatientProfiles")
EMBEDDING_LAMBDA = os.environ.get("EMBEDDING_LAMBDA", "meal-plan-generate-embeddings")
LLM_MODEL_ID = os.environ.get("LLM_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")


def lambda_handler(event, context):
    """
    Triggered by S3 ObjectCreated event.
    Event contains: Records[0].s3.bucket.name, Records[0].s3.object.key
    """
    try:
        # ── Parse S3 event ──
        record = event["Records"][0]["s3"]
        bucket = record["bucket"]["name"]
        key = record["object"]["key"]

        # Extract kit_id from key (format: kit_id/report.pdf)
        kit_id = key.split("/")[0]
        logger.info(f"Processing report for kit_id={kit_id}, s3://{bucket}/{key}")

        # ── Update status to PROCESSING ──
        _update_status(kit_id, "PROCESSING")

        # ── Step 1: Extract text using Textract ──
        logger.info("Calling Textract for text extraction...")
        raw_text = _extract_text_from_pdf(bucket, key)

        if not raw_text or len(raw_text.strip()) < 50:
            _update_status(kit_id, "FAILED", error="Textract returned insufficient text")
            return {"statusCode": 400, "body": "Insufficient text extracted from PDF"}

        logger.info(f"Extracted {len(raw_text)} characters from PDF")

        # ── Step 2: Parse structured data using LLM ──
        logger.info("Parsing report with Bedrock Claude...")
        parsed_data = _parse_report_with_llm(raw_text)

        # ── Step 3: Chunk text for RAG embeddings ──
        chunks = _chunk_report_text(raw_text)
        logger.info(f"Created {len(chunks)} text chunks for embedding")

        # ── Step 4: Update DynamoDB with extracted data ──
        _update_patient_profile(kit_id, parsed_data, chunks)

        # ── Step 5: Trigger embedding generation (async) ──
        _trigger_embedding_lambda(kit_id)

        logger.info(f"Successfully processed report for kit_id={kit_id}")
        return {
            "statusCode": 200,
            "body": json.dumps({
                "kit_id": kit_id,
                "status": "COMPLETED",
                "chunks_created": len(chunks),
                "avoid_count": len(parsed_data.get("avoid_list", [])),
                "reduce_count": len(parsed_data.get("reduce_list", [])),
                "recommended_count": len(parsed_data.get("recommended_list", []))
            })
        }

    except Exception as e:
        logger.error(f"Extraction error: {str(e)}", exc_info=True)
        if 'kit_id' in locals():
            _update_status(kit_id, "FAILED", error=str(e))
        return {"statusCode": 500, "body": f"Error: {str(e)}"}


def _extract_text_from_pdf(bucket: str, key: str) -> str:
    """Use Amazon Textract to extract text from a PDF stored in S3."""
    response = textract.detect_document_text(
        Document={
            "S3Object": {
                "Bucket": bucket,
                "Name": key
            }
        }
    )

    # Combine all detected text blocks
    lines = []
    for block in response.get("Blocks", []):
        if block["BlockType"] == "LINE":
            lines.append(block.get("Text", ""))

    return "\n".join(lines)


def _parse_report_with_llm(report_text: str) -> dict:
    """
    Use Bedrock Claude 3 Haiku to extract structured data from report text.
    Falls back to regex-based extraction if LLM fails.
    """
    system_prompt = """You are a medical data extraction AI specialized in IOM gut health reports.

Extract the following from the report text. Only extract what is EXPLICITLY stated.
If a field is not found, return an empty list.

Output valid JSON only:
{
  "avoid_list": ["items to avoid"],
  "reduce_list": ["items to reduce"],
  "recommended_list": ["recommended items"],
  "bacterial_history": [{"name": "str", "count": "str", "status": "elevated|normal|low|absent", "notes": "str"}],
  "allergies": ["allergies"],
  "medical_conditions": ["conditions"],
  "dietary_notes": "general notes"
}"""

    try:
        response = bedrock.invoke_model(
            modelId=LLM_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2048,
                "temperature": 0.1,
                "system": system_prompt,
                "messages": [
                    {
                        "role": "user",
                        "content": f"Extract structured data from this IOM report:\n\n{report_text[:8000]}"
                    }
                ]
            })
        )

        response_body = json.loads(response["body"].read())
        content = response_body["content"][0]["text"]

        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            parsed = json.loads(json_match.group())
            return parsed

    except Exception as e:
        logger.warning(f"LLM extraction failed, using regex fallback: {e}")

    # ── Regex fallback ──
    return _regex_extract(report_text)


def _regex_extract(text: str) -> dict:
    """Fallback regex-based extraction for common IOM report patterns."""
    result = {
        "avoid_list": [],
        "reduce_list": [],
        "recommended_list": [],
        "bacterial_history": [],
        "allergies": [],
        "medical_conditions": [],
        "dietary_notes": ""
    }

    text_lower = text.lower()

    # Common avoid patterns
    avoid_patterns = [
        r"(?:avoid|eliminate|remove|exclude)[:\s]+([^\n]+)",
        r"foods?\s+to\s+avoid[:\s]+([^\n]+)",
    ]
    for pattern in avoid_patterns:
        matches = re.findall(pattern, text_lower)
        for match in matches:
            items = [item.strip() for item in re.split(r'[,;]', match) if item.strip()]
            result["avoid_list"].extend(items)

    # Common reduce patterns
    reduce_patterns = [
        r"(?:reduce|minimize|limit|moderate)[:\s]+([^\n]+)",
        r"foods?\s+to\s+reduce[:\s]+([^\n]+)",
    ]
    for pattern in reduce_patterns:
        matches = re.findall(pattern, text_lower)
        for match in matches:
            items = [item.strip() for item in re.split(r'[,;]', match) if item.strip()]
            result["reduce_list"].extend(items)

    # Common recommendation patterns
    rec_patterns = [
        r"(?:recommend|increase|include|add)[:\s]+([^\n]+)",
        r"(?:beneficial|suggested)\s+foods?[:\s]+([^\n]+)",
    ]
    for pattern in rec_patterns:
        matches = re.findall(pattern, text_lower)
        for match in matches:
            items = [item.strip() for item in re.split(r'[,;]', match) if item.strip()]
            result["recommended_list"].extend(items)

    # Deduplicate
    result["avoid_list"] = list(set(result["avoid_list"]))
    result["reduce_list"] = list(set(result["reduce_list"]))
    result["recommended_list"] = list(set(result["recommended_list"]))

    return result


def _chunk_report_text(text: str, max_chunk_size: int = 500, overlap: int = 50) -> list[dict]:
    """
    Split report text into overlapping chunks for RAG embedding.
    Tries to split at paragraph boundaries first, then sentence boundaries.
    """
    chunks = []

    # Split by double newlines (paragraphs) first
    paragraphs = re.split(r'\n\s*\n', text)

    current_chunk = ""
    chunk_index = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current_chunk) + len(para) < max_chunk_size:
            current_chunk += ("\n\n" + para if current_chunk else para)
        else:
            if current_chunk:
                chunks.append({
                    "chunk_index": chunk_index,
                    "text": current_chunk,
                    "char_count": len(current_chunk)
                })
                chunk_index += 1

                # Keep overlap from end of current chunk
                if overlap > 0:
                    current_chunk = current_chunk[-overlap:] + "\n\n" + para
                else:
                    current_chunk = para
            else:
                # Single paragraph exceeds max size, split at sentence
                sentences = re.split(r'(?<=[.!?])\s+', para)
                for sent in sentences:
                    if len(current_chunk) + len(sent) < max_chunk_size:
                        current_chunk += (" " + sent if current_chunk else sent)
                    else:
                        if current_chunk:
                            chunks.append({
                                "chunk_index": chunk_index,
                                "text": current_chunk,
                                "char_count": len(current_chunk)
                            })
                            chunk_index += 1
                        current_chunk = sent

    # Don't forget the last chunk
    if current_chunk.strip():
        chunks.append({
            "chunk_index": chunk_index,
            "text": current_chunk,
            "char_count": len(current_chunk)
        })

    return chunks


def _update_patient_profile(kit_id: str, parsed_data: dict, chunks: list):
    """Update DynamoDB patient profile with extracted data."""
    table = dynamodb.Table(PATIENT_TABLE)
    now = datetime.utcnow().isoformat() + "Z"

    table.update_item(
        Key={"kit_id": kit_id},
        UpdateExpression="""
            SET extraction_status = :status,
                updated_at = :now,
                avoid_list = :avoid,
                reduce_list = :reduce,
                recommended_list = :recommend,
                bacterial_history = :bacteria,
                allergies = :allergies,
                medical_conditions = :conditions,
                dietary_notes = :notes,
                report_chunks = :chunks
        """,
        ExpressionAttributeValues={
            ":status": "COMPLETED",
            ":now": now,
            ":avoid": parsed_data.get("avoid_list", []),
            ":reduce": parsed_data.get("reduce_list", []),
            ":recommend": parsed_data.get("recommended_list", []),
            ":bacteria": parsed_data.get("bacterial_history", []),
            ":allergies": parsed_data.get("allergies", []),
            ":conditions": parsed_data.get("medical_conditions", []),
            ":notes": parsed_data.get("dietary_notes", ""),
            ":chunks": chunks
        }
    )
    logger.info(f"Updated patient profile for kit_id={kit_id}")


def _update_status(kit_id: str, status: str, error: str = None):
    """Quick status update helper."""
    table = dynamodb.Table(PATIENT_TABLE)
    update_expr = "SET extraction_status = :status, updated_at = :now"
    expr_values = {
        ":status": status,
        ":now": datetime.utcnow().isoformat() + "Z"
    }
    if error:
        update_expr += ", extraction_error = :error"
        expr_values[":error"] = error

    table.update_item(
        Key={"kit_id": kit_id},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_values
    )


def _trigger_embedding_lambda(kit_id: str):
    """Invoke the embedding generation Lambda asynchronously."""
    try:
        lambda_client.invoke(
            FunctionName=EMBEDDING_LAMBDA,
            InvocationType="Event",  # Async invocation
            Payload=json.dumps({"kit_id": kit_id})
        )
        logger.info(f"Triggered embedding generation for kit_id={kit_id}")
    except Exception as e:
        logger.error(f"Failed to trigger embedding Lambda: {e}")
