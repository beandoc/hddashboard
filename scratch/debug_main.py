
import sys
import os
from sqlalchemy.orm import Session
from datetime import datetime

# Mock the environment
sys.path.append('/Users/sachinsrivastava/Downloads/HD Dashboard')
from database import SessionLocal, Patient, MonthlyRecord
from dashboard_logic import get_current_month_str

db = SessionLocal()
try:
    _current_month = get_current_month_str()
    active_patient_ids = {p.id for p in db.query(Patient).filter(Patient.is_active == True).all()}
    entered_ids = {r.patient_id for r in db.query(MonthlyRecord).filter(MonthlyRecord.record_month == _current_month).all()}
    pending_entry_count = len(active_patient_ids - entered_ids)
    print(f"Pending count: {pending_entry_count}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
