import json
import os
import io
import base64
import logging
from datetime import datetime
import boto3

# We will need pypdf which we'll install in a Lambda layer
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── AWS Clients ──
s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

REPORTS_BUCKET = os.environ.get("REPORTS_BUCKET", "nutrigenie-data")

def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body", "{}")) if isinstance(event.get("body"), str) else event.get("body", event)

        kit_id = body.get("kit_id", "").strip()
        file_name = body.get("file_name", "report.pdf")
        file_content_b64 = body.get("file_content_base64", "")

        if not kit_id or not file_content_b64:
            return _response(400, {"error": "kit_id and file_content_base64 are required"})

        # Sanitize kit_id
        kit_id = kit_id.replace("/", "_").replace("\\", "_")
        file_bytes = base64.b64decode(file_content_b64)

        target_s3_key = f"patients/{kit_id}.json"

        # Check if it's already a JSON file
        if file_name.lower().endswith(".json") or file_bytes.startswith(b"{"):
            try:
                # Validate it's proper JSON
                json_data = json.loads(file_bytes.decode('utf-8'))
                s3.put_object(
                    Bucket=REPORTS_BUCKET,
                    Key=target_s3_key,
                    Body=json.dumps(json_data),
                    ContentType="application/json"
                )
                return _response(200, {"message": "JSON uploaded successfully", "kit_id": kit_id})
            except Exception as e:
                return _response(400, {"error": f"Invalid JSON provided: {str(e)}"})

        # Otherwise, assume it's a PDF.
        if not file_bytes[:5] == b"%PDF-":
            return _response(400, {"error": "File does not appear to be a valid PDF or JSON"})

        # 1. Extract text using pypdf
        if not PdfReader:
            return _response(500, {"error": "pypdf library not loaded in environment"})
        
        pdf_file = io.BytesIO(file_bytes)
        reader = PdfReader(pdf_file)
        
        extracted_text = ""
        # Only read first few pages to save context window and focus on key data
        for page in reader.pages[:10]:
            text = page.extract_text()
            if text:
                extracted_text += text + "\n"

        if not extracted_text.strip():
            return _response(400, {"error": "Could not extract text from the provided PDF."})

        # 2. Use Bedrock Nova Micro to convert this raw clinical text into our clean JSON schema
        json_data = _extract_to_json_with_bedrock(extracted_text, kit_id)

        # 3. Save directly to S3 exactly as if we uploaded a JSON
        s3.put_object(
            Bucket=REPORTS_BUCKET,
            Key=target_s3_key,
            Body=json.dumps(json_data),
            ContentType="application/json"
        )

        return _response(200, {
            "message": "PDF parsed and standardized JSON uploaded successfully",
            "kit_id": kit_id
        })

    except Exception as e:
        logger.error(f"Upload error: {str(e)}", exc_info=True)
        return _response(500, {"error": f"Internal server error: {str(e)}"})

def _extract_to_json_with_bedrock(text: str, kit_id: str) -> dict:
    """Uses Nova Micro to parse raw clinical PDF text into the standardized patient JSON format."""
    
    prompt = f"""You are a clinical data extraction engine. 
Convert the following unstructured text from a microbiome gut test report into a strict JSON object.

REQUIRED SCHEMA (MUST output valid JSON matching this structure, infer where needed):
{{
  "kit_id": "{kit_id}",
  "metadata": {{
    "Age": 30,
    "Sex": "Male/Female",
    "BMI": "22.5",
    "Diet type": "Vegetarian",
    "City": "...",
    "Prebiotics - Gut affectors": "Flax seeds, oats..."
  }},
  "allergens": [{{"name": "Peanuts", "intensity": "High"}}, ...],
  "disease_risk": [{{"name": "IBS", "score": 85, "match_level": "High"}}, ...],
  "bacterial_abundance": [{{"name": "Bifidobacterium", "abundance_percentage": 2.5}}, ...],
  "bacteria_to_increase": [{{"name": "Akkermansia", "description": "..."}}],
  "bacteria_to_decrease": [{{"name": "Blautia", "description": "..."}}]
}}

IMPORTANT: 
- Return ONLY JSON. Do not include markdown code blocks ```json ... ```. Just the raw `{...}`.
- If data is missing for a field, provide an empty array `[]` or `"Not Provided"`.

RAW REPORT TEXT:
{text[:40000]} # Limit text to roughly 10k tokens (Nova micro handles 128k, but for speed)
"""

    payload = {
        "system": [{"text": "You are a clinical data extractor. Output ONLY raw JSON."}],
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {
            "maxTokens": 2000,
            "temperature": 0.1,
            "topP": 0.9
        }
    }
    
    try:
        response = bedrock.invoke_model(
            modelId="amazon.nova-micro-v1:0",
            contentType="application/json",
            accept="application/json",
            body=json.dumps(payload)
        )
        response_body = json.loads(response.get('body').read())
        llm_output = response_body.get('output', {}).get('message', {}).get('content', [{}])[0].get('text', '')
        
        # Clean up in case Nova returns markdown blocks anyway
        llm_output = llm_output.strip()
        if llm_output.startswith("```json"):
            llm_output = llm_output[7:]
        if llm_output.startswith("```"):
            llm_output = llm_output[3:]
        if llm_output.endswith("```"):
            llm_output = llm_output[:-3]
            
        return json.loads(llm_output.strip())
    except Exception as e:
        logger.error(f"Bedrock extraction failed: {str(e)}")
        # Return fallback bare-minimum JSON so the app doesn't fatally crash
        return {
            "kit_id": kit_id,
            "metadata": {"Diet type": "Vegetarian"},
            "allergens": [],
            "error_during_extraction": str(e)
        }

def _response(status_code: int, body: dict) -> dict:
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
