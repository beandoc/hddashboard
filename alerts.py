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
from datetime import datetime, date, timedelta
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ── CONFIG ──────────────────────────────────────────────────────────────────
SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "nephrochsc@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
DOCTOR_EMAIL  = os.getenv("DOCTOR_EMAIL", "chiin.says@gmail.com")
CLINIC_NAME   = os.getenv("CLINIC_NAME", "CH(SC) Nephrology")
CLINIC_PHONE  = os.getenv("CLINIC_PHONE", "9665183839")   # WhatsApp Business number

# Twilio (optional — only used if credentials present)
TWILIO_SID     = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH    = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WA_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "")


# ── HD SCHEDULE HELPERS ─────────────────────────────────────────────────────

_DAY_MAP = {
    "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
    "Friday": 4, "Saturday": 5, "Sunday": 6,
}

def compute_upcoming_sessions(patient, from_date=None):
    """
    Return list of (session_date, day_name, shift) for the patient's next
    scheduled sessions, all on or after from_date (default: today).
    Based on patient.hd_day_1/2/3 (day-of-week names) and hd_slot_1/2/3.
    Days that don't parse as a weekday name are skipped.
    """
    if from_date is None:
        from_date = date.today()

    sessions = []
    for day_attr, slot_attr in [
        ("hd_day_1", "hd_slot_1"),
        ("hd_day_2", "hd_slot_2"),
        ("hd_day_3", "hd_slot_3"),
    ]:
        day_name = (getattr(patient, day_attr, None) or "").strip()
        shift    = (getattr(patient, slot_attr, None) or "").strip()
        if day_name not in _DAY_MAP:
            continue
        days_ahead = (_DAY_MAP[day_name] - from_date.weekday()) % 7
        sess_date  = from_date + timedelta(days=days_ahead)
        sessions.append((sess_date, day_name, shift))

    sessions.sort(key=lambda x: x[0])
    return sessions


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
            critical_labs.append(f"Corrected Calcium: {'{:.2f}'.format(float(lab_values['corrected_ca']))} mg/dL")
        if lab_values.get("ipth"):
            critical_labs.append(f"iPTH: {lab_values['ipth']} pg/mL")
        if lab_values.get("idwg") is not None:
            critical_labs.append(f"Interdialytic Weight Gain: {'{:.2f}'.format(float(lab_values['idwg']))} kg")
        if critical_labs:
            lab_section = "\n\nCurrent values:\n" + "\n".join(f"  {l}" for l in critical_labs)

    return (
        f"Dear {patient_name},\n\n"
        f"Your HD review from Nephrology Dept CH(SC)\n"
        f"has flagged the following:\n"
        f"{alert_text}"
        f"{lab_section}\n\n"
        f"Please contact the nephrology team for follow-up.\n\n"
        f"Regards\n"
        f"Thank you.\n"
        f"( This is an automated message, please dont reply)"
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
    # Using web.whatsapp.com format to force it to open in the browser tab
    return f"https://web.whatsapp.com/send?phone={number}&text={encoded_message}"


def build_schedule_message(patient_name: str, sessions: list,
                            remarks: str = None) -> str:
    """
    Build the HD schedule WhatsApp message for one patient.
    sessions = list of (session_date, day_name, shift) tuples from
               compute_upcoming_sessions(); only future dates are included.
    """
    if sessions:
        lines = []
        for sess_date, day_name, shift in sessions:
            lines.append(f"  • {day_name} {sess_date.strftime('%d %b %Y')}")
        schedule_text = "\n".join(lines)
    else:
        schedule_text = "  • (Schedule to be confirmed)"

    remarks_section = ""
    if remarks and remarks.strip():
        remarks_section = f"\n\nDoctor's Note:\n  {remarks.strip()}"

    return (
        f"Dear {patient_name},\n\n"
        f"Your Hemodialysis Schedule at Dialysis centre CHSC\n"
        f"{schedule_text}"
        f"{remarks_section}\n\n"
        f"Please report 15 minutes before your session.\n"
        f" \n"
        f"Thank you.\n"
        f"(Note : This is an automated message. Please dont reply)"
    )


def send_whatsapp(contact_no: str, message: str) -> tuple:
    """
    Return a wa.me link for the given contact and message.
    When opened on the clinic phone (WhatsApp Business), the message
    is sent FROM the clinic TO the patient.
    Returns (True, wa_me_url).
    """
    link = generate_whatsapp_link(contact_no, message)
    return True, link


def build_individual_whatsapp_link(patient, record, month_label: str) -> str:
    """
    Build a complete one-to-one wa.me link for a patient that includes:
      - Clinical alerts (if any)
      - HD schedule slots
      - Doctor's remarks from the monthly record
    """
    alerts = []
    if record:
        from dashboard_logic import _resolve_epo_dose

        raw_access = (getattr(record, "access_type", "") or "").strip()
        access = "Permacath" if raw_access in ("P/Cath", "P-Cath", "Permacath", "PCATH") else raw_access
        if access and access.upper() != "AVF":
            alerts.append("Non-AVF Access")
        if record.idwg and record.idwg > 2.5:
            alerts.append(f"High Interdialytic Weight Gain ({record.idwg} kg)")
            
        if record.albumin and record.albumin < 2.5:
            alerts.append(f"Low Albumin ({record.albumin} g/dL)")
            
        _corr_ca = (record.calcium + 0.8 * (4.0 - record.albumin)) if (record.calcium and record.albumin) else record.calcium
        if _corr_ca and _corr_ca < 8.0:
            alerts.append(f"Low Corrected Calcium ({'{:.2f}'.format(float(_corr_ca))} mg/dL)")
            
        if record.phosphorus and record.phosphorus > 5.5:
            alerts.append(f"High Phosphorus ({record.phosphorus} mg/dL)")
            
        _epo_sc = _resolve_epo_dose(record)
        if _epo_sc and record.hb:
            _weight = record.target_dry_weight or patient.dry_weight or 60.0
            _dose_kg = _epo_sc / _weight
            _eri = _dose_kg / (record.hb * 10)
            if _eri >= 2.0 or _dose_kg >= 450:
                alerts.append(f"ESA Hypo-response [HypoR1] (Hb {record.hb} g/dL)")
            elif _eri >= 1.5:
                alerts.append(f"ESA Hypo-response [HypoR2] (Hb {record.hb} g/dL)")

    upcoming = compute_upcoming_sessions(patient)
    if upcoming:
        lines = []
        for sess_date, day_name, shift in upcoming:
            lines.append(f"  • {day_name} {sess_date.strftime('%d %b %Y')}")
        schedule_text = "\n".join(lines)
    else:
        schedule_text = "  • (To be confirmed)"

    remarks = (getattr(record, "issues", None) or "").strip() if record else ""

    alert_section = ""
    if alerts:
        alert_text = "\n".join(f"  ⚠ {a}" for a in alerts)
        alert_section = (
            f"\n🔔 Clinical Alerts ({month_label}):\n"
            f"{alert_text}\n"
            f"Please contact the nephrology team for follow-up.\n"
        )

    remarks_section = f"\nDoctor's Note:\n  {remarks}\n" if remarks else ""

    message = (
        f"Dear {patient.name},\n\n"
        f"Your HD review from Nephrology Dept CH(SC)\n"
        f"{alert_section}"
        f"\n📅 Your HD Schedule:\n"
        f"{schedule_text}\n"
        f"{remarks_section}\n"
        f"Regards\n"
        f"Thank you.\n"
        f"( This is an automated message, please dont reply)"
    )
    return generate_whatsapp_link(patient.contact_no, message) if patient.contact_no else "#"


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
            return "{:.{}f} {}".format(float(val), decimals, unit).strip()

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
              {fmt(ca, 'mg/dL', decimals=2)}</td>
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
          <th>Calcium(corr)</th><th>Int.Wt.Gain</th>
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


def send_reminders_digest_email(reminders: list) -> tuple:
    """
    Send a single composite email listing all pending clinical reminders.
    reminders: list of PatientReminder ORM objects (is_completed=False).
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        return False, "Email not configured — add SMTP_USER and SMTP_PASSWORD"
    if not DOCTOR_EMAIL:
        return False, "DOCTOR_EMAIL not set in environment"
    if not reminders:
        return False, "No pending reminders to send"

    from datetime import date
    today = date.today()

    due = [r for r in reminders if r.reminder_date <= today]
    upcoming = [r for r in reminders if r.reminder_date > today]

    def _reminder_row(r, is_due: bool):
        badge_bg   = "#dc2626" if is_due else "#64748b"
        badge_text = "DUE" if is_due else "UPCOMING"
        date_str   = r.reminder_date.strftime("%d %b %Y")
        return (
            f'<tr style="border-bottom:1px solid #f1f5f9">'
            f'<td style="padding:10px 14px;font-weight:600;white-space:nowrap">'
            f'  {r.patient.name}'
            f'  <span style="font-size:11px;color:#94a3b8;font-weight:400"> #{r.patient.hid_no}</span>'
            f'</td>'
            f'<td style="padding:10px 14px;white-space:nowrap;font-size:13px;color:#475569">{date_str}</td>'
            f'<td style="padding:10px 14px">'
            f'  <span style="background:{badge_bg};color:#fff;border-radius:10px;'
            f'    padding:2px 9px;font-size:11px;font-weight:700">{badge_text}</span>'
            f'</td>'
            f'<td style="padding:10px 14px;font-size:13px;color:#334155;line-height:1.5">{r.message}</td>'
            f'</tr>'
        )

    due_rows      = "".join(_reminder_row(r, True)  for r in due)
    upcoming_rows = "".join(_reminder_row(r, False) for r in upcoming)

    section_due = ""
    if due_rows:
        section_due = f"""
        <h3 style="margin:24px 0 10px;font-size:15px;color:#dc2626">
          &#9888;&#65039; Due Reminders ({len(due)})
        </h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px;
                      border:1px solid #fee2e2;border-radius:8px;overflow:hidden">
          <thead>
            <tr style="background:#fee2e2">
              <th style="padding:8px 14px;text-align:left;color:#991b1b;font-size:12px">Patient</th>
              <th style="padding:8px 14px;text-align:left;color:#991b1b;font-size:12px">Date</th>
              <th style="padding:8px 14px;text-align:left;color:#991b1b;font-size:12px">Status</th>
              <th style="padding:8px 14px;text-align:left;color:#991b1b;font-size:12px">Reminder</th>
            </tr>
          </thead>
          <tbody>{due_rows}</tbody>
        </table>"""

    section_upcoming = ""
    if upcoming_rows:
        section_upcoming = f"""
        <h3 style="margin:24px 0 10px;font-size:15px;color:#0369a1">
          &#128197; Upcoming Reminders ({len(upcoming)})
        </h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px;
                      border:1px solid #bae6fd;border-radius:8px;overflow:hidden">
          <thead>
            <tr style="background:#e0f2fe">
              <th style="padding:8px 14px;text-align:left;color:#0369a1;font-size:12px">Patient</th>
              <th style="padding:8px 14px;text-align:left;color:#0369a1;font-size:12px">Date</th>
              <th style="padding:8px 14px;text-align:left;color:#0369a1;font-size:12px">Status</th>
              <th style="padding:8px 14px;text-align:left;color:#0369a1;font-size:12px">Reminder</th>
            </tr>
          </thead>
          <tbody>{upcoming_rows}</tbody>
        </table>"""

    generated = datetime.now().strftime("%d %b %Y %H:%M")
    html = f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:680px;margin:0 auto">
      <div style="background:linear-gradient(135deg,#0f172a,#1e293b);
                  padding:24px 28px;border-radius:10px 10px 0 0">
        <h2 style="color:#fff;margin:0;font-size:18px">
          &#128203; Clinical Reminders Digest
        </h2>
        <p style="color:rgba(255,255,255,0.65);margin:6px 0 0;font-size:13px">
          {len(reminders)} pending reminder{'s' if len(reminders)!=1 else ''} &nbsp;&middot;&nbsp;
          Generated {generated}
        </p>
      </div>
      <div style="background:#fff;padding:20px 28px;
                  border:1px solid #e2e8f0;border-top:none">
        <div style="display:flex;gap:16px;margin-bottom:20px">
          <div style="flex:1;background:#fff0f0;border:1px solid #fee2e2;
                      border-radius:8px;padding:14px 18px;text-align:center">
            <div style="font-size:2em;font-weight:700;color:#dc2626">{len(due)}</div>
            <div style="font-size:11px;color:#991b1b;margin-top:2px;font-weight:600">DUE</div>
          </div>
          <div style="flex:1;background:#f0f9ff;border:1px solid #bae6fd;
                      border-radius:8px;padding:14px 18px;text-align:center">
            <div style="font-size:2em;font-weight:700;color:#0369a1">{len(upcoming)}</div>
            <div style="font-size:11px;color:#0369a1;margin-top:2px;font-weight:600">UPCOMING</div>
          </div>
          <div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;
                      border-radius:8px;padding:14px 18px;text-align:center">
            <div style="font-size:2em;font-weight:700;color:#475569">{len(reminders)}</div>
            <div style="font-size:11px;color:#64748b;margin-top:2px;font-weight:600">TOTAL PENDING</div>
          </div>
        </div>
        {section_due}
        {section_upcoming}
      </div>
      <div style="background:#f8fafc;padding:14px 28px;border:1px solid #e2e8f0;
                  border-top:none;border-radius:0 0 10px 10px">
        <p style="margin:0;font-size:12px;color:#94a3b8">
          {CLINIC_NAME} &middot; HD Dashboard automated digest &middot; Do not reply
        </p>
      </div>
    </div>"""

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = (
            f"Clinical Reminders Digest — {len(due)} Due, {len(upcoming)} Upcoming | {CLINIC_NAME}"
        )
        msg["From"] = SMTP_USER
        msg["To"]   = DOCTOR_EMAIL
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, DOCTOR_EMAIL, msg.as_string())

        logger.info(f"Reminders digest sent to {DOCTOR_EMAIL} ({len(reminders)} reminders)")
        return True, f"Digest sent to {DOCTOR_EMAIL} — {len(due)} due, {len(upcoming)} upcoming"
    except smtplib.SMTPAuthenticationError:
        return False, (
            "Gmail authentication failed. "
            "Use an App Password — Google Account → Security → 2FA → App Passwords"
        )
    except Exception as e:
        logger.error(f"Reminders digest email failed: {e}")
        return False, str(e)


def send_entry_alert_email(patient_name: str, hid: str, month_label: str,
                            alerts: list, labs: dict, entered_by: str = "") -> None:
    """
    Fire-and-forget email triggered immediately when staff saves a monthly record
    that has one or more critical flags. Runs in a background thread so it never
    delays the HTTP response.
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        return
    if not alerts:
        return

    def _send():
        try:
            alert_pills = "".join(
                f'<span style="display:inline-block;background:#fee2e2;color:#991b1b;'
                f'border-radius:4px;padding:3px 10px;margin:3px;font-size:12px;'
                f'font-weight:600">{a}</span>'
                for a in alerts
            )

            def _row(label, val, unit="", warn=False, decimals=1):
                bg = "#fff0f0" if warn and val is not None else "#f9fafb"
                display = "{:.{}f} {}".format(float(val), decimals, unit).strip() if val is not None else "—"
                return (f'<tr><td style="padding:8px 12px;color:#64748b;font-size:13px">{label}</td>'
                        f'<td style="padding:8px 12px;background:{bg};font-family:monospace;'
                        f'font-weight:600;font-size:13px">{display}</td></tr>')

            lab_rows = (
                _row("Haemoglobin", labs.get("hb"), "g/dL", warn=(labs.get("hb") or 99) < 10) +
                _row("Albumin", labs.get("albumin"), "g/dL", warn=(labs.get("albumin") or 99) < 2.5) +
                _row("Phosphorus", labs.get("phosphorus"), "mg/dL", warn=(labs.get("phosphorus") or 0) > 5.5) +
                _row("Corrected Calcium", labs.get("corrected_ca"), "mg/dL", warn=(labs.get("corrected_ca") or 99) < 8.0, decimals=2) +
                _row("Interdialytic Weight Gain", labs.get("idwg"), "kg", warn=(labs.get("idwg") or 0) > 2.5, decimals=2) +
                _row("iPTH", labs.get("ipth"), "pg/mL")
            )

            html = f"""
            <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:560px;margin:0 auto">
              <div style="background:linear-gradient(135deg,#0f172a,#1e293b);padding:24px 28px;border-radius:10px 10px 0 0">
                <h2 style="color:#fff;margin:0;font-size:18px">⚠️ HD Alert — {patient_name}</h2>
                <p style="color:rgba(255,255,255,0.65);margin:6px 0 0;font-size:13px">
                  HID {hid} &nbsp;·&nbsp; {month_label} &nbsp;·&nbsp; Entered by: {entered_by or 'staff'}
                </p>
              </div>
              <div style="background:#fff;padding:20px 28px;border:1px solid #e2e8f0;border-top:none">
                <p style="margin:0 0 14px;font-size:14px;color:#374151">
                  Critical flags detected when record was saved:
                </p>
                <div style="margin-bottom:20px">{alert_pills}</div>
                <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">
                  <thead>
                    <tr style="background:#f1f5f9">
                      <th style="padding:8px 12px;text-align:left;font-size:12px;color:#64748b;text-transform:uppercase">Parameter</th>
                      <th style="padding:8px 12px;text-align:left;font-size:12px;color:#64748b;text-transform:uppercase">Value</th>
                    </tr>
                  </thead>
                  <tbody>{lab_rows}</tbody>
                </table>
              </div>
              <div style="background:#f8fafc;padding:14px 28px;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 10px 10px">
                <p style="margin:0;font-size:12px;color:#94a3b8">
                  {CLINIC_NAME} · HD Dashboard automated alert · Do not reply
                </p>
              </div>
            </div>
            """

            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"⚠️ HD Alert: {patient_name} — {', '.join(alerts[:3])} | {month_label}"
            msg["From"] = SMTP_USER
            msg["To"] = DOCTOR_EMAIL

            msg.attach(MIMEText(html, "html"))
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, DOCTOR_EMAIL, msg.as_string())
            logger.info(f"Entry alert email sent for {patient_name} → {DOCTOR_EMAIL}")
        except Exception as e:
            logger.error(f"Entry alert email failed for {patient_name}: {e}")

    import threading
    threading.Thread(target=_send, daemon=True).start()
