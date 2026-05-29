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

    # Batch: single query for all patients, determine admitted ones in Python
    _hosp_events = (
        db.query(ClinicalEvent)
        .filter(
            ClinicalEvent.patient_id.in_([p.id for p in patients]),
            ClinicalEvent.event_type.in_(["Hospitalization", "Discharge"]),
        )
        .order_by(ClinicalEvent.event_date.desc(), ClinicalEvent.id.desc())
        .all()
    )
    _last_hosp_by_pid: dict = {}
    for ev in _hosp_events:
        _last_hosp_by_pid.setdefault(ev.patient_id, ev)
    admitted_patients = [
        p for p in patients
        if _last_hosp_by_pid.get(p.id) and _last_hosp_by_pid[p.id].event_type == "Hospitalization"
    ]

    csrf_token = _csrf_signer.sign("events-new").decode()
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
        "csrf_token":  csrf_token,
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
    hospital_name: str = Form(""),
    discharge_date: Optional[str] = Form(None),
    los_days: Optional[int] = Form(None),
    discharge_diagnosis: str = Form(""),
    hosp_diagnosis: list[str] = Form([]),
    hosp_icd_code: list[str] = Form([]),
    hosp_icd_diag: list[str] = Form([]),
    proc_setting: str = Form(""),
    proc_outcome: str = Form(""),
    proc_operator: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        _csrf_signer.unsign(csrf_token, max_age=3600)
    except BadData:
        raise HTTPException(status_code=403, detail="Invalid or expired form token. Please refresh and try again.")

    # 1. Save Clinical Event
    user = get_user(request)
    created_by = "Unknown"
    if user:
        if isinstance(user, dict):
            created_by = user.get("username", "Unknown")
        else:
            created_by = getattr(user, "username", "Unknown")

    # Build notes — prepend contextual metadata for each event class
    from constants import PROCEDURE_EVENT_TYPES
    final_notes = notes.strip() if notes else ""

    if event_type == "Hospitalization":
        if hospital_name and f"Hospital: {hospital_name}" not in final_notes:
            final_notes = f"Hospital: {hospital_name}\n{final_notes}".strip()
        if discharge_diagnosis and "Discharge Diagnosis:" not in final_notes:
            final_notes = f"{final_notes}\nDischarge Diagnosis: {discharge_diagnosis}".strip()

    elif event_type == "Discharge":
        if hospital_name and f"Hospital: {hospital_name}" not in final_notes:
            final_notes = f"Hospital: {hospital_name}\n{final_notes}".strip()
        if discharge_diagnosis and "Discharge Diagnosis:" not in final_notes:
            final_notes = f"{final_notes}\nDischarge Diagnosis: {discharge_diagnosis}".strip()

    elif event_type in PROCEDURE_EVENT_TYPES:
        parts = []
        if proc_setting:  parts.append(f"Setting: {proc_setting}")
        if proc_outcome:  parts.append(f"Outcome: {proc_outcome}")
        if proc_operator: parts.append(f"Operator: {proc_operator}")
        if final_notes:   parts.append(final_notes)
        final_notes = "\n".join(parts)

    ev = ClinicalEvent(
        patient_id=patient_id,
        event_date=date.fromisoformat(event_date),
        event_type=event_type,
        severity=severity,
        notes=final_notes,
        created_by=created_by
    )
    db.add(ev)

    # 2. Sync to MonthlyRecord and HospitalisationEvent if Hospitalization
    if event_type == "Hospitalization":
        from services.patient_service import sync_hospitalization_to_monthly_record
        diag_list     = hosp_diagnosis or []
        code_list     = hosp_icd_code or []
        diag_icd_list = hosp_icd_diag or []

        adm_date = date.fromisoformat(event_date)

        # Parse optional same-day discharge from admission modal
        dis_date_adm = None
        los_adm = los_days
        if discharge_date:
            try:
                dis_date_adm = date.fromisoformat(discharge_date)
                if los_adm is None:
                    los_adm = max((dis_date_adm - adm_date).days, 0)
            except ValueError:
                pass

        if not diag_list and not code_list:
            sync_hospitalization_to_monthly_record(
                db=db, patient_id=patient_id, event_date=adm_date,
                diagnosis="", icd_code="", icd_diagnosis=""
            )
        else:
            for d, c, i in zip(diag_list, code_list, diag_icd_list):
                sync_hospitalization_to_monthly_record(
                    db=db, patient_id=patient_id, event_date=adm_date,
                    diagnosis=d, icd_code=c, icd_diagnosis=i
                )

        # Create HospitalisationEvent if not already existing for this admission date
        from database import HospitalisationEvent
        hosp_exists = db.query(HospitalisationEvent).filter(
            HospitalisationEvent.patient_id == patient_id,
            HospitalisationEvent.admission_date == adm_date
        ).first()
        if not hosp_exists:
            from datetime import timedelta
            prior = (
                db.query(HospitalisationEvent)
                .filter(
                    HospitalisationEvent.patient_id == patient_id,
                    HospitalisationEvent.discharge_date != None,
                    HospitalisationEvent.discharge_date >= adm_date - timedelta(days=30),
                    HospitalisationEvent.discharge_date < adm_date,
                )
                .first()
            )
            # Primary ICD from hidden field (ICD search); secondary rows in diag_list
            c_val = code_list[0] if code_list else None
            d_val = diag_list[0] if diag_list else None
            # cause_category derived from ICD code via shortlist mapping
            _ICD_CATEGORY = {
                "J81":"Fluid overload","I50.0":"Cardiac","A41.9":"Infection",
                "T82.7":"Access-related","I10":"Cardiac","E87.5":"Metabolic",
                "J18.9":"Infection","I21":"Cardiac","R55":"Cardiac",
                "D64.9":"Metabolic","T85.7":"Access-related","N18.6":"Renal",
                "E83.5":"Metabolic","E83.3":"Metabolic","I48":"Cardiac",
                "K92.1":"GI","G40":"Neurological","I63":"Neurological",
                "E11":"Metabolic","N28.9":"Renal",
            }
            cat_val = _ICD_CATEGORY.get(c_val, None) if c_val else None

            db.add(HospitalisationEvent(
                patient_id=patient_id,
                admission_date=adm_date,
                discharge_date=dis_date_adm,
                los_days=los_adm,
                primary_icd=c_val or None,
                primary_diagnosis=d_val or None,
                cause_category=cat_val,
                readmission_within_30d=bool(prior),
                notes=final_notes or None,
                entered_by=created_by,
            ))

    elif event_type == "Discharge":
        from database import HospitalisationEvent
        dis_date = date.fromisoformat(event_date)
        open_hosp = db.query(HospitalisationEvent).filter(
            HospitalisationEvent.patient_id == patient_id,
            HospitalisationEvent.discharge_date == None
        ).order_by(HospitalisationEvent.admission_date.desc()).first()
        if open_hosp:
            open_hosp.discharge_date = dis_date
            open_hosp.los_days = max((dis_date - open_hosp.admission_date).days, 0)
            if discharge_diagnosis:
                open_hosp.notes = (open_hosp.notes or "") + f"\nDischarge Dx: {discharge_diagnosis}"

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("create_event failed: %s", exc, exc_info=True)
        back = request.headers.get("referer", "/events")
        sep = "&" if "?" in back else "?"
        return RedirectResponse(
            url=f"{back}{sep}event_error=Failed+to+save+event.+Please+try+again.",
            status_code=303,
        )
    return RedirectResponse(url="/events?event_saved=1", status_code=303)

@router.post("/{event_id}/delete")
async def delete_event(
    event_id: int,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        _csrf_signer.unsign(csrf_token, max_age=3600)
    except BadData:
        raise HTTPException(status_code=403, detail="Invalid or expired form token.")
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
    
    user = get_user(request)
    entered_by = "Unknown"
    if user:
        if isinstance(user, dict):
            entered_by = user.get("username", "Unknown")
        else:
            entered_by = getattr(user, "username", "Unknown")

    interim = InterimLabRecord(
        patient_id=patient_id,
        lab_date=date.fromisoformat(lab_date),
        record_month=lab_date[:7],
        parameter=parameter,
        value=value,
        unit=unit,
        trigger=trigger,
        notes=notes,
        entered_by=entered_by
    )
    db.add(interim)
    db.commit()
    return RedirectResponse(url=f"/patients/{patient_id}/profile", status_code=303)
