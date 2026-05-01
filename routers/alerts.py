from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, date
import logging

from database import get_db, Patient, MonthlyRecord, PatientReminder
from config import templates
from dependencies import get_user
from dashboard_logic import get_current_month_str, get_month_label, get_patients_needing_alerts, get_effective_month
from alerts import (
    build_individual_whatsapp_link, build_schedule_message, send_whatsapp,
    send_bulk_whatsapp_alerts, send_ward_email, send_reminders_digest_email,
    compute_upcoming_sessions,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])

@router.get("", response_class=HTMLResponse)
async def alert_center(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    month_str, data_note = get_effective_month(db, month)
    month_label = get_month_label(month_str)
    
    # 1. Get clinical alerts
    alert_patients = get_patients_needing_alerts(db, month_str)
    alert_links = []
    for ap in alert_patients:
        p = ap["patient"]
        if not p.contact_no: continue
        rec_obj = db.query(MonthlyRecord).filter(
            MonthlyRecord.patient_id == p.id,
            MonthlyRecord.record_month == month_str
        ).first()
        link = build_individual_whatsapp_link(p, rec_obj, month_label)
        alert_links.append({
            "name": p.name, "hid": p.hid_no, "contact": p.contact_no,
            "alerts": ap["alerts"], "link": link,
        })

    # 2. Get schedule links
    active = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    schedule_links = []
    for p in active:
        if not p.contact_no: continue
        rec_obj = db.query(MonthlyRecord).filter(
            MonthlyRecord.patient_id == p.id,
            MonthlyRecord.record_month == month_str
        ).first()
        sessions = compute_upcoming_sessions(p)
        remarks = (rec_obj.issues or "") if (rec_obj and rec_obj.issues) else ""
        msg = build_schedule_message(p.name, sessions, remarks)
        _, link = send_whatsapp(p.contact_no, msg)
        schedule_links.append({
            "name": p.name, "hid": p.hid_no, "contact": p.contact_no,
            "sessions": sessions,
            "remarks": remarks, "link": link,
        })

    # 3. Get clinical reminders
    clinical_reminders = db.query(PatientReminder).filter(
        PatientReminder.is_completed == False
    ).order_by(PatientReminder.reminder_date).all()

    return templates.TemplateResponse("alerts.html", {
        "request": request, "alert_links": alert_links,
        "schedule_links": schedule_links,
        "clinical_reminders": clinical_reminders,
        "month_str": month_str,
        "month_label": month_label,
        "data_note": data_note,
        "now_date": date.today(),
        "user": get_user(request),
    })

@router.get("/wa-link/{patient_id}")
async def api_wa_link(patient_id: int, month: Optional[str] = None, db: Session = Depends(get_db)):
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p: raise HTTPException(status_code=404, detail="Patient not found")
    if not p.contact_no: raise HTTPException(status_code=400, detail="No contact number on file")
    
    month_str = month or get_current_month_str()
    rec_obj = db.query(MonthlyRecord).filter(
        MonthlyRecord.patient_id == patient_id,
        MonthlyRecord.record_month == month_str
    ).first()
    link = build_individual_whatsapp_link(p, rec_obj, get_month_label(month_str))
    return JSONResponse(content={"url": link})

@router.post("/send-whatsapp")
async def api_send_whatsapp_bulk(month: Optional[str] = None, db: Session = Depends(get_db)):
    month_str = month or get_current_month_str()
    try:
        patients = get_patients_needing_alerts(db, month_str)
        result = send_bulk_whatsapp_alerts(patients, get_month_label(month_str))
        return JSONResponse(content={"message": result.get("message", "✅ Done.")})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/send-email")
async def api_send_email_bulk(month: Optional[str] = None, db: Session = Depends(get_db)):
    month_str = month or get_current_month_str()
    try:
        patients = get_patients_needing_alerts(db, month_str)
        success, detail = send_ward_email(patients, get_month_label(month_str), month_str[:4])
        if not success: raise HTTPException(status_code=500, detail=detail)
        return JSONResponse(content={"message": f"✅ {detail}"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/send-reminders-email")
async def api_send_reminders_email(db: Session = Depends(get_db)):
    reminders = db.query(PatientReminder).filter(
        PatientReminder.is_completed == False
    ).order_by(PatientReminder.reminder_date).all()
    success, detail = send_reminders_digest_email(reminders)
    if not success:
        raise HTTPException(status_code=500, detail=detail)
    return JSONResponse(content={"message": f"✅ {detail}"})


@router.post("/reminders/create")
async def create_reminder(
    patient_id: int = Form(...),
    reminder_date: str = Form(...),
    message: str = Form(...),
    db: Session = Depends(get_db)
):
    new_rem = PatientReminder(
        patient_id=patient_id,
        reminder_date=datetime.strptime(reminder_date, "%Y-%m-%d").date(),
        message=message
    )
    db.add(new_rem)
    db.commit()
    return RedirectResponse(url="/patients", status_code=303)

@router.post("/reminders/{reminder_id}/complete")
async def complete_reminder(reminder_id: int, db: Session = Depends(get_db)):
    rem = db.query(PatientReminder).filter(PatientReminder.id == reminder_id).first()
    if not rem: raise HTTPException(status_code=404)
    rem.is_completed = True
    db.commit()
    return JSONResponse(content={"status": "success"})
