from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime, timedelta
import logging

import json
from database import get_db, Patient, ClinicalEvent, InterimLabRecord, MonthlyRecord
from config import templates, _csrf_signer
from itsdangerous import BadData
from dependencies import get_user
from constants import EVENT_TYPES, EVENT_TYPE_GROUPS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["events"])

@router.get("", response_class=HTMLResponse)
async def events_timeline(
    request: Request,
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    event_type: Optional[str] = None,
    severity:   Optional[str] = None,
    patient_id: Optional[str] = None,
    prefill: Optional[str] = None,
    db: Session = Depends(get_db),
):
    today = date.today()
    d_from = date.fromisoformat(date_from) if date_from else today - timedelta(days=90)
    d_to   = date.fromisoformat(date_to)   if date_to   else today

    q = db.query(ClinicalEvent).filter(
        ClinicalEvent.event_date >= d_from,
        ClinicalEvent.event_date <= d_to,
    )
    if event_type: q = q.filter(ClinicalEvent.event_type == event_type)
    if severity: q = q.filter(ClinicalEvent.severity == severity)
    if patient_id and patient_id.strip():
        try:
            pid_int = int(patient_id)
            q = q.filter(ClinicalEvent.patient_id == pid_int)
        except ValueError:
            pass

    events = q.order_by(ClinicalEvent.event_date.desc()).all()

    sev_counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    type_counts: dict = {}
    for ev in events:
        sev_counts[ev.severity] = sev_counts.get(ev.severity, 0) + 1
        type_counts[ev.event_type] = type_counts.get(ev.event_type, 0) + 1

    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()

    # Determine currently admitted patients (last event is Hospitalization and not yet Discharged)
    admitted_patients = []
    for p in patients:
        last_event = db.query(ClinicalEvent).filter(
            ClinicalEvent.patient_id == p.id,
            ClinicalEvent.event_type.in_(["Hospitalization", "Discharge"])
        ).order_by(ClinicalEvent.event_date.desc(), ClinicalEvent.id.desc()).first()
        if last_event and last_event.event_type == "Hospitalization":
            admitted_patients.append(p)

    return templates.TemplateResponse("events.html", {
        "request":     request,
        "events":      events,
        "patients":    patients,
        "admitted_patients": admitted_patients,
        "event_types":       EVENT_TYPES,
        "event_type_groups": EVENT_TYPE_GROUPS,
        "sev_counts":  sev_counts,
        "type_counts": type_counts,
        "date_from":   d_from.isoformat(),
        "date_to":     d_to.isoformat(),
        "filter_type": event_type or "",
        "filter_sev":  severity or "",
        "filter_pid":  patient_id or "",
        "total":       len(events),
        "today":       today.isoformat(),
        "prefill":     prefill or "",
        "user":        get_user(request),
    })

@router.post("/new")
async def create_event(
    request: Request,
    patient_id: int = Form(...),
    event_date: str = Form(...),
    event_type: str = Form(...),
    severity: str = Form("Medium"),
    notes: str = Form(""),
    hosp_diagnosis: list[str] = Form([]),
    hosp_icd_code: list[str] = Form([]),
    hosp_icd_diag: list[str] = Form([]),
    db: Session = Depends(get_db),
):
    # 1. Save Clinical Event
    user = get_user(request)
    created_by = "Unknown"
    if user:
        if isinstance(user, dict):
            created_by = user.get("username", "Unknown")
        else:
            created_by = getattr(user, "username", "Unknown")

    ev = ClinicalEvent(
        patient_id=patient_id,
        event_date=date.fromisoformat(event_date),
        event_type=event_type,
        severity=severity,
        notes=notes,
        created_by=created_by
    )
    db.add(ev)
    
    # 2. Sync to MonthlyRecord if Hospitalization
    if event_type == "Hospitalization" and (hosp_diagnosis or hosp_icd_code):
        month_str = event_date[:7]
        rec = db.query(MonthlyRecord).filter(
            MonthlyRecord.patient_id == patient_id,
            MonthlyRecord.record_month == month_str
        ).first()
        
        if not rec:
            rec = MonthlyRecord(patient_id=patient_id, record_month=month_str)
            db.add(rec)
        
        rec.hospitalization_this_month = True
        
        # Load existing details or start fresh
        try:
            current_details = json.loads(rec.hospitalization_details) if rec.hospitalization_details else []
        except:
            current_details = []
            
        # Add new entries
        for d, c, i in zip(hosp_diagnosis, hosp_icd_code, hosp_icd_diag):
            if d.strip() or c.strip():
                current_details.append({
                    "date": event_date,
                    "diagnosis": d.strip(),
                    "icd_code": c.strip(),
                    "icd_diagnosis": i.strip()
                })
        
        rec.hospitalization_details = json.dumps(current_details)
        
        # Update flat fields with first entry if empty
        if not rec.hospitalization_date:
            rec.hospitalization_date = date.fromisoformat(event_date)
            rec.hospitalization_diagnosis = hosp_diagnosis[0] if hosp_diagnosis else ""
            rec.hospitalization_icd_code = hosp_icd_code[0] if hosp_icd_code else ""
            rec.hospitalization_icd_diagnosis = hosp_icd_diag[0] if hosp_icd_diag else ""

    db.commit()
    return RedirectResponse(url=request.headers.get("referer", "/events"), status_code=303)

@router.post("/{event_id}/delete")
async def delete_event(event_id: int, db: Session = Depends(get_db)):
    ev = db.query(ClinicalEvent).filter(ClinicalEvent.id == event_id).first()
    if ev:
        db.delete(ev)
        db.commit()
    return RedirectResponse(url="/events", status_code=303)

@router.post("/patients/{patient_id}/interim-labs/new")
async def create_interim_lab(
    patient_id: int,
    request: Request,
    lab_date: str = Form(...),
    parameter: str = Form(...),
    value: float = Form(...),
    unit: str = Form(""),
    trigger: str = Form(""),
    notes: Optional[str] = Form(None),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        _csrf_signer.unsign(csrf_token, max_age=3600)
    except BadData:
        raise HTTPException(status_code=403, detail="Invalid or expired form token. Please refresh and try again.")
    
    interim = InterimLabRecord(
        patient_id=patient_id,
        lab_date=date.fromisoformat(lab_date),
        record_month=lab_date[:7],
        parameter=parameter,
        value=value,
        unit=unit,
        trigger=trigger,
        notes=notes,
        entered_by=get_user(request).get("username", "Unknown") if get_user(request) else "Unknown"
    )
    db.add(interim)
    db.commit()
    return RedirectResponse(url=f"/patients/{patient_id}/profile", status_code=303)
