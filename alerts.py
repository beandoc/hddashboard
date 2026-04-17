"""
Alerting module
- Email via Gmail SMTP (automated, works on Render)
- WhatsApp via pre-filled wa.me links (manual trigger, no ban risk)
"""
import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ── CONFIG ──────────────────────────────────────────────────────────────────
SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
DOCTOR_EMAIL  = os.getenv("DOCTOR_EMAIL", "chiin.says@gmail.com")
CLINIC_NAME   = os.getenv("CLINIC_NAME", "CH(SC) Nephrology")

# Twilio (optional — only used if credentials present)
TWILIO_SID     = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH    = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WA_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "")


# ── WHATSAPP LINK GENERATOR ─────────────────────────────────────────────────

def build_whatsapp_message(patient_name: str, alerts: list,
                            month_label: str, lab_values: dict = None) -> str:
    """Build WhatsApp alert message text with critical lab values."""
    alert_text = "\n".join(f"• {a}" for a in alerts)

    lab_section = ""
    if lab_values:
        critical_labs = []
        if lab_values.get("hb"):
            critical_labs.append(f"Hb: {lab_values['hb']} g/dL")
        if lab_values.get("albumin"):
            critical_labs.append(f"Albumin: {lab_values['albumin']} g/dL")
        if lab_values.get("phosphorus"):
            critical_labs.append(f"Phosphorus: {lab_values['phosphorus']} mg/dL")
        if lab_values.get("corrected_ca"):
            critical_labs.append(f"Corrected Ca: {lab_values['corrected_ca']} mg/dL")
        if lab_values.get("ipth"):
            critical_labs.append(f"iPTH: {lab_values['ipth']} pg/mL")
        if lab_values.get("idwg"):
            critical_labs.append(f"IDWG: {lab_values['idwg']} kg")
        if critical_labs:
            lab_section = "\n\nCurrent values:\n" + "\n".join(f"  {l}" for l in critical_labs)

    return (
        f"Dear {patient_name},\n\n"
        f"Your HD review ({month_label}) at {CLINIC_NAME} "
        f"has flagged the following:\n"
        f"{alert_text}"
        f"{lab_section}\n\n"
        f"Please contact the nephrology team for follow-up.\n"
        f"Thank you."
    )


def generate_whatsapp_link(contact_no: str, message: str) -> str:
    """
    Generate a wa.me pre-filled message link.
    Clicking this opens WhatsApp with the message ready to send.
    No API, no ban risk.
    """
    number = contact_no.strip().replace(" ", "").replace("-", "")
    if not number.startswith("+"):
        number = "+91" + number.lstrip("0")
    # Remove the + for wa.me format
    number = number.lstrip("+")
    encoded_message = quote(message)
    return f"https://wa.me/{number}?text={encoded_message}"


def generate_all_whatsapp_links(alert_patients: list, month_label: str) -> list:
    """
    Generate WhatsApp links for all alert patients.
    Returns list of dicts with patient name, alerts, and clickable link.
    """
    links = []
    for ap in alert_patients:
        patient = ap["patient"]
        if not patient.whatsapp_notify or not patient.contact_no:
            continue

        lab_values = {
            "hb": ap["record"].get("hb"),
            "albumin": ap["record"].get("albumin"),
            "phosphorus": ap["record"].get("phosphorus"),
            "corrected_ca": ap["record"].get("corrected_ca"),
            "ipth": ap["record"].get("ipth"),
            "idwg": ap["record"].get("idwg"),
        }

        message = build_whatsapp_message(
            patient.name, ap["alerts"], month_label, lab_values
        )
        link = generate_whatsapp_link(patient.contact_no, message)

        links.append({
            "name": patient.name,
            "hid": patient.hid_no,
            "contact": patient.contact_no,
            "alerts": ap["alerts"],
            "whatsapp_link": link,
            "message_preview": message,
        })

    return links


# ── TWILIO (optional fallback) ───────────────────────────────────────────────

def send_whatsapp_twilio(to_number: str, message: str) -> tuple:
    """Send via Twilio if credentials configured. Returns (success, detail)."""
    if not TWILIO_SID or not TWILIO_AUTH or not TWILIO_WA_FROM:
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
        return True, msg.sid
    except Exception as e:
        logger.error(f"Twilio failed: {e}")
        return False, str(e)


def send_bulk_whatsapp_alerts(alert_patients: list, month_label: str) -> dict:
    """
    If Twilio configured: send automatically.
    If not: return wa.me links for manual sending.
    """
    if TWILIO_SID and TWILIO_AUTH and TWILIO_WA_FROM:
        # Automated Twilio send
        sent, failed, skipped = 0, 0, 0
        results = []
        for ap in alert_patients:
            patient = ap["patient"]
            if not patient.whatsapp_notify:
                skipped += 1
                continue
            if not patient.contact_no:
                skipped += 1
                continue
            rec = ap.get("record", {})
            message = build_whatsapp_message(
                patient.name, ap["alerts"], month_label, rec)
            success, detail = send_whatsapp_twilio(patient.contact_no, message)
            if success:
                sent += 1
                results.append({"name": patient.name, "status": "sent"})
            else:
                failed += 1
                results.append({"name": patient.name, "status": "failed"})
        return {
            "mode": "twilio",
            "sent": sent, "failed": failed, "skipped": skipped,
            "message": f"Twilio: {sent} sent, {failed} failed.",
            "results": results,
        }
    else:
        # Fallback: generate wa.me links
        links = generate_all_whatsapp_links(alert_patients, month_label)
        return {
            "mode": "links",
            "links": links,
            "message": f"{len(links)} WhatsApp messages ready to send.",
        }


# ── EMAIL ────────────────────────────────────────────────────────────────────

def build_ward_report_html(alert_patients: list,
                            month_label: str, year: str) -> str:
    """Build comprehensive HTML ward report with critical lab values."""
    rows = ""
    for ap in alert_patients:
        p = ap["patient"]
        rec = ap.get("record", {})

        alerts_html = "".join(
            f'<span style="display:inline-block;background:#ffe6e6;'
            f'color:#c62828;border:1px solid #ffcccc;border-radius:3px;'
            f'padding:1px 6px;margin:1px;font-size:11px">{a}</span>'
            for a in ap["alerts"]
        )

        def fmt(val, unit="", decimals=1):
            if val is None:
                return '<span style="color:#bbb">—</span>'
            return f"{round(float(val), decimals)} {unit}".strip()

        def cell_color(val, low=None, high=None):
            if val is None:
                return "#fff"
            try:
                v = float(val)
                if low and v < low:
                    return "#fff0f0"
                if high and v > high:
                    return "#fff0f0"
                return "#f0fff4"
            except:
                return "#fff"

        hb    = rec.get("hb")
        alb   = rec.get("albumin")
        phos  = rec.get("phosphorus")
        ca    = rec.get("corrected_ca")
        idwg  = rec.get("idwg")
        ipth  = rec.get("ipth")

        wa_message = build_whatsapp_message(
            p.name, ap["alerts"], month_label,
            {"hb": hb, "albumin": alb, "phosphorus": phos,
             "corrected_ca": ca, "ipth": ipth, "idwg": idwg}
        )
        wa_link = generate_whatsapp_link(
            p.contact_no, wa_message) if p.contact_no else "#"

        rows += f"""
        <tr>
          <td style="padding:10px 12px;border-bottom:1px solid #eee;
              font-weight:600;white-space:nowrap">{p.name}<br>
            <span style="font-size:11px;color:#999;font-weight:400">
              {p.hid_no}</span></td>
          <td style="padding:10px 12px;border-bottom:1px solid #eee;
              font-size:12px">{p.access_type or "—"}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #eee;
              background:{cell_color(hb, low=10)};
              text-align:center;font-family:monospace">
              {fmt(hb, 'g/dL')}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #eee;
              background:{cell_color(alb, low=3.5)};
              text-align:center;font-family:monospace">
              {fmt(alb, 'g/dL')}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #eee;
              background:{cell_color(phos, high=5.5)};
              text-align:center;font-family:monospace">
              {fmt(phos, 'mg/dL')}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #eee;
              background:{cell_color(ca, low=8.5)};
              text-align:center;font-family:monospace">
              {fmt(ca, 'mg/dL')}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #eee;
              background:{cell_color(idwg, high=2.5)};
              text-align:center;font-family:monospace">
              {fmt(idwg, 'kg')}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #eee">
              {alerts_html}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #eee;
              text-align:center">
            {'<a href="' + wa_link + '" style="background:#25d366;color:#fff;'
             'padding:4px 10px;border-radius:4px;text-decoration:none;'
             'font-size:12px">📲 Send</a>'
             if p.contact_no else "—"}
          </td>
        </tr>"""

    generated = datetime.now().strftime("%d %b %Y %H:%M")
    total = len(alert_patients)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"/>
<style>
  body {{ font-family: Arial, sans-serif; background: #f4f7fa;
         margin: 0; padding: 20px; }}
  .wrap {{ max-width: 1000px; margin: 0 auto; background: #fff;
           border-radius: 8px; overflow: hidden;
           box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
  .hdr {{ background: #007bff; color: #fff; padding: 24px 28px; }}
  .hdr h1 {{ margin: 0; font-size: 1.4em; }}
  .hdr p {{ margin: 6px 0 0; opacity: .85; font-size: 0.9em; }}
  .body {{ padding: 24px 28px; }}
  .summary {{ display: flex; gap: 16px; margin-bottom: 24px; }}
  .stat {{ background: #f8f9fa; border-radius: 8px; padding: 14px 20px;
           text-align: center; flex: 1; }}
  .stat .num {{ font-size: 2em; font-weight: bold; color: #007bff; }}
  .stat .lbl {{ font-size: 0.78em; color: #666; margin-top: 2px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.85em; }}
  thead tr {{ background: #007bff; color: #fff; }}
  th {{ padding: 10px 12px; text-align: left; font-size: 0.75em;
        text-transform: uppercase; letter-spacing: 0.05em; white-space:nowrap; }}
  .footer {{ color: #999; font-size: 0.75em; margin-top: 20px;
             text-align: center; }}
  .wa-note {{ background: #f0fff4; border: 1px solid #b3dfd8;
              border-radius: 6px; padding: 12px 16px; margin-bottom: 20px;
              font-size: 0.85em; color: #2e7d32; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="hdr">
    <h1>{CLINIC_NAME} — HD Alert Report</h1>
    <p>{month_label} {year} &nbsp;·&nbsp; Generated {generated}</p>
  </div>
  <div class="body">
    <div class="summary">
      <div class="stat">
        <div class="num">{total}</div>
        <div class="lbl">Patients with Alerts</div>
      </div>
      <div class="stat">
        <div class="num">{sum(1 for a in alert_patients
                            if any("Hb" in x for x in a["alerts"]))}</div>
        <div class="lbl">Hb Alerts</div>
      </div>
      <div class="stat">
        <div class="num">{sum(1 for a in alert_patients
                            if any("Albumin" in x for x in a["alerts"]))}</div>
        <div class="lbl">Albumin Alerts</div>
      </div>
      <div class="stat">
        <div class="num">{sum(1 for a in alert_patients
                            if any("Phos" in x for x in a["alerts"]))}</div>
        <div class="lbl">Phosphorus Alerts</div>
      </div>
    </div>

    <div class="wa-note">
      📲 <strong>WhatsApp Links Included:</strong> Click the green
      "Send" button next to each patient to open WhatsApp with a
      pre-written message. No app required — works from any device.
    </div>

    <table>
      <thead>
        <tr>
          <th>Patient</th><th>Access</th>
          <th>Hb</th><th>Albumin</th><th>Phos</th>
          <th>Ca(corr)</th><th>IDWG</th>
          <th>Alerts</th><th>WhatsApp</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>

    <p class="footer">
      {CLINIC_NAME} HD Dashboard &nbsp;·&nbsp;
      Confidential — for clinical use only
    </p>
  </div>
</div>
</body></html>"""


def send_ward_email(alert_patients: list,
                    month_label: str, year: str) -> tuple:
    """Send ward report email with embedded WhatsApp links."""
    if not SMTP_USER or not SMTP_PASSWORD:
        return False, "Email not configured — add SMTP_USER and SMTP_PASSWORD in Render environment"

    recipient = DOCTOR_EMAIL
    if not recipient:
        return False, "DOCTOR_EMAIL not set in environment"

    try:
        html_body = build_ward_report_html(alert_patients, month_label, year)
        msg = MIMEMultipart("alternative")
        msg["Subject"] = (
            f"HD Alert Report — {month_label} {year} "
            f"[{len(alert_patients)} patients] | {CLINIC_NAME}"
        )
        msg["From"]    = SMTP_USER
        msg["To"]      = recipient
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, recipient, msg.as_string())

        logger.info(f"Ward email sent to {recipient}")
        return True, f"Email sent to {recipient}"
    except smtplib.SMTPAuthenticationError:
        return False, (
            "Gmail authentication failed. "
            "Use an App Password, not your Gmail password. "
            "Go to Google Account → Security → 2FA → App Passwords"
        )
    except Exception as e:
        logger.error(f"Email failed: {e}")
        return False, str(e)
