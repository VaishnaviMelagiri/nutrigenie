"""
Lambda: upload_report (S3 Event Trigger)
Automatically converts PDF reports uploaded to the S3 `reports/` folder
into structured JSON patient profiles in the `patients/` folder.
If a JSON file is uploaded to `reports/`, it is simply copied to `patients/`.
"""

import json
import io
import os
import logging
import boto3

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")


def lambda_handler(event, context):
    """Triggered by S3 PutObject events on the reports/ prefix."""
    try:
        record = event["Records"][0]
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]  # e.g. reports/IOM_KIT003.pdf

        logger.info(f"Processing uploaded file: s3://{bucket}/{key}")

        # Extract kit_id from filename  (reports/IOM_KIT003.pdf -> IOM_KIT003)
        filename = os.path.basename(key)
        kit_id = os.path.splitext(filename)[0]
        target_key = f"patients/{kit_id}.json"

        # Download the file
        response = s3.get_object(Bucket=bucket, Key=key)
        file_bytes = response["Body"].read()

        # ── JSON file: just copy to patients/ ──
        if filename.lower().endswith(".json") or file_bytes.lstrip()[:1] == b"{":
            try:
                json_data = json.loads(file_bytes.decode("utf-8"))
                s3.put_object(
                    Bucket=bucket, Key=target_key,
                    Body=json.dumps(json_data), ContentType="application/json",
                )
                logger.info(f"JSON copied to {target_key}")
                return {"status": "ok", "action": "json_copy", "kit_id": kit_id}
            except Exception as e:
                logger.error(f"Invalid JSON: {e}")
                return {"status": "error", "message": str(e)}

        # ── PDF file: extract text + Bedrock structuring ──
        if not file_bytes[:5] == b"%PDF-":
            logger.error("File is neither valid PDF nor JSON")
            return {"status": "error", "message": "Unsupported file format"}

        if not PdfReader:
            logger.error("pypdf not available")
            return {"status": "error", "message": "pypdf library not loaded"}

        reader = PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in reader.pages[:10]:
            t = page.extract_text()
            if t:
                text += t + "\n"

        if not text.strip():
            logger.error("No text extracted from PDF")
            return {"status": "error", "message": "Empty PDF"}

        # Call Bedrock Nova Micro to structure the text
        json_data = _extract_json_with_bedrock(text, kit_id)

        s3.put_object(
            Bucket=bucket, Key=target_key,
            Body=json.dumps(json_data), ContentType="application/json",
        )
        logger.info(f"PDF parsed and saved to {target_key}")
        return {"status": "ok", "action": "pdf_parsed", "kit_id": kit_id}

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


def _extract_json_with_bedrock(text: str, kit_id: str) -> dict:
    """Uses Amazon Nova Micro to convert raw clinical text into patient JSON."""

    prompt = f"""Convert this clinical microbiome report text into a JSON object.

REQUIRED SCHEMA:
{{
  "kit_id": "{kit_id}",
  "metadata": {{
    "Age": 30, "Sex": "Male", "BMI": "22.5",
    "Diet type": "Vegetarian", "City": "Bangalore",
    "Prebiotics - Gut affectors": "Flax seeds, oats..."
  }},
  "allergens": [{{"name": "...", "intensity": "High"}}],
  "disease_risk": [{{"name": "IBS", "score": 85, "match_level": "High"}}],
  "bacteria_to_increase": [{{"name": "...", "description": "..."}}],
  "bacteria_to_decrease": [{{"name": "...", "description": "..."}}]
}}

Return ONLY raw JSON. No markdown, no explanations.
If data is missing, use empty arrays or "Not Provided".

REPORT TEXT:
{text[:30000]}"""

    payload = {
        "system": [{"text": "You are a clinical data extractor. Output ONLY raw JSON."}],
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": 2000, "temperature": 0.1, "topP": 0.9},
    }

    try:
        resp = bedrock.invoke_model(
            modelId="amazon.nova-micro-v1:0",
            contentType="application/json",
            accept="application/json",
            body=json.dumps(payload),
        )
        body = json.loads(resp["body"].read())
        output = body.get("output", {}).get("message", {}).get("content", [{}])[0].get("text", "")

        # Strip markdown fences if Nova adds them
        output = output.strip()
        if output.startswith("```json"):
            output = output[7:]
        if output.startswith("```"):
            output = output[3:]
        if output.endswith("```"):
            output = output[:-3]

        return json.loads(output.strip())
    except Exception as e:
        logger.error(f"Bedrock extraction failed: {e}")
        return {
            "kit_id": kit_id,
            "metadata": {"Diet type": "Vegetarian"},
            "allergens": [],
            "extraction_error": str(e),
        }
