from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
import logging

from database import get_db, Patient, MonthlyRecord
from config import templates
from dependencies import get_user
from dashboard_logic import get_current_month_str, get_month_label, get_patients_needing_alerts
from alerts import (
    build_individual_whatsapp_link, build_schedule_message, send_whatsapp,
    send_bulk_whatsapp_alerts, send_ward_email
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])

@router.get("", response_class=HTMLResponse)
async def alert_center(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    month_str = month or get_current_month_str()
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
        def _slot_label(day, shift):
            parts = [p for p in [day or "", shift or ""] if p]
            return " – ".join(parts) if parts else ""
        slots = [
            _slot_label(p.hd_day_1, p.hd_slot_1),
            _slot_label(p.hd_day_2, p.hd_slot_2),
            _slot_label(p.hd_day_3, p.hd_slot_3),
        ]
        remarks = (rec_obj.issues or "") if (rec_obj and rec_obj.issues) else ""
        msg = build_schedule_message(p.name, slots, remarks)
        _, link = send_whatsapp(p.contact_no, msg)
        schedule_links.append({
            "name": p.name, "hid": p.hid_no, "contact": p.contact_no,
            "slots": [s for s in slots if s],
            "remarks": remarks, "link": link,
        })

    return templates.TemplateResponse("alerts.html", {
        "request": request, "alert_links": alert_links,
        "schedule_links": schedule_links, "month_str": month_str,
        "month_label": month_label, "user": get_user(request),
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
