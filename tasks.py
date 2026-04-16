from celery_app import celery_app
from database import SessionLocal, Patient, AlertLog, MonthlyRecord
from dashboard_logic import get_patients_needing_alerts, get_month_label, get_current_month_str
from alerts import send_bulk_whatsapp_alerts, send_ward_email, build_schedule_message, send_whatsapp
import logging

logger = logging.getLogger(__name__)

@celery_app.task
def task_send_bulk_whatsapp(month_str: str = None):
    db = SessionLocal()
    try:
        month = month_str or get_current_month_str()
        alert_patients = get_patients_needing_alerts(db, month)
        if not alert_patients:
            return "No alerts to send"
        
        results = send_bulk_whatsapp_alerts(alert_patients, get_month_label(month))
        for r in results.get("results", []):
            p = db.query(Patient).filter(Patient.name == r["name"]).first()
            if p:
                log = AlertLog(
                    patient_id=p.id, 
                    alert_type="whatsapp", 
                    status="sent" if r["status"] == "sent" else "failed", 
                    message_preview=r.get("sid") or r.get("error") or ""
                )
                db.add(log)
        db.commit()
        return results["message"]
    finally:
        db.close()

@celery_app.task
def task_send_ward_email(month_str: str = None):
    db = SessionLocal()
    try:
        month = month_str or get_current_month_str()
        alert_patients = get_patients_needing_alerts(db, month)
        if not alert_patients:
            return "No alerts to send"
        
        success, detail = send_ward_email(alert_patients, get_month_label(month), month[:4])
        log = AlertLog(
            alert_type="email", 
            alert_reason=f"Ward report {month}", 
            status="sent" if success else "failed", 
            message_preview=detail
        )
        db.add(log)
        db.commit()
        return detail
    finally:
        db.close()

@celery_app.task
def task_send_schedule_reminder(patient_id: int):
    db = SessionLocal()
    try:
        p = db.query(Patient).filter(Patient.id == patient_id).first()
        if not p or not p.contact_no:
            return "Patient not found or no contact number"
        
        slots = [p.hd_slot_1, p.hd_slot_2, p.hd_slot_3]
        message = build_schedule_message(p.name, slots)
        success, detail = send_whatsapp(p.contact_no, message)
        
        log = AlertLog(
            patient_id=p.id, 
            alert_type="whatsapp_schedule", 
            status="sent" if success else "failed", 
            message_preview=detail
        )
        db.add(log)
        db.commit()
        return "Sent" if success else detail
    finally:
        db.close()
