from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
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

    # Batch-load all monthly records for this month once — avoids N+1 in both loops below
    active = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    _all_month_recs = db.query(MonthlyRecord).filter(
        MonthlyRecord.patient_id.in_([p.id for p in active]),
        MonthlyRecord.record_month == month_str,
    ).all()
    _month_rec_map = {r.patient_id: r for r in _all_month_recs}

    alert_links = []
    for ap in alert_patients:
        p = ap["patient"]
        if not p.contact_no: continue
        rec_obj = _month_rec_map.get(p.id)
        link = build_individual_whatsapp_link(p, rec_obj, month_label)
        alert_links.append({
            "id": p.id,
            "name": p.name, "hid": p.hid_no, "contact": p.contact_no,
            "alerts": ap["alerts"], "link": link,
        })

    # 2. Get schedule links
    schedule_links = []
    for p in active:
        if not p.contact_no: continue
        rec_obj = _month_rec_map.get(p.id)
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

    # 4. Circuit pressure alerts (early access failure detection)
    pressure_alerts = []
    try:
        from dashboard_logic import _fetch_recent_n_sessions
        from services.pressure_analysis import compute_fleet_pressure_signals
        recent_sessions = _fetch_recent_n_sessions(db, [p.id for p in active], n=8)
        pressure_signals = compute_fleet_pressure_signals(db, active, recent_sessions)
        pressure_alerts = [s for s in pressure_signals if s.max_risk in ("alert", "warning")]
    except Exception:
        logger.exception("Pressure alert computation failed — skipping section")

    return templates.TemplateResponse("alerts.html", {
        "request": request, "alert_links": alert_links,
        "schedule_links": schedule_links,
        "clinical_reminders": clinical_reminders,
        "pressure_alerts": pressure_alerts,
        "patients": active,
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
async def api_send_whatsapp_bulk(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    month_str = month or get_current_month_str()
    try:
        body = {}
        try:
            body = await request.json()
        except Exception:
            pass
        
        patient_ids = body.get("patient_ids")
        patients = get_patients_needing_alerts(db, month_str)
        if patient_ids is not None:
            patients = [p for p in patients if p["patient"].id in patient_ids]
            
        result = send_bulk_whatsapp_alerts(patients, get_month_label(month_str))
        
        if result.get("mode") == "links":
            # For each patient in filtered set, generate success/fail status
            results = []
            for p_info in patients:
                p = p_info["patient"]
                if p.contact_no:
                    results.append({
                        "id": p.id,
                        "name": p.name,
                        "status": "success",
                        "detail": f"Simulated: Message prepared for {p.contact_no}"
                    })
                else:
                    results.append({
                        "id": p.id,
                        "name": p.name,
                        "status": "failed",
                        "detail": "No contact number on file"
                    })
            return JSONResponse(content={
                "status": "success",
                "mode": "simulated",
                "message": f"Simulated dispatch for {len(patients)} patients.",
                "results": results
            })
        else:
            enriched_results = []
            for res in result.get("results", []):
                matching_p = next((p_info["patient"] for p_info in patients if p_info["patient"].name == res["name"]), None)
                enriched_results.append({
                    "id": matching_p.id if matching_p else None,
                    "name": res["name"],
                    "status": res["status"],
                    "detail": f"Twilio status: {res['status']}"
                })
            return JSONResponse(content={
                "status": "success",
                "mode": "twilio",
                "message": result.get("message"),
                "results": enriched_results
            })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/send-email")
async def api_send_email_bulk(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    month_str = month or get_current_month_str()
    try:
        body = {}
        try:
            body = await request.json()
        except Exception:
            pass
            
        patient_ids = body.get("patient_ids")
        patients = get_patients_needing_alerts(db, month_str)
        if patient_ids is not None:
            patients = [p for p in patients if p["patient"].id in patient_ids]
            
        if not patients:
            return JSONResponse(content={"status": "success", "message": "No patients selected or no alerts found."})
            
        success, detail = send_ward_email(patients, get_month_label(month_str), month_str[:4])
        if not success:
            from alerts import SMTP_USER, SMTP_PASSWORD
            if not SMTP_USER or not SMTP_PASSWORD:
                return JSONResponse(content={
                    "status": "success",
                    "mode": "simulated",
                    "message": f"✅ [Simulated] Email ward report prepared for {len(patients)} patients (SMTP not configured)."
                })
            raise HTTPException(status_code=500, detail=detail)
        return JSONResponse(content={"status": "success", "mode": "smtp", "message": f"✅ {detail}"})
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


@router.get("/test-email")
async def test_email_config():
    """
    Diagnostic endpoint — sends a test email and returns the result.
    Visit /alerts/test-email to check SMTP config on Render.
    """
    import os, smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from alerts import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, DOCTOR_EMAIL, CLINIC_NAME
    from datetime import datetime

    checks = {
        "SMTP_HOST":     SMTP_HOST     or "❌ NOT SET",
        "SMTP_PORT":     str(SMTP_PORT),
        "SMTP_USER":     SMTP_USER     or "❌ NOT SET",
        "SMTP_PASSWORD": ("✅ SET (" + str(len(SMTP_PASSWORD)) + " chars)") if SMTP_PASSWORD else "❌ NOT SET (email will never send)",
        "DOCTOR_EMAIL":  DOCTOR_EMAIL  or "❌ NOT SET",
    }

    send_result = None
    send_error  = None

    if SMTP_USER and SMTP_PASSWORD and DOCTOR_EMAIL:
        try:
            html = f"""
            <div style="font-family:Arial,sans-serif;max-width:480px;margin:24px auto;
                        padding:24px;border:2px solid #22c55e;border-radius:8px">
              <h2 style="color:#16a34a;margin:0 0 12px">✅ SMTP Test — {CLINIC_NAME}</h2>
              <p style="color:#374151">This is a test email sent at
                <strong>{datetime.now().strftime("%d %b %Y %H:%M:%S")}</strong>
                to confirm your SMTP configuration is working correctly on Render.</p>
              <p style="color:#374151">If you received this, critical lab alert emails
                will deliver when staff save panic-level values.</p>
              <hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0"/>
              <p style="font-size:12px;color:#9ca3af">
                From: {SMTP_USER} → To: {DOCTOR_EMAIL}
              </p>
            </div>"""
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[TEST] SMTP config verified — {CLINIC_NAME} HD Dashboard"
            msg["From"]    = SMTP_USER
            msg["To"]      = DOCTOR_EMAIL
            msg.attach(MIMEText(html, "html"))
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, DOCTOR_EMAIL, msg.as_string())
            send_result = f"✅ Test email sent to {DOCTOR_EMAIL} — check inbox (and spam folder)"
        except smtplib.SMTPAuthenticationError:
            send_error = (
                "❌ Gmail authentication failed.\n"
                "You must use a Google App Password, not your regular password.\n"
                "Steps: Google Account → Security → 2-Step Verification → App Passwords → "
                "create one for 'Mail' and paste the 16-char code as SMTP_PASSWORD in Render."
            )
        except Exception as exc:
            send_error = f"❌ SMTP error: {exc}"
    else:
        send_error = "❌ Cannot send — one or more credentials are missing (see config checks above)"

    # Return a plain HTML diagnostic page
    rows = "".join(
        f'<tr><td style="padding:6px 12px;color:#64748b;font-size:13px">{k}</td>'
        f'<td style="padding:6px 12px;font-family:monospace;font-size:13px">{v}</td></tr>'
        for k, v in checks.items()
    )
    result_html = (
        f'<div style="background:#f0fdf4;border:1px solid #86efac;border-radius:6px;'
        f'padding:14px 18px;margin-top:20px;color:#166534">{send_result}</div>'
        if send_result else
        f'<div style="background:#fef2f2;border:1px solid #fca5a5;border-radius:6px;'
        f'padding:14px 18px;margin-top:20px;color:#991b1b;white-space:pre-wrap">{send_error}</div>'
    )

    html_page = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"/>
    <title>Email Config Test</title></head>
    <body style="font-family:'Segoe UI',Arial,sans-serif;background:#f8fafc;padding:32px">
    <div style="max-width:580px;margin:0 auto;background:#fff;border-radius:10px;
                padding:28px;box-shadow:0 2px 8px rgba(0,0,0,.08)">
      <h2 style="margin:0 0 20px;color:#0f172a">📧 SMTP / Email Config Diagnostic</h2>
      <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;
                    border-radius:6px;overflow:hidden">
        <thead>
          <tr style="background:#f1f5f9">
            <th style="padding:8px 12px;text-align:left;font-size:11px;color:#64748b;
                       text-transform:uppercase">Variable</th>
            <th style="padding:8px 12px;text-align:left;font-size:11px;color:#64748b;
                       text-transform:uppercase">Status</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
      {result_html}
      <p style="margin-top:20px;font-size:12px;color:#94a3b8">
        Render env vars: Dashboard → your service → Environment → Edit variables
      </p>
    </div>
    </body></html>"""

    return HTMLResponse(content=html_page)


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
    db.refresh(new_rem)
    return JSONResponse(content={"status": "success", "id": new_rem.id})

@router.post("/reminders/{reminder_id}/complete")
async def complete_reminder(reminder_id: int, db: Session = Depends(get_db)):
    rem = db.query(PatientReminder).filter(PatientReminder.id == reminder_id).first()
    if not rem: raise HTTPException(status_code=404)
    rem.is_completed = True
    db.commit()
    return JSONResponse(content={"status": "success"})
