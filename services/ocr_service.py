"""
ocr_service.py — Blood/Biochemistry Report OCR using Google Gemini Vision API
Extracts structured lab values from uploaded report images and maps them to
MonthlyRecord database fields, exactly as if entered manually.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ─── Module-level singletons ──────────────────────────────────────────────────
# API key read once at import time; client created once and reused across requests.
_GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
_gemini_client: genai.Client | None = (
    genai.Client(api_key=_GEMINI_API_KEY, http_options={"timeout": 30})
    if _GEMINI_API_KEY else None
)

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
    "hct": {
        "label": "Hematocrit / PCV",
        "aliases": ["HCT", "Hematocrit", "PCV", "Packed Cell Volume"],
        "unit": "%",
        "type": "float",
    },
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

    # Medications
    "epo_mircera_dose": {
        "label": "ESA / Mircera Dose",
        "aliases": ["ESA", "Erythropoietin", "Mircera", "Epoetin", "Darbepoetin", "PEG EPO", "Pegylated Erythropoietin"],
        "unit": "",
        "type": "string",
    },
    "desidustat_dose": {
        "label": "Desidustat Dose",
        "aliases": ["Desidustat", "Oxemia"],
        "unit": "",
        "type": "string",
    },
    "iv_iron_product": {
        "label": "IV Iron Product",
        "aliases": ["IV Iron", "Iron Sucrose", "Ferric Carboxymaltose", "FCM"],
        "unit": "",
        "type": "string",
    },
    "iv_iron_dose": {
        "label": "IV Iron Dose",
        "aliases": ["IV Iron Dose", "FCM Dose", "Iron Dose"],
        "unit": "mg",
        "type": "float",
    },
}


def _build_extraction_prompt() -> str:
    field_lines = []
    for db_field, info in FIELD_MAP.items():
        aliases = ", ".join(info["aliases"])
        unit = f" ({info['unit']})" if info["unit"] else ""
        field_lines.append(f'  - "{db_field}": {info["label"]}{unit} — aliases: {aliases}')

    fields_block = "\n".join(field_lines)
    valid_keys = ", ".join(f'"{k}"' for k in FIELD_MAP.keys())

    return f"""You are a clinical lab report OCR assistant. Your ONLY job is to extract specific numeric lab values for a hemodialysis patient from the provided report image.

TASK:
Read all text in the image. Extract values for the fields listed below. Ignore everything else — patient name, doctor notes, reference ranges, diagnoses, addresses, logos, etc. For medication fields, extract the full string (e.g. 'Mircera 75mcg').

ALLOWED OUTPUT KEYS — these are the ONLY valid keys you may include in "extracted_fields":
{valid_keys}

FIELD DEFINITIONS (label and common aliases to help you match the report):
{fields_block}

EXTRACTION RULES:
1. Extract numeric values (integers or decimals) for lab tests and strip units. For medications, extract the string value including the dose/frequency.
2. If a field is not present in the report, do NOT include it in the output — omit it entirely.
3. If a value is unreadable or clearly erroneous, omit it.
4. For blood pressure written as "120/80": extract 120 → bp_sys, 80 → bp_dia.
5. For WBC/TLC in thousands (e.g. 7.2 ×10³/µL): keep as 7.2. If given as millions, divide by 1000.
6. Units conversion: if creatinine is in µmol/L → divide by 88.4 to get mg/dL. If urea is in mmol/L → multiply by 2.8 to get mg/dL.
7. For urea: if labelled "pre-dialysis" → pre_dialysis_urea; "post-dialysis" → post_dialysis_urea. If ambiguous, use pre_dialysis_urea.
8. Rate your confidence for each field: "high" (clearly readable), "medium" (partially readable), "low" (uncertain/inferred).

CRITICAL — STRICT ALLOWLIST:
- The "extracted_fields" object MUST contain ONLY keys from the allowed list above.
- DO NOT invent new keys (e.g. do not add "glucose", "troponin", "sodium_potassium_ratio", "egfr", or any other name not in the allowed list).
- Any value you cannot map to an allowed key must be silently discarded.

OUTPUT FORMAT: Provide the data matching the requested JSON schema."""


# ─── Module-level cached constants (built once at import time) ────────────────
_EXTRACTION_PROMPT: str = _build_extraction_prompt()
_FIELD_LABELS: dict[str, str] = {k: v["label"] for k, v in FIELD_MAP.items()}
_FIELD_UNITS: dict[str, str] = {k: v["unit"] for k, v in FIELD_MAP.items()}


class OCRResponse(BaseModel):
    extracted_fields: dict[str, Any] = Field(
        default_factory=dict,
        description="Extracted lab values and medications. Keys must strictly match the allowed list. Values can be float or string."
    )
    confidence: dict[str, str] = Field(
        default_factory=dict,
        description="Confidence rating for each extracted field (high/medium/low)."
    )
    report_date: str = Field(default="", description="Report date as DD/MM/YYYY or empty string")
    patient_name_on_report: str = Field(default="", description="Patient name on report or empty string")
    report_type: str = Field(default="unknown", description="biochemistry/haematology/lipid/comprehensive/unknown")


def extract_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict[str, Any]:
    """
    Send image to Gemini Vision and extract lab values.

    Returns:
        dict with keys: extracted_fields, confidence, report_date,
                        patient_name_on_report, report_type, model, error (if any)
    """
    if not _gemini_client:
        logger.error("GEMINI_API_KEY not set in environment")
        return {
            "extracted_fields": {},
            "confidence": {},
            "error": "GEMINI_API_KEY not configured. Please add it to your .env file.",
            "model": "none",
        }

    try:
        response = _gemini_client.models.generate_content(
            model="gemini-flash-lite-latest",
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mime_type,
                ),
                _EXTRACTION_PROMPT,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=OCRResponse,
            )
        )

        raw_text = response.text.strip()
        logger.info("Gemini OCR raw response length: %d chars", len(raw_text))

        result = json.loads(raw_text)

        # Validate and sanitize extracted_fields — only keep known fields
        raw_fields = result.get("extracted_fields", {})
        clean_fields: dict[str, Any] = {}
        clean_confidence: dict[str, str] = {}
        confidence_map = result.get("confidence", {})

        for field, value in raw_fields.items():
            if field not in FIELD_MAP:
                # Log discarded fields for auditability — these are keys Gemini returned
                # that are NOT mapped in this application and are silently rejected.
                logger.info("OCR DISCARD — unmapped field '%s' (value=%s) not in application FIELD_MAP", field, value)
                continue
            expected_type = FIELD_MAP[field].get("type", "float")
            
            if expected_type == "float":
                try:
                    numeric = float(value)
                    if numeric < 0 or numeric > 100000:
                        logger.warning("OCR DISCARD — suspicious value for '%s': %s (out of absolute bounds)", field, value)
                        continue
                    clean_fields[field] = round(numeric, 2)
                    clean_confidence[field] = confidence_map.get(field, "medium")
                except (TypeError, ValueError):
                    logger.warning("OCR DISCARD — non-numeric value for '%s': %s", field, value)
            else:
                if value and isinstance(value, str):
                    clean_fields[field] = value.strip()
                    clean_confidence[field] = confidence_map.get(field, "medium")

        return {
            "extracted_fields": clean_fields,
            "confidence": clean_confidence,
            "report_date": result.get("report_date", ""),
            "patient_name_on_report": result.get("patient_name_on_report", ""),
            "report_type": result.get("report_type", "unknown"),
            "fields_found": len(clean_fields),
            "model": "gemini-flash-lite-latest",
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
    return _FIELD_LABELS


def get_field_units() -> dict[str, str]:
    return _FIELD_UNITS
