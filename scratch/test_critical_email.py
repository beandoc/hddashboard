"""
Diagnostic script for critical lab email alerts.
Run locally: python3 scratch/test_critical_email.py
Or add SMTP creds in .env first.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

import smtplib, logging
logging.basicConfig(level=logging.DEBUG)

SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
DOCTOR_EMAIL  = os.getenv("DOCTOR_EMAIL", "chiin.says@gmail.com")

print("\n── Env Check ──────────────────────────────────")
print(f"SMTP_USER     : {SMTP_USER!r}")
print(f"SMTP_PASSWORD : {'SET (' + str(len(SMTP_PASSWORD)) + ' chars)' if SMTP_PASSWORD else 'NOT SET ⚠'}")
print(f"SMTP_HOST     : {SMTP_HOST}")
print(f"SMTP_PORT     : {SMTP_PORT}")
print(f"DOCTOR_EMAIL  : {DOCTOR_EMAIL!r}")

if not SMTP_USER or not SMTP_PASSWORD:
    print("\n❌ SMTP credentials not set — email will be silently dropped.")
    print("   Fix: Set SMTP_USER and SMTP_PASSWORD in Render env vars.")
    print("   Gmail users: generate a 16-char App Password at:")
    print("   https://myaccount.google.com/apppasswords")
    sys.exit(1)

# Check if patient has mail_trigger set
print("\n── Patient mail_trigger Check ─────────────────")
try:
    from database import SessionLocal, Patient
    db = SessionLocal()
    patients = db.query(Patient).filter(Patient.mail_trigger == True, Patient.is_active == True).all()
    print(f"Patients with mail_trigger=True: {len(patients)}")
    for p in patients:
        print(f"  - {p.name} ({p.hid_no})")
    if not patients:
        print("  ⚠ No patients have mail_trigger enabled!")
        print("  Fix: Edit patient profile → check 'Enable email alerts'")
    db.close()
except Exception as e:
    print(f"  DB error: {e}")

# Try sending a real test email
print("\n── SMTP Connection Test ───────────────────────")
try:
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.set_debuglevel(1)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        print(f"\n✅ SMTP login successful as {SMTP_USER}")
except smtplib.SMTPAuthenticationError:
    print("\n❌ SMTP Auth Error — wrong App Password or 2FA not enabled")
    print("   Gmail: go to https://myaccount.google.com/apppasswords")
except Exception as e:
    print(f"\n❌ SMTP connection error: {e}")

# Simulate a critical lab check
print("\n── Simulated Critical Lab Alert ──────────────")
from alerts import check_critical_labs, send_critical_lab_alert_email

test_data = {
    "hb": 5.5,           # Critical low < 6.0
    "serum_potassium": 6.8,  # Critical high > 6.5
    "albumin": 1.8,      # Critical low < 2.0
}
hits = check_critical_labs(test_data)
print(f"Critical hits from test data: {[h['text'] for h in hits]}")

if hits:
    print(f"Firing test email to {DOCTOR_EMAIL}...")
    send_critical_lab_alert_email(
        patient_name="TEST PATIENT",
        hid="HID-TEST",
        month_label="May 2026",
        critical_hits=hits,
        entered_by="diagnostic_script"
    )
    import time; time.sleep(3)  # wait for threading
    print("✅ Email fired — check inbox at", DOCTOR_EMAIL)
