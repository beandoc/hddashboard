"""
Alerting module — WhatsApp (Twilio) + Email (smtplib) + Clinical Sentinels
Configure via .env file — no credentials hardcoded.
"""
import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ── CONFIGURATION (from .env) ──────────────────────────────────────────────
TWILIO_SID     = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH    = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WA_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "")
SMTP_HOST      = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT      = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER      = os.getenv("SMTP_USER", "")
SMTP_PASSWORD  = os.getenv("SMTP_PASSWORD", "")
DOCTOR_EMAIL   = os.getenv("DOCTOR_EMAIL", "")
CLINIC_NAME    = os.getenv("CLINIC_NAME", "CH(SC) Nephrology")


def build_whatsapp_message(patient_name: str, alerts: list, month_label: str) -> str:
    """Build the WhatsApp alert message text."""
    alert_text = ", ".join(a.split(" ", 1)[-1] for a in alerts)
    return (
        f"Dear {patient_name},\n\n"
        f"Your HD review for *{month_label}* has flagged: {alert_text}.\n\n"
        f"Please contact {CLINIC_NAME} for follow-up.\n\nThank you."
    )


def build_schedule_message(patient_name: str, slots: list) -> str:
    """Build the trilingual WhatsApp schedule message."""
    from alerts import get_date_for_slot
    dates = [f"{get_date_for_slot(s)} ({s})" for s in slots if s and s != "No Slot"]
    if not dates: return f"Hello {patient_name}, clinical slots TBD."
    
    dates_str = "\n".join([f" • {d}" for d in dates])
    return (
        f"Dear {patient_name},\n\n"
        f"Please find your HD slot details for this week:\n"
        f"इस हफ्ते के लिए ये एचडी स्लॉट की तारीखें हैं:\n"
        f"कृपया या आठवड्याचा एचडी स्लॉट तपशील पहा:\n\n"
        f"{dates_str}\n\n"
        f"Regards, Nephrology Dept."
    )


def send_whatsapp(to_number: str, message: str) -> tuple:
    """Send WhatsApp via Twilio. Returns (success: bool, detail: str)."""
    if not TWILIO_SID or not TWILIO_AUTH or not TWILIO_WA_FROM:
        logger.warning("Twilio credentials not configured")
        return False, "Twilio not configured"

    try:
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_AUTH)
        number = to_number.strip().replace(" ", "").replace("-", "")
        if not number.startswith("+"):
            number = "+91" + number.lstrip("0")
        msg = client.messages.create(
            from_=TWILIO_WA_FROM,
            to=f"whatsapp:{number}",
            body=message,
        )
        logger.info(f"WhatsApp sent to {number} SID={msg.sid}")
        return True, msg.sid
    except Exception as e:
        logger.error(f"WhatsApp failed to {to_number}: {e}")
        return False, str(e)


def send_bulk_whatsapp_alerts(alert_patients: list, month_label: str) -> dict:
    """Send WhatsApp to all flagged patients with notify=True."""
    sent, failed, skipped = 0, 0, 0
    results = []

    for ap in alert_patients:
        patient = ap["patient"]

        if not patient.whatsapp_notify:
            skipped += 1
            continue

        if not patient.contact_no:
            skipped += 1
            results.append({"name": patient.name, "status": "skipped-no-number"})
            continue

        message = build_whatsapp_message(patient.name, ap["alerts"], month_label)
        success, detail = send_whatsapp(patient.contact_no, message)

        if success:
            sent += 1
            results.append({"name": patient.name, "status": "sent", "sid": detail})
        else:
            failed += 1
            results.append({"name": patient.name, "status": "failed", "error": detail})

    return {
        "sent": sent,
        "failed": failed,
        "skipped": skipped,
        "results": results,
        "message": f"WhatsApp: {sent} sent, {failed} failed, {skipped} skipped.",
    }


def build_ward_report_html(alert_patients: list, month_label: str, year: str) -> str:
    """Build HTML ward report for email."""
    rows = ""
    for ap in alert_patients:
        p = ap["patient"]
        alerts_html = "".join(
            f'<span style="display:inline-block;background:#ffe6e6;color:#c62828;'
            f'border:1px solid #ffcccc;border-radius:3px;padding:1px 6px;'
            f'margin:1px;font-size:12px">{a}</span>'
            for a in ap["alerts"]
        )
        rows += (
            f"<tr>"
            f'<td style="padding:8px 12px;border-bottom:1px solid #eee;font-weight:500">{p.name}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #eee;color:#888;font-size:12px">{p.hid_no}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #eee">{p.access_type or "-"}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #eee">{alerts_html}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #eee;color:#555;font-size:12px">{p.contact_no or "-"}</td>'
            f"</tr>"
        )

    generated = datetime.now().strftime("%d %b %Y %H:%M")
    return f"""<html><body style="font-family:Arial,sans-serif;background:#f4f7fa;margin:0;padding:20px">
<div style="max-width:800px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1)">
  <div style="background:#007bff;color:#fff;padding:24px 28px">
    <h1 style="margin:0;font-size:1.4em">{CLINIC_NAME}</h1>
    <p style="margin:6px 0 0;opacity:.85">HD Alert Report — {month_label} {year}</p>
  </div>
  <div style="padding:24px 28px">
    <p style="color:#555">{len(alert_patients)} patients require clinical review:</p>
    <table style="width:100%;border-collapse:collapse;font-size:0.88em;margin-top:16px">
      <thead><tr style="background:#007bff;color:#fff">
        <th style="padding:10px 12px;text-align:left">Patient</th>
        <th style="padding:10px 12px;text-align:left">HID</th>
        <th style="padding:10px 12px;text-align:left">Access</th>
        <th style="padding:10px 12px;text-align:left">Alerts</th>
        <th style="padding:10px 12px;text-align:left">Contact</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
    <p style="color:#888;font-size:0.78em;margin-top:24px">Generated: {generated} — {CLINIC_NAME}</p>
  </div>
</div>
</body></html>"""


def send_ward_email(alert_patients: list, month_label: str, year: str) -> tuple:
    """Send ward report email. Returns (success: bool, detail: str)."""
    if not SMTP_USER or not SMTP_PASSWORD or not DOCTOR_EMAIL:
        return False, "Email not configured in .env"

    try:
        html_body = build_ward_report_html(alert_patients, month_label, year)
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"HD Alert Report — {month_label} {year} [{len(alert_patients)} patients]"
        msg["From"] = SMTP_USER
        msg["To"] = DOCTOR_EMAIL
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, DOCTOR_EMAIL, msg.as_string())

        logger.info(f"Ward email sent to {DOCTOR_EMAIL}")
        return True, f"Email sent to {DOCTOR_EMAIL}"
    except Exception as e:
        logger.error(f"Email failed: {e}")
        return False, str(e)


def send_critical_clinical_alert(patient_name: str, marker_name: str, value: float) -> tuple:
    """Send an immediate emergency alert for life-threatening lab values."""
    target_email = "chiin.says@gmail.com"
    if not SMTP_USER or not SMTP_PASSWORD:
        return False, "SMTP credentials missing"

    try:
        msg = MIMEMultipart()
        msg["Subject"] = f"🚨 CRITICAL CLINICAL ALERT: {marker_name} ({value}) - {patient_name}"
        msg["From"]    = f"{CLINIC_NAME} Sentinel <{SMTP_USER}>"
        msg["To"]      = target_email
        
        body = (
            f"Hello Doctor,\n\n"
            f"A CRITICAL clinical value has been detected for the following patient:\n\n"
            f"Patient Name: {patient_name}\n"
            f"Clinical Parameter: {marker_name}\n"
            f"Entered Value: {value}\n\n"
            f"Kindly verify reports and review immediately. This value exceeds safe ward thresholds.\n\n"
            f"---\n"
            f"HD Dashboard Clinical Sentinel"
        )
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, target_email, msg.as_string())

        logger.info(f"🚨 CRITICAL ALERT SENT: {patient_name} | {marker_name}: {value}")
        return True, "Alert Sent"
    except Exception as e:
        logger.error(f"Failed to send critical alert: {e}")
        return False, str(e)


def get_date_for_slot(slot_str: str) -> str:
    """Convert 'Mon Morning' to '10 Apr' format for the current week."""
    import calendar
    from datetime import timedelta
    days_map = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
    
    try:
        day_part = slot_str.split(" ")[0]
        target_weekday = days_map.get(day_part, 0)
        today = datetime.now()
        # Find the Monday of this week
        monday = today - timedelta(days=today.weekday())
        target_date = monday + timedelta(days=target_weekday)
        return target_date.strftime("%d %b")
    except:
        return "TBD"


def send_schedule_email(patient_name: str, email: str, slots: list) -> tuple:
    """Send a trilingual (En/Hi/Mr) HD schedule to a patient."""
    if not SMTP_USER or not SMTP_PASSWORD or not email:
        return False, "Missing credentials or email"

    try:
        dates = [f"{get_date_for_slot(s)} ({s})" for s in slots if s and s != "No Slot"]
        if not dates: return False, "No valid slots"

        dates_str = "\n".join([f" • {d}" for d in dates])
        
        msg = MIMEMultipart()
        msg["Subject"] = f"Your Hemodialysis Schedule / एचडी स्लॉट का विवरण - {patient_name}"
        msg["From"]    = f"{CLINIC_NAME} <{SMTP_USER}>"
        msg["To"]      = email

        body = (
            f"Dear {patient_name},\n\n"
            f"Please find your HD slot details for this week:\n"
            f"इस हफ्ते के लिए ये एचडी स्लॉट की तारीखें हैं:\n"
            f"कृपया या आठवड्याचा एचडी स्लॉट तपशील पहा:\n\n"
            f"{dates_str}\n\n"
            f"Regards, \n"
            f"Nephrology Dept, {CLINIC_NAME}\n"
        )
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, email, msg.as_string())

        return True, "Schedule sent"
    except Exception as e:
        logger.error(f"Failed to send schedule: {e}")
        return False, str(e)
