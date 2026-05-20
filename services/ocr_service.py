"""
ocr_service.py — Blood/Biochemistry Report OCR using Google Gemini Vision API
Extracts structured lab values from uploaded report images and maps them to
MonthlyRecord database fields, exactly as if entered manually.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Field mapping: all MonthlyRecord lab fields with their common aliases.
# The LLM is given this full list to guide extraction.
# ─────────────────────────────────────────────────────────────────────────────
FIELD_MAP: dict[str, dict[str, Any]] = {
    # Anemia
    "hb": {
        "label": "Hemoglobin",
        "aliases": ["Hb", "Haemoglobin", "Hemoglobin", "HGB", "Hgb"],
        "unit": "g/dL",
        "type": "float",
    },
    # Iron Panel
    "serum_ferritin": {
        "label": "Serum Ferritin",
        "aliases": ["Ferritin", "S. Ferritin", "Serum Ferritin"],
        "unit": "ng/mL",
        "type": "float",
    },
    "tsat": {
        "label": "Transferrin Saturation",
        "aliases": ["TSAT", "Transferrin Saturation", "T.Sat", "% Saturation"],
        "unit": "%",
        "type": "float",
    },
    "serum_iron": {
        "label": "Serum Iron",
        "aliases": ["S. Iron", "Serum Iron", "Iron"],
        "unit": "µg/dL",
        "type": "float",
    },
    "tibc": {
        "label": "TIBC",
        "aliases": ["TIBC", "Total Iron Binding Capacity"],
        "unit": "µg/dL",
        "type": "float",
    },
    # Mineral Metabolism
    "calcium": {
        "label": "Serum Calcium",
        "aliases": ["Calcium", "S. Calcium", "Ca", "Total Calcium", "Corrected Calcium"],
        "unit": "mg/dL",
        "type": "float",
    },
    "phosphorus": {
        "label": "Serum Phosphorus",
        "aliases": ["Phosphorus", "Phosphate", "S. Phosphate", "S. Phosphorus", "PO4", "Inorganic Phosphate"],
        "unit": "mg/dL",
        "type": "float",
    },
    "alkaline_phosphate": {
        "label": "Alkaline Phosphatase",
        "aliases": ["ALP", "Alkaline Phosphatase", "Alk Phos", "Alkaline Phosphate"],
        "unit": "U/L",
        "type": "float",
    },
    "ipth": {
        "label": "Intact PTH",
        "aliases": ["iPTH", "PTH", "Parathyroid Hormone", "Intact Parathyroid Hormone", "Intact PTH"],
        "unit": "pg/mL",
        "type": "float",
    },
    "vit_d": {
        "label": "Vitamin D (25-OH)",
        "aliases": ["Vit D", "25-OH Vitamin D", "25-OH Vit D", "25(OH)D", "Vitamin D", "Calcidiol"],
        "unit": "ng/mL",
        "type": "float",
    },
    # Electrolytes & Acid-Base
    "serum_sodium": {
        "label": "Serum Sodium",
        "aliases": ["Sodium", "Na", "S. Sodium", "Serum Sodium"],
        "unit": "mEq/L",
        "type": "float",
    },
    "serum_potassium": {
        "label": "Serum Potassium",
        "aliases": ["Potassium", "K", "S. Potassium", "Serum Potassium", "Serum K"],
        "unit": "mEq/L",
        "type": "float",
    },
    "serum_bicarbonate": {
        "label": "Serum Bicarbonate",
        "aliases": ["Bicarbonate", "HCO3", "Serum Bicarbonate", "Total CO2", "TCO2"],
        "unit": "mEq/L",
        "type": "float",
    },
    "serum_uric_acid": {
        "label": "Serum Uric Acid",
        "aliases": ["Uric Acid", "S. Uric Acid", "Urate"],
        "unit": "mg/dL",
        "type": "float",
    },
    # Dialysis Adequacy
    "pre_dialysis_urea": {
        "label": "Pre-Dialysis Urea / BUN",
        "aliases": ["Pre HD Urea", "Pre-HD Urea", "Pre Urea", "Blood Urea", "Urea", "BUN", "Blood Urea Nitrogen"],
        "unit": "mg/dL",
        "type": "float",
    },
    "post_dialysis_urea": {
        "label": "Post-Dialysis Urea",
        "aliases": ["Post HD Urea", "Post-HD Urea", "Post Urea"],
        "unit": "mg/dL",
        "type": "float",
    },
    "serum_creatinine": {
        "label": "Serum Creatinine",
        "aliases": ["Creatinine", "S. Creatinine", "Serum Creatinine", "Cr"],
        "unit": "mg/dL",
        "type": "float",
    },
    "urr": {
        "label": "Urea Reduction Ratio",
        "aliases": ["URR", "Urea Reduction Ratio"],
        "unit": "%",
        "type": "float",
    },
    "single_pool_ktv": {
        "label": "Kt/V (single pool)",
        "aliases": ["Kt/V", "spKt/V", "Single Pool Kt/V", "KTV"],
        "unit": "",
        "type": "float",
    },
    "equilibrated_ktv": {
        "label": "Equilibrated Kt/V",
        "aliases": ["eKt/V", "Equilibrated Kt/V", "eKTV"],
        "unit": "",
        "type": "float",
    },
    # Nutrition
    "albumin": {
        "label": "Serum Albumin",
        "aliases": ["Albumin", "S. Albumin", "Serum Albumin", "Alb"],
        "unit": "g/dL",
        "type": "float",
    },
    "prealbumin": {
        "label": "Prealbumin",
        "aliases": ["Prealbumin", "Pre-Albumin", "Transthyretin", "TTR"],
        "unit": "mg/dL",
        "type": "float",
    },
    # Lipids
    "total_cholesterol": {
        "label": "Total Cholesterol",
        "aliases": ["Cholesterol", "Total Cholesterol", "T. Chol", "TC"],
        "unit": "mg/dL",
        "type": "float",
    },
    "ldl_cholesterol": {
        "label": "LDL Cholesterol",
        "aliases": ["LDL", "LDL-C", "LDL Cholesterol", "Low Density Lipoprotein"],
        "unit": "mg/dL",
        "type": "float",
    },
    # Haematology
    "wbc_count": {
        "label": "WBC / TLC",
        "aliases": ["WBC", "TLC", "Total Leucocyte Count", "Total WBC", "White Blood Cell Count", "WBC Count"],
        "unit": "×10³/µL",
        "type": "float",
    },
    "neutrophil_count": {
        "label": "Neutrophil Count",
        "aliases": ["Neutrophils", "ANC", "Absolute Neutrophil Count", "Neutrophil Count", "Polymorphs"],
        "unit": "×10³/µL",
        "type": "float",
    },
    "platelet_count": {
        "label": "Platelet Count",
        "aliases": ["Platelets", "PLT", "Platelet Count", "Thrombocytes"],
        "unit": "×10³/µL",
        "type": "float",
    },
    "hba1c": {
        "label": "HbA1c",
        "aliases": ["HbA1c", "HBA1C", "Glycated Haemoglobin", "Glycosylated Hemoglobin", "A1c"],
        "unit": "%",
        "type": "float",
    },
    # Liver Function
    "ast": {
        "label": "AST (SGOT)",
        "aliases": ["AST", "SGOT", "Aspartate Aminotransferase"],
        "unit": "U/L",
        "type": "float",
    },
    "alt": {
        "label": "ALT (SGPT)",
        "aliases": ["ALT", "SGPT", "Alanine Aminotransferase"],
        "unit": "U/L",
        "type": "float",
    },
    # Inflammatory
    "crp": {
        "label": "C-Reactive Protein",
        "aliases": ["CRP", "C-Reactive Protein", "hs-CRP", "hsCRP"],
        "unit": "mg/L",
        "type": "float",
    },
    # Cardiac
    "nt_probnp": {
        "label": "NT-proBNP",
        "aliases": ["NT-proBNP", "NT proBNP", "proBNP", "BNP"],
        "unit": "pg/mL",
        "type": "float",
    },
    # Vitals
    "bp_sys": {
        "label": "Systolic Blood Pressure",
        "aliases": ["SBP", "Systolic BP", "Systolic", "BP Systolic"],
        "unit": "mmHg",
        "type": "float",
    },
    "bp_dia": {
        "label": "Diastolic Blood Pressure",
        "aliases": ["DBP", "Diastolic BP", "Diastolic", "BP Diastolic"],
        "unit": "mmHg",
        "type": "float",
    },
    # Fluid
    "idwg": {
        "label": "Interdialytic Weight Gain",
        "aliases": ["IDWG", "Interdialytic Weight Gain", "Weight Gain"],
        "unit": "kg",
        "type": "float",
    },
    "residual_urine_output": {
        "label": "Residual Urine Output",
        "aliases": ["Residual Urine", "RUO", "Urine Output", "Residual Diuresis"],
        "unit": "mL/day",
        "type": "float",
    },
    "npcr": {
        "label": "nPCR",
        "aliases": ["nPCR", "Normalized Protein Catabolic Rate", "PCR"],
        "unit": "g/kg/day",
        "type": "float",
    },
}


def _build_extraction_prompt() -> str:
    """Build the structured prompt for Gemini Vision with full field definitions."""
    field_lines = []
    for db_field, info in FIELD_MAP.items():
        aliases = ", ".join(info["aliases"])
        unit = f" ({info['unit']})" if info["unit"] else ""
        field_lines.append(f'  - "{db_field}": {info["label"]}{unit} — aliases: {aliases}')

    fields_block = "\n".join(field_lines)

    return f"""You are a medical lab report OCR expert. Your job is to extract specific lab values from the provided blood/biochemistry report image.

TASK:
Carefully read all text in the image and extract the numeric values for the following fields. These are lab result parameters from a hemodialysis patient's blood report or biochemistry report.

FIELDS TO EXTRACT:
{fields_block}

EXTRACTION RULES:
1. Extract ONLY numeric values (integers or decimals). Strip units from values.
2. If a field is not found in the report, omit it from the output entirely — do NOT include null values.
3. If a value seems clearly erroneous or unreadable, omit it.
4. For blood pressure given as "120/80", extract 120 as bp_sys and 80 as bp_dia.
5. For WBC/TLC reported in thousands (e.g. 7.2 x10³/µL), keep as 7.2. If given in millions, convert to thousands.
6. Pay attention to units — if creatinine is in µmol/L, convert to mg/dL (divide by 88.4).
7. For urea: if given in mmol/L, convert to mg/dL (multiply by 2.8).
8. Identify whether urea is "pre-dialysis" or "post-dialysis" from context — map to pre_dialysis_urea or post_dialysis_urea accordingly. If just "Urea" with no context, use pre_dialysis_urea.
9. Rate your confidence for each field as: "high" (clearly readable), "medium" (somewhat readable), or "low" (inferred/uncertain).

OUTPUT FORMAT (strict JSON only, no markdown, no explanation):
{{
  "extracted_fields": {{
    "hb": 8.2,
    "serum_creatinine": 6.1,
    "serum_potassium": 4.8
  }},
  "confidence": {{
    "hb": "high",
    "serum_creatinine": "high",
    "serum_potassium": "medium"
  }},
  "report_date": "DD/MM/YYYY or empty string if not found",
  "patient_name_on_report": "name as printed on report, or empty string",
  "report_type": "biochemistry/haematology/lipid/comprehensive/unknown"
}}

IMPORTANT: Return ONLY valid JSON. Do not include any text before or after the JSON object."""


def extract_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict[str, Any]:
    """
    Send image to Gemini Vision and extract lab values.

    Args:
        image_bytes: Raw image bytes (JPEG, PNG, etc.)
        mime_type: MIME type of the image

    Returns:
        dict with keys: extracted_fields, confidence, report_date,
                        patient_name_on_report, report_type, model, error (if any)
    """
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        logger.error("GEMINI_API_KEY not set in environment")
        return {
            "extracted_fields": {},
            "confidence": {},
            "error": "GEMINI_API_KEY not configured. Please add it to your .env file.",
            "model": "none",
        }

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        prompt = _build_extraction_prompt()

        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mime_type,
                ),
                prompt,
            ],
        )

        raw_text = response.text.strip()
        logger.info("Gemini OCR raw response length: %d chars", len(raw_text))

        # Extract JSON from response (handle cases where model wraps in markdown)
        json_match = re.search(r"\{[\s\S]*\}", raw_text)
        if not json_match:
            logger.error("No JSON found in Gemini response: %s", raw_text[:500])
            return {
                "extracted_fields": {},
                "confidence": {},
                "error": "Could not parse AI response. Please try again with a clearer image.",
                "model": "gemini-1.5-flash",
                "raw_text": raw_text[:1000],
            }

        result = json.loads(json_match.group())

        # Validate and sanitize extracted_fields — only keep known fields
        raw_fields = result.get("extracted_fields", {})
        clean_fields: dict[str, float] = {}
        clean_confidence: dict[str, str] = {}
        confidence_map = result.get("confidence", {})

        for field, value in raw_fields.items():
            if field not in FIELD_MAP:
                continue
            try:
                numeric = float(value)
                if numeric < 0 or numeric > 100000:
                    logger.warning("Suspicious value for %s: %s — skipping", field, value)
                    continue
                clean_fields[field] = round(numeric, 2)
                clean_confidence[field] = confidence_map.get(field, "medium")
            except (TypeError, ValueError):
                logger.warning("Non-numeric value for %s: %s", field, value)

        return {
            "extracted_fields": clean_fields,
            "confidence": clean_confidence,
            "report_date": result.get("report_date", ""),
            "patient_name_on_report": result.get("patient_name_on_report", ""),
            "report_type": result.get("report_type", "unknown"),
            "fields_found": len(clean_fields),
            "model": "gemini-1.5-flash",
        }

    except Exception as exc:
        logger.error("OCR extraction failed: %s", exc, exc_info=True)
        return {
            "extracted_fields": {},
            "confidence": {},
            "error": f"OCR processing failed: {str(exc)}",
            "model": "gemini-1.5-flash",
        }


def get_field_labels() -> dict[str, str]:
    """Return a mapping of db_field -> human label for frontend display."""
    return {k: v["label"] for k, v in FIELD_MAP.items()}


def get_field_units() -> dict[str, str]:
    """Return a mapping of db_field -> unit for frontend display."""
    return {k: v["unit"] for k, v in FIELD_MAP.items()}
