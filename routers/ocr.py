"""
routers/ocr.py — OCR Blood Report Upload API
POST /ocr/extract-report: Accepts image upload, returns extracted lab values via Gemini Vision.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import Patient, get_db
from dependencies import get_user
from services.ocr_service import extract_from_image, get_field_labels, get_field_units

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ocr", tags=["ocr"])

# Supported MIME types for uploaded images
ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
    "application/pdf",
}
MAX_FILE_SIZE_MB = 10


@router.post("/extract-report")
async def extract_report(
    request: Request,
    patient_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """
    Upload a blood/biochemistry report image and extract lab values using Gemini Vision OCR.

    Args:
        patient_id: The patient this report belongs to
        file: Report image (JPEG, PNG, WebP)

    Returns:
        JSON with extracted_fields (mapped to MonthlyRecord field names),
        confidence ratings, and metadata.
    """
    # Auth check
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Validate patient exists
    patient = db.query(Patient).filter(Patient.id == patient_id, Patient.is_active == True).first()
    if not patient:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    # Validate file type
    content_type = file.content_type or ""
    # Normalize content type (browsers sometimes send "image/jpg" instead of "image/jpeg")
    if content_type == "image/jpg":
        content_type = "image/jpeg"

    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{content_type}'. Please upload a JPEG, PNG, or WebP image.",
        )

    # Read file bytes
    image_bytes = await file.read()

    # Validate file size
    size_mb = len(image_bytes) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f} MB). Maximum allowed size is {MAX_FILE_SIZE_MB} MB.",
        )

    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    logger.info(
        "OCR extract request — patient_id=%s file=%s size=%.1fMB type=%s",
        patient_id,
        file.filename,
        size_mb,
        content_type,
    )

    # Run OCR extraction
    result = extract_from_image(image_bytes, mime_type=content_type)

    # Add helpful metadata for the frontend
    result["patient_id"] = patient_id
    result["patient_name"] = patient.name
    result["filename"] = file.filename
    result["field_labels"] = get_field_labels()
    result["field_units"] = get_field_units()

    if "error" in result:
        logger.warning("OCR extraction returned error for patient %s: %s", patient_id, result["error"])
        # Return 200 with error in body so frontend can show the message gracefully
        return JSONResponse(content=result, status_code=200)

    logger.info(
        "OCR extraction complete — patient_id=%s fields_found=%s",
        patient_id,
        result.get("fields_found", 0),
    )

    return JSONResponse(content=result)


@router.get("/field-map")
async def get_field_map(request: Request) -> JSONResponse:
    """Return the complete field mapping for the frontend to reference."""
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    return JSONResponse(content={
        "labels": get_field_labels(),
        "units": get_field_units(),
    })
