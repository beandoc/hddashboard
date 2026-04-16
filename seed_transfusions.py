"""
seed_transfusions.py
====================
Seeds blood transfusion logs from a CSV file.
CSV format: hid_no, name, transfusion_date (YYYY-MM-DD), units, reason
"""
import sys
import os
import argparse
import csv
from datetime import datetime

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import SessionLocal, Patient, BloodTransfusion

def seed_transfusions(filepath: str):
    db = SessionLocal()
    print(f"\nHD Dashboard — Transfusion Seeder")
    print(f"File: {filepath}\n")

    count = 0
    try:
        with open(filepath, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                hid = row.get("hid_no", "").strip()
                t_date_str = row.get("transfusion_date", "").strip()
                units = row.get("units", "1").strip()
                reason = row.get("reason", "").strip()

                if not hid or not t_date_str:
                    continue

                patient = db.query(Patient).filter(Patient.hid_no == hid).first()
                if not patient:
                    print(f"  [SKIP] Patient HID {hid} not found.")
                    continue

                t_date = datetime.strptime(t_date_str, "%Y-%m-%d").date()
                
                # Check for duplicate
                existing = db.query(BloodTransfusion).filter(
                    BloodTransfusion.patient_id == patient.id,
                    BloodTransfusion.transfusion_date == t_date
                ).first()

                if not existing:
                    new_bt = BloodTransfusion(
                        patient_id=patient.id,
                        transfusion_date=t_date,
                        units=int(float(units)),
                        reason=reason
                    )
                    db.add(new_bt)
                    count += 1
                    print(f"  [ADDED] {patient.name}: {units} unit(s) on {t_date}")

        db.commit()
        print(f"\n✅ Success: {count} transfusion logs added.")
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    args = parser.parse_args()
    seed_transfusions(args.file)
