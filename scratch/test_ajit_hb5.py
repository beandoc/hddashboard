
import os
import sys
import time
from dotenv import load_dotenv
from sqlalchemy.orm import Session

# Add project root to sys.path
sys.path.append(os.getcwd())

load_dotenv()

from database import SessionLocal, Patient, MonthlyRecord
from services.entry_service import save_monthly_record

def test_ajit_shinde_hb5():
    db = SessionLocal()
    try:
        # 1. Find or create Ajit Shinde
        patient = db.query(Patient).filter(Patient.name == "Ajit Shinde").first()
        if not patient:
            print("Patient Ajit Shinde not found. Creating...")
            # This is a fallback, but he should exist based on my previous query.
            return

        # 2. Ensure mail_trigger is True for the test
        original_mail_trigger = patient.mail_trigger
        patient.mail_trigger = True
        db.commit()
        print(f"Set mail_trigger=True for {patient.name}")

        # 3. Simulate saving a monthly record with Hb=5
        data = {
            "month_str": "2026-05",
            "hb": 5.0,
            "albumin": 3.0,
            "phosphorus": 4.0,
            "calcium": 8.5,
            "idwg": 1.2,
            "dry_weight": 65.0,
            "entered_by": "Automated Test"
        }
        
        print(f"Triggering save_monthly_record for {patient.name} with Hb=5.0...")
        
        # Override DOCTOR_EMAIL for this test if needed, 
        # but the user said "to chiin.says" which is the default anyway.
        
        save_monthly_record(db, patient.id, data)
        
        print("Trigger function called. Since it runs in a background thread, check logs.")
        print("Waiting 5 seconds to allow background thread to attempt sending...")
        time.sleep(5)
        
        # 4. Restore original mail_trigger if desired
        # patient.mail_trigger = original_mail_trigger
        # db.commit()
        
    finally:
        db.close()

if __name__ == "__main__":
    test_ajit_shinde_hb5()
