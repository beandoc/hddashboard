
import os
import sys
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.append(os.getcwd())

load_dotenv()

from alerts import send_entry_alert_email

def test_ajit_shinde_alert():
    patient_name = "Ajit Shinde"
    hid = "400040426619"
    month_label = "May 2026"
    alerts = ["Low Hb (5.0 g/dL) - CRITICAL"]
    labs = {
        "hb": 5.0,
        "albumin": 3.2,
        "phosphorus": 4.5,
        "corrected_ca": 8.8,
        "idwg": 1.5,
        "ipth": 250
    }
    entered_by = "Antigravity Test Script"

    print(f"Attempting to send critical alert email for {patient_name}...")
    print(f"Recipient (DOCTOR_EMAIL): {os.getenv('DOCTOR_EMAIL')}")
    print(f"Sender (SMTP_USER): {os.getenv('SMTP_USER')}")
    
    # We call the function. Note that it starts a background thread.
    send_entry_alert_email(
        patient_name=patient_name,
        hid=hid,
        month_label=month_label,
        alerts=alerts,
        labs=labs,
        entered_by=entered_by
    )
    
    print("Email trigger function called. Check logs for success/failure.")

if __name__ == "__main__":
    test_ajit_shinde_alert()
