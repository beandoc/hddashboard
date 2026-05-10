
import sys
import os
from datetime import datetime

# Mock the environment to run the logic
sys.path.append('/Users/sachinsrivastava/Downloads/HD Dashboard')
from database import SessionLocal, MonthlyRecord, Patient
from dashboard_logic import get_effective_month, get_current_month_str

db = SessionLocal()
current = get_current_month_str()
record_count = db.query(MonthlyRecord).filter(MonthlyRecord.record_month == current).count()
active_count = db.query(Patient).filter(Patient.is_active == True).count()
res_month, res_note = get_effective_month(db)

print(f"Current Month: {current}")
print(f"Record Count: {record_count}")
print(f"Active Count: {active_count}")
print(f"Effective Month: {res_month}")
print(f"Effective Note: {res_note}")

db.close()
