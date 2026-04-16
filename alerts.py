"""
Alerting module — WhatsApp (Twilio) + Email (smtplib)
Configure via .env file — no credentials hardcoded.
"""
import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ── CONFIGURATION (from .env) ──────────────────────────────────────────────
TWILIO_SID          = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH         = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WA_FROM      = os.getenv("TWILIO_WHATSAPP_FROM", "")   # e.g. whatsapp:+14155238886
TWILIO_TEMPLATE_SID = os.getenv("TWILIO_TEMPLATE_SID", "")    # approved template SID (optional)

SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")         # Gmail: use App Password
DOCTOR_EMAIL  = os.getenv("DOCTOR_EMAIL", "")          # ward report recipient
CLINIC_NAME   = os.getenv("CLINIC_NAME", "CH(SC) Nephrology")


def build_whatsapp_message(patient_name: str, alerts: list, month_label: str) -> str:
    """Build the WhatsApp alert message text."""
    alert_text = ", ".join(a.split(" ", 1)[-1] for a in alerts)  # strip emoji prefix
    return (
        f"Dear {patient_name},\n\n"
        f"Your HD review for *{month_label}* has flagged the following:\n"
        f"• {alert_text}\n\n"
        f"Please contact the {CLINIC_NAME} team for a review and follow-up.\n\n"
        f"Thank you."
    )


def build_schedule_message(patient_name: str, slots: list) -> str:
    """Build the WhatsApp schedule reminder message."""
    slot_text = "\n".join([f"• {s}" for s in slots if s])
    return (
        f"Dear {patient_name},\n\n"
        f"This is a reminder of your weekly dialysis schedule at *{CLINIC_NAME}*:\n"
        f"{slot_text}\n\n"
        f"Please ensure you arrive 15 minutes prior to your slot. If you cannot attend, please inform us in advance.\n\n"
        f"Thank you."
    )


def send_whatsapp(to_number: str, message: str) -> tuple[bool, str]:
    """
    Send a WhatsApp message via Twilio.
    to_number: patient's number, e.g. '9665183839' (will be prefixed with +91)
    Returns (success, status_message)
    """
    if not TWILIO_SID or not TWILIO_AUTH or not TWILIO_WA_FROM:
        logger.warning("Twilio credentials not configured in .env")
        return False, "Twilio not configured"

    try:
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_AUTH)

        # Normalise number to E.164 with India country code
        number = to_number.strip().replace(" ", "").replace("-", "")
        if not number.startswith("+"):
            number = "+91" + number.lstrip("0")

        msg = client.messages.create(
            from_=TWILIO_WA_FROM,           # e.g. "whatsapp:+14155238886"
            to=f"whatsapp:{number}",
            body=message,
        )
        logger.info(f"WhatsApp sent to {number} — SID: {msg.sid}")
        return True, msg.sid

    except Exception as e:
        logger.error(f"WhatsApp send failed to {to_number}: {e}")
        return False, str(e)


def send_bulk_whatsapp_alerts(alert_patients: list, month_label: str) -> dict:
    """
    Send WhatsApp alerts to all flagged patients with notify=True.
    alert_patients: list of dicts {"patient": Patient ORM obj, "alerts": [...], "record": {...}}
    Returns summary dict.
    """
    sent, failed, skipped = 0, 0, 0
    results = []

    for ap in alert_patients:
        patient = ap["patient"]

        if not patient.whatsapp_notify:
            skipped += 1
            continue

        if not patient.contact_no:
            skipped += 1
            results.append({"name": patient.name, "status": "skipped — no number"})
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


# ── EMAIL ──────────────────────────────────────────────────────────────────

def build_ward_report_html(alert_patients: list, month_label: str, year: str) -> str:
    """Build an HTML ward report email."""
    rows = ""
    for ap in alert_patients:
        p = ap["patient"]
        alerts_html = "".join(
            f'<span style="display:inline-block;background:#ffe6e6;color:#c62828;'
            f'border:1px solid #ffcccc;border-radius:3px;padding:1px 6px;'
            f'margin:1px;font-size:12px">{a}</span>'
            for a in ap["alerts"]
        )
        rows += f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;font-weight:500">{p.name}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#888;font-size:12px">{p.hid_no}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee">{p.access_type or "—"}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee">{alerts_html}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#555;font-size:12px">{p.contact_no or "—"}</td>
        </tr>"""

    return f"""
    <html><body style="font-family:Roboto,Arial,sans-serif;background:#f4f7fa;margin:0;padding:20px">
      <div style="max-width:800px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1)">
        <div style="background:#007bff;color:#fff;padding:24px 28px">
          <h1 style="margin:0;font-size:1.4em;font-weight:700">{CLINIC_NAME}</h1>
          <p style="margin:6px 0 0;opacity:.85;font-size:0.9em">HD Patient Alert Report — {month_label} {year}</p>
        </div>
        <div style="padding:24px 28px">
          <p style="color:#555;font-size:0.9em">The following <strong>{len(alert_patients)} patients</strong> have active alerts requiring clinical review:</p>
          <table style="width:100%;border-collapse:collapse;font-size:0.88em;margin-top:16px">
            <thead>
              <tr style="background:#007bff;color:#fff">
                <th style="padding:10px 12px;text-align:left">Patient</th>
                <th style="padding:10px 12px;text-align:left">HID</th>
                <th style="padding:10px 12px;text-align:left">Access</th>
                <th style="padding:10px 12px;text-align:left">Alerts</th>
                <th style="padding:10px 12px;text-align:left">Contact</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
          <p style="color:#888;font-size:0.78em;margin-top:24px">
            Generated: {datetime.now().strftime("%d %b %Y %H:%M")} — {CLINIC_NAME} HD Dashboard
          </p>
        </div>
      </div>
    </body></html>
    """


def send_critical_hb_alert(patient_name: str, hb_level: float) -> tuple[bool, str]:
    """Send an immediate emergency email for Hb <= 7.0."""
    target_email = "chiin.says@gmail.com"
    if not SMTP_USER or not SMTP_PASSWORD:
        return False, "SMTP credentials missing"

    try:
        msg = MIMEMultipart()
        msg["Subject"] = f"CRITICAL ALERT: Low Hemoglobin ({hb_level}) - {patient_name}"
        msg["From"]    = f"HD Dashboard Alert <{SMTP_USER}>"
        msg["To"]      = target_email
        
        body = (
            f"Hello Doctor,\n\n"
            f"A critical hemoglobin value has been entered for the following patient:\n\n"
            f"Patient Name: {patient_name}\n"
            f"Hemoglobin Level: {hb_level}\n\n"
            f"Kindly verify reports and review immediately.\n\n"
            f"---\n"
            f"HD Dashboard Clinical Safeguard"
        )
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, target_email, msg.as_string())

        logger.info(f"🚨 CRITICAL ALERT SENT for {patient_name} (Hb: {hb_level})")
        return True, "Alert Sent"
    except Exception as e:
        logger.error(f"Failed to send critical alert: {e}")
        return False, str(e)


def send_ward_email(alert_patients: list, month_label: str, year: str) -> tuple[bool, str]:
    """Send ward report email to the doctor/admin address."""
    if not SMTP_USER or not SMTP_PASSWORD or not DOCTOR_EMAIL:
        return False, "Email credentials not configured in .env"

    try:
        html_body = build_ward_report_html(alert_patients, month_label, year)
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"HD Alert Report — {month_label} {year} [{len(alert_patients)} patients]"
        msg["From"]    = SMTP_USER
        msg["To"]      = DOCTOR_EMAIL
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, DOCTOR_EMAIL, msg.as_string())

        logger.info(f"Ward report email sent to {DOCTOR_EMAIL}")
        return True, f"Email sent to {DOCTOR_EMAIL}"
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False, str(e)
