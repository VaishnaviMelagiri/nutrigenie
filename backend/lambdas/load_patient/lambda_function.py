"""
Lambda: load_patient
Reads iom_data.json from S3, parses the patient profile for a given Kit ID.
Returns structured patient data including dietary constraints, bacterial info, and gut markers.

API: GET /patient/{kit_id}
"""

import json
import os
import logging

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")
DATA_BUCKET = os.environ.get("DATA_BUCKET", "nutrigenie-data")


def lambda_handler(event, context):
    try:
        kit_id = event.get("pathParameters", {}).get("kit_id", "").strip()
        if not kit_id:
            return _response(400, {"error": "kit_id is required"})

        logger.info(f"Loading patient data for kit_id: {kit_id}")

        # Read iom_data.json from S3
        try:
            obj = s3.get_object(
                Bucket=DATA_BUCKET,
                Key=f"patients/{kit_id}.json"
            )
            raw_data = json.loads(obj["Body"].read().decode("utf-8"))
        except s3.exceptions.NoSuchKey:
            return _response(404, {"error": f"No patient data found for kit_id: {kit_id}"})
        except Exception as e:
            logger.error(f"S3 read error: {e}")
            return _response(500, {"error": "Failed to read patient data"})

        # Parse into structured profile
        profile = _parse_iom_data(raw_data, kit_id)

        return _response(200, profile)

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return _response(500, {"error": str(e)})


def _parse_iom_data(data: dict, kit_id: str) -> dict:
    """Parse iom_data.json into a clean patient profile."""
    metadata = data.get("metadata", {})
    tokens = data.get("tokens", {})

    # ── Basic Info ──
    profile = {
        "kit_id": kit_id,
        "name": metadata.get("Name", "Unknown"),
        "gender": metadata.get("Gender", ""),
        "age": metadata.get("Age", ""),
        "height_cm": metadata.get("Height", ""),
        "weight_kg": metadata.get("Weight", ""),
        "bmi": metadata.get("BMI", ""),
        "location": metadata.get("Location", ""),
        "diet_type": metadata.get("Which best describes your usual diet", "Veg"),
    }

    # ── IBS Info ──
    profile["ibs_info"] = {
        "subtype": metadata.get("Do you know which subtype of IBS you have?", ""),
        "severity_score": metadata.get("IBS Severity score", ""),
        "severity_level": metadata.get("IBS Severity Level", ""),
        "abdominal_pain": metadata.get("How severe is your abdominal pain?", ""),
        "bloating": metadata.get("How severe is your abdominal Distension/Bloating?", ""),
    }

    # ── Food Allergies / Avoid List ──
    allergies_raw = metadata.get(
        "Do you have food allergies or intolerances?",
        metadata.get("Do you have any food allergies or intolerances?", "")
    )
    if allergies_raw and allergies_raw.lower() not in ["no", "none", ""]:
        profile["avoid_list"] = [
            item.strip() for item in allergies_raw.replace("(legumes)", "").split(",")
            if item.strip()
        ]
    else:
        profile["avoid_list"] = []

    # ── Prebiotics / Gut Affectors ──
    profile["prebiotics"] = metadata.get("Prebiotics - Gut affectors", "")

    # ── Bacterial Data ──
    bacteria_increase = []
    bacteria_decrease = []
    try:
        bacteria_raw = json.loads(tokens.get("#TID009", "[]"))
        for b in bacteria_raw:
            if b.get("Category") != "Bacteria":
                continue
            entry = {
                "name": b.get("Token_name", ""),
                "initial": b.get("Initial_Abundance", 0),
                "target": b.get("Optimised_abundance", 0),
                "description": b.get("Description", ""),
            }
            if b.get("Type") == "increase":
                bacteria_increase.append(entry)
            elif b.get("Type") == "decrease":
                bacteria_decrease.append(entry)
    except (json.JSONDecodeError, TypeError):
        pass

    profile["bacteria_to_increase"] = bacteria_increase
    profile["bacteria_to_decrease"] = bacteria_decrease

    # ── Pathogen Data ──
    try:
        pathogens = json.loads(tokens.get("#TIDP01", "[]"))
        profile["pathogens"] = [
            {"name": p["bacteria_name"], "abundance": p["abundance"], "range": p["range"]}
            for p in pathogens
        ]
    except (json.JSONDecodeError, TypeError):
        profile["pathogens"] = []

    # ── Gut Health Markers ──
    markers = []
    marker_keys = [
        ("#TID087", "#TID088", "#TID089", "#TID090"),  # Gut Diversity
        ("#TID091", "#TID092", "#TID093", "#TID094"),  # Insulin Resistance
        ("#TID095", "#TID096", "#TID097", "#TID098"),  # Probiotic Bacteria
        ("#TID099", "#TID100", "#TID101", "#TID102"),  # Lactic Acid
        ("#TID121", "#TID122", "#TID123", "#TID124"),  # Dietary Fibre
        ("#TID125", "#TID126", "#TID127", "#TID128"),  # Immunity
        ("#TID129", "#TID130", "#TID131", "#TID132"),  # Energy Producers
        ("#TID133", "#TID134", "#TID135", "#TID136"),  # Neg Weight
        ("#TID137", "#TID138", "#TID139", "#TID140"),  # Protein Metabolisers
        ("#TID141", "#TID142", "#TID143", "#TID144"),  # Carb Fermenters
        ("#TID145", "#TID146", "#TID147", "#TID148"),  # Heart Health
        ("#TID149", "#TID150", "#TID151", "#TID152"),  # F/B Ratio
    ]
    for name_key, status_key, level_key, desc_key in marker_keys:
        name = tokens.get(name_key, "")
        if name:
            markers.append({
                "name": name,
                "status": tokens.get(status_key, ""),
                "level": tokens.get(level_key, ""),
                "description": tokens.get(desc_key, ""),
            })
    profile["gut_markers"] = markers

    # ── Symptoms ──
    symptom_fields = [
        "Nausea", "Migraine", "Acid Reflux", "Flatulence/Bloating",
        "Heartburn", "Vomiting", "Stress", "Anxiety", "Depression", "Disturbed Sleep"
    ]
    profile["symptoms"] = {
        field: metadata.get(field, "Not Severe") for field in symptom_fields
    }

    return profile


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        },
        "body": json.dumps(body),
    }
