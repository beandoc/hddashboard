"""
routers/api_next.py
===================
API router dedicated to the Next.js frontend application.
Handles all calls matching /api/... prefix.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import MonthlyRecord, Patient, get_db
from dependencies import get_user
from services import patient_service, entry_service
from dashboard_logic import compute_dashboard, get_current_month_str, get_month_label

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api-next"])

# ── Response schemas & payloads ──────────────────────────────────────────────

class PatientPayload(BaseModel):
    name: str
    contact: Optional[str] = ""
    age: Optional[int] = None
    gender: Optional[str] = "Male"
    diagnosis: Optional[str] = ""
    hd_slot_1: Optional[str] = ""
    hd_slot_2: Optional[str] = ""
    hd_slot_3: Optional[str] = ""
    clinical_remarks: Optional[str] = ""
    is_active: Optional[bool] = True

# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def get_dashboard_api(
    month: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    request: Request = None,
):
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    month_str = month or get_current_month_str()
    try:
        data = compute_dashboard(db, month_str)
        return JSONResponse(content=jsonable_encoder(data))
    except Exception as e:
        logger.error(f"Error computing dashboard: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patients")
async def list_patients(
    q: Optional[str] = Query(default=""),
    db: Session = Depends(get_db),
    request: Request = None,
):
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Search query filter (by name, HID, or contact)
    query = db.query(Patient)
    if q:
        search_filter = f"%{q}%"
        query = query.filter(
            (Patient.name.ilike(search_filter)) |
            (Patient.hid_no.ilike(search_filter)) |
            (Patient.contact_no.ilike(search_filter))
        )
    
    # We want active or matches search
    patients = query.order_by(Patient.name).all()

    output = []
    for p in patients:
        output.append({
            "id": p.id,
            "name": p.name,
            "hid": p.hid_no,
            "sex": p.sex,
            "access": p.access_type,
            "contact": p.contact_no,
            "hd_slot_1": p.hd_slot_1,
            "hd_slot_2": p.hd_slot_2,
            "hd_slot_3": p.hd_slot_3,
            "is_active": p.is_active
        })

    return JSONResponse(content=jsonable_encoder(output))


@router.post("/patients")
async def create_patient(
    payload: PatientPayload,
    db: Session = Depends(get_db),
    request: Request = None,
):
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        # Construct parameters for create_patient_record
        data = payload.model_dump()
        
        # Auto-generate hid_no if not present
        if "hid_no" not in data or not data.get("hid_no"):
            max_id = db.query(func.max(Patient.id)).scalar() or 0
            data["hid_no"] = f"HD-{(max_id + 1):04d}"

        # Map frontend key names to patient_service field names
        data["sex"] = data.get("gender", "Male")
        data["contact_no"] = data.get("contact", "")
        data["clinical_background"] = data.get("clinical_remarks", "")

        patient = patient_service.create_patient_record(db, data)
        return JSONResponse(content={"id": patient.id, "message": "Patient created successfully"})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating patient: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/patients/{patient_id}")
async def get_patient(
    patient_id: int,
    db: Session = Depends(get_db),
    request: Request = None,
):
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    output = {
        "name": patient.name,
        "contact": patient.contact_no,
        "age": patient.age,
        "gender": patient.sex,
        "diagnosis": patient.diagnosis,
        "hd_slot_1": patient.hd_slot_1 or "",
        "hd_slot_2": patient.hd_slot_2 or "",
        "hd_slot_3": patient.hd_slot_3 or "",
        "clinical_remarks": patient.clinical_background or "",
        "is_active": patient.is_active
    }
    return JSONResponse(content=jsonable_encoder(output))


@router.put("/patients/{patient_id}")
async def update_patient(
    patient_id: int,
    payload: PatientPayload,
    db: Session = Depends(get_db),
    request: Request = None,
):
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        patient = db.query(Patient).filter(Patient.id == patient_id).first()
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        data = payload.model_dump()
        # Keep same HID
        data["hid_no"] = patient.hid_no

        # Map frontend key names to patient_service field names
        data["sex"] = data.get("gender", "Male")
        data["contact_no"] = data.get("contact", "")
        data["clinical_background"] = data.get("clinical_remarks", "")

        patient_service.update_patient_record(db, patient_id, data)
        return JSONResponse(content={"message": "Patient updated successfully"})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating patient {patient_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/patients/{patient_id}/timeline")
async def get_patient_timeline(
    patient_id: int,
    db: Session = Depends(get_db),
    request: Request = None,
):
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    records = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id).order_by(MonthlyRecord.record_month.desc()).all()

    timeline = []
    for r in records:
        timeline.append({
            "month": r.record_month,
            "label": get_month_label(r.record_month),
            "hb": r.hb,
            "albumin": r.albumin,
            "phosphorus": r.phosphorus,
            "idwg": r.idwg,
            "issues": r.issues
        })

    output = {
        "patient": {
            "id": patient.id,
            "name": patient.name
        },
        "timeline": timeline
    }
    return JSONResponse(content=jsonable_encoder(output))


@router.post("/send-schedule/{patient_id}")
async def send_schedule(
    patient_id: int,
    db: Session = Depends(get_db),
    request: Request = None,
):
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    from alerts import compute_upcoming_sessions, build_schedule_message, send_whatsapp_twilio
    
    sessions = compute_upcoming_sessions(patient)
    month_str = get_current_month_str()
    record = db.query(MonthlyRecord).filter(
        MonthlyRecord.patient_id == patient_id,
        MonthlyRecord.record_month == month_str
    ).first()
    remarks = record.issues if (record and record.issues) else ""

    message = build_schedule_message(patient.name, sessions, remarks)

    if patient.contact_no:
        success, detail = send_whatsapp_twilio(patient.contact_no, message)
        if success:
            return JSONResponse(content={"message": f"Schedule sent via Twilio to {patient.name} ({patient.contact_no})"})
        else:
            return JSONResponse(content={"message": f"Twilio send failed: {detail}"}, status_code=500)
    else:
        raise HTTPException(status_code=400, detail="Patient has no contact number on file")


@router.post("/entries/bulk")
async def save_entries_bulk(
    payload: List[Dict[str, Any]],
    db: Session = Depends(get_db),
    request: Request = None,
):
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    username = getattr(user, "username", "anonymous")

    try:
        saved_count = 0
        for entry in payload:
            patient_id = entry.get("patient_id")
            if not patient_id:
                continue

            # Check if patient exists
            patient = db.query(Patient).filter(Patient.id == patient_id).first()
            if not patient:
                logger.warning(f"Bulk entry contains invalid patient_id: {patient_id}")
                continue

            record_month = entry.get("record_month")
            if not record_month:
                continue

            # Build data dict for save_monthly_record
            # Ensure proper type conversions to floats/strings
            data = {
                "month_str": record_month,
                "hb": float(entry["hb"]) if entry.get("hb") not in (None, "") else None,
                "albumin": float(entry["albumin"]) if entry.get("albumin") not in (None, "") else None,
                "phosphorus": float(entry["phosphorus"]) if entry.get("phosphorus") not in (None, "") else None,
                "idwg": float(entry["idwg"]) if entry.get("idwg") not in (None, "") else None,
                "calcium": float(entry["calcium"]) if entry.get("calcium") not in (None, "") else None,
                "serum_ferritin": float(entry["serum_ferritin"]) if entry.get("serum_ferritin") not in (None, "") else None,
                "tsat": float(entry["tsat"]) if entry.get("tsat") not in (None, "") else None,
                "ipth": float(entry["ipth"]) if entry.get("ipth") not in (None, "") else None,
                "wbc_count": float(entry["wbc_count"]) if entry.get("wbc_count") not in (None, "") else None,
                "serum_potassium": float(entry["serum_potassium"]) if entry.get("serum_potassium") not in (None, "") else None,
                "serum_sodium": float(entry["serum_sodium"]) if entry.get("serum_sodium") not in (None, "") else None,
                "residual_urine_output": float(entry["residual_urine_output"]) if entry.get("residual_urine_output") not in (None, "") else None,
                "single_pool_ktv": float(entry["single_pool_ktv"]) if entry.get("single_pool_ktv") not in (None, "") else None,
                "post_dialysis_urea": float(entry["post_dialysis_urea"]) if entry.get("post_dialysis_urea") not in (None, "") else None,
                "pre_dialysis_urea": float(entry["pre_dialysis_urea"]) if entry.get("pre_dialysis_urea") not in (None, "") else None,
                "hba1c": float(entry["hba1c"]) if entry.get("hba1c") not in (None, "") else None,
                "esa_type": entry.get("esa_type") or None,
                "epo_weekly_units": float(entry["epo_weekly_units"]) if entry.get("epo_weekly_units") not in (None, "") else None,
                "epo_mircera_dose": entry.get("epo_mircera_dose") or None,
                "esa_modified_at": entry.get("esa_modified_at") or None,
                "desidustat_modified_at": entry.get("desidustat_modified_at") or None,
                "phosphate_binder_modified_at": entry.get("phosphate_binder_modified_at") or None,
                "antihypertensive_name": entry.get("antihypertensive_name", []),
                "antihypertensive_dose": entry.get("antihypertensive_dose", []),
                "antihypertensive_freq": entry.get("antihypertensive_freq", []),
                "hospitalization_this_month": bool(entry.get("hospitalization_this_month")),
                "hospitalization_diagnosis": entry.get("hospitalization_diagnosis") or None,
                "hospitalization_details": entry.get("hospitalization_details") or None,
            }

            entry_service.save_monthly_record(db, patient_id, data, actor=username)
            saved_count += 1

        db.commit()
        return JSONResponse(content={"message": f"Successfully saved {saved_count} records"})
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving bulk entries: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save records")
