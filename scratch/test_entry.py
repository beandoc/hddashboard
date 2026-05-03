import os
import sys
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

# Add current directory to path
sys.path.append(os.getcwd())

from database import Patient, MonthlyRecord, get_db, SessionLocal
from routers.entry import _build_patient_slot_info
from dashboard_logic import get_current_month_str

def test_entry_index():
    db = SessionLocal()
    try:
        month_str = get_current_month_str()
        print(f"Testing for month: {month_str}")
        
        patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
        print(f"Found {len(patients)} active patients")
        
        records = db.query(MonthlyRecord).filter(MonthlyRecord.record_month == month_str).all()
        existing_records = {r.patient_id: r for r in records}
        print(f"Found {len(records)} existing records")
        
        for p in patients:
            try:
                info = _build_patient_slot_info(p)
                # print(f"Patient {p.name}: {info}")
            except Exception as e:
                print(f"Error building slot info for {p.name}: {e}")
                raise
        
        print("Success: All patient slot info built")
    finally:
        db.close()

if __name__ == "__main__":
    test_entry_index()
