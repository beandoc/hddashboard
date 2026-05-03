from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime
import logging

from database import get_db, Patient, SessionRecord, InterimLabRecord
from config import templates
from dependencies import get_user

logger = logging.getLogger(__name__)

from services import session_service

router = APIRouter(prefix="/patients", tags=["sessions"])
session_router = APIRouter(prefix="/sessions", tags=["sessions"])

@router.get("/{patient_id}/sessions/new", response_class=HTMLResponse)
async def new_session_form(patient_id: int, request: Request, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient: raise HTTPException(status_code=404, detail="Patient not found")
    last_3_sessions = db.query(SessionRecord).filter(SessionRecord.patient_id == patient_id).order_by(SessionRecord.session_date.desc()).limit(3).all()
    return templates.TemplateResponse("session_form.html", {
        "request": request, "patient": patient, "session": None, "mode": "new",
        "user": get_user(request),
        "last_3_sessions": last_3_sessions
    })

@router.post("/{patient_id}/sessions/new")
async def create_session(
    patient_id: int, db: Session = Depends(get_db),
    session_date: str = Form(...),
    blood_flow_rate: Optional[float] = Form(None),
    actual_blood_flow_rate: Optional[float] = Form(None),
    dialysate_flow: Optional[float] = Form(None),
    dialysate_flow_direction: Optional[str] = Form(None),
    duration_hours: Optional[int] = Form(None),
    duration_minutes: Optional[int] = Form(None),
    weight_pre: Optional[float] = Form(None),
    weight_post: Optional[float] = Form(None),
    bp_pre_sys: Optional[float] = Form(None),
    bp_pre_dia: Optional[float] = Form(None),
    bp_post_sys: Optional[float] = Form(None),
    bp_post_dia: Optional[float] = Form(None),
    arterial_line_pressure: Optional[float] = Form(None),
    venous_line_pressure: Optional[float] = Form(None),
    access_location: str = Form(""),
    access_condition: str = Form(""),
    needle_gauge: str = Form(""),
    cannulation_technique: str = Form(""),
    access_complications: str = Form(""),
    vascular_interventions: str = Form(""),
    anticoagulation: str = Form(""),
    anticoagulation_dose: Optional[float] = Form(None),
    idh_episode: bool = Form(False),
    muscle_cramps: bool = Form(False),
    early_termination: bool = Form(False),
    dialyzer_type: str = Form(""),
    entered_by: str = Form(""),
    interim_hb: Optional[float] = Form(None),
    interim_k: Optional[float] = Form(None),
    interim_ca: Optional[float] = Form(None),
    interim_trigger: Optional[str] = Form(None),
    intradialytic_exercise_mins: Optional[int] = Form(None),
    intradialytic_meals_eaten: bool = Form(False),
    pre_hd_dyspnea_likert: Optional[int] = Form(None),
    post_hd_dyspnea_likert: Optional[int] = Form(None),
    is_emergency: bool = Form(False),
    reason_emergency: Optional[str] = Form(None),
    urea_peripheral_s: Optional[float] = Form(None),
    urea_arterial_a: Optional[float] = Form(None),
    urea_venous_v: Optional[float] = Form(None),
    access_recirculation_percent: Optional[float] = Form(None),
    access_flow_qa: Optional[float] = Form(None),
):
    try:
        session_service.create_session_record(db, patient_id, locals())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return RedirectResponse(url=f"/analytics/patients/{patient_id}", status_code=303)

@session_router.get("/{session_id}/edit", response_class=HTMLResponse)
async def edit_session_form(session_id: int, request: Request, db: Session = Depends(get_db)):
    sess = db.query(SessionRecord).filter(SessionRecord.id == session_id).first()
    if not sess: raise HTTPException(status_code=404)
    patient = db.query(Patient).filter(Patient.id == sess.patient_id).first()
    return templates.TemplateResponse("session_form.html", {
        "request": request, "patient": patient, "session": sess, "mode": "edit",
        "user": get_user(request),
    })

@session_router.post("/{session_id}/edit")
async def update_session(
    session_id: int, db: Session = Depends(get_db),
    session_date: str = Form(...),
    blood_flow_rate: Optional[float] = Form(None),
    actual_blood_flow_rate: Optional[float] = Form(None),
    dialysate_flow: Optional[float] = Form(None),
    dialysate_flow_direction: Optional[str] = Form(None),
    duration_hours: Optional[int] = Form(None),
    duration_minutes: Optional[int] = Form(None),
    weight_pre: Optional[float] = Form(None),
    weight_post: Optional[float] = Form(None),
    bp_pre_sys: Optional[float] = Form(None),
    bp_pre_dia: Optional[float] = Form(None),
    bp_post_sys: Optional[float] = Form(None),
    bp_post_dia: Optional[float] = Form(None),
    arterial_line_pressure: Optional[float] = Form(None),
    venous_line_pressure: Optional[float] = Form(None),
    access_location: str = Form(""),
    access_condition: str = Form(""),
    needle_gauge: str = Form(""),
    cannulation_technique: str = Form(""),
    access_complications: str = Form(""),
    vascular_interventions: str = Form(""),
    anticoagulation: str = Form(""),
    anticoagulation_dose: Optional[float] = Form(None),
    idh_episode: bool = Form(False),
    muscle_cramps: bool = Form(False),
    early_termination: bool = Form(False),
    dialyzer_type: str = Form(""),
    entered_by: str = Form(""),
    interim_hb: Optional[float] = Form(None),
    interim_k: Optional[float] = Form(None),
    interim_ca: Optional[float] = Form(None),
    interim_trigger: Optional[str] = Form(None),
    intradialytic_exercise_mins: Optional[int] = Form(None),
    intradialytic_meals_eaten: bool = Form(False),
    pre_hd_dyspnea_likert: Optional[int] = Form(None),
    post_hd_dyspnea_likert: Optional[int] = Form(None),
    is_emergency: bool = Form(False),
    reason_emergency: Optional[str] = Form(None),
    urea_peripheral_s: Optional[float] = Form(None),
    urea_arterial_a: Optional[float] = Form(None),
    urea_venous_v: Optional[float] = Form(None),
    access_recirculation_percent: Optional[float] = Form(None),
    access_flow_qa: Optional[float] = Form(None),
):
    try:
        session_service.update_session_record(db, session_id, locals())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    sess = db.query(SessionRecord).filter(SessionRecord.id == session_id).first()
    return RedirectResponse(url=f"/analytics/patients/{sess.patient_id}", status_code=303)

@session_router.post("/{session_id}/delete")
async def delete_session(session_id: int, db: Session = Depends(get_db)):
    sess = db.query(SessionRecord).filter(SessionRecord.id == session_id).first()
    if sess:
        pid = sess.patient_id
        db.delete(sess)
        db.commit()
        return RedirectResponse(url=f"/analytics/patients/{pid}", status_code=303)
    return RedirectResponse(url="/patients", status_code=303)
