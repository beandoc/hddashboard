
import sys
import os
import logging

# Mock the environment to run the logic
sys.path.append('/Users/sachinsrivastava/Downloads/HD Dashboard')
from database import SessionLocal
from dashboard_logic import compute_dashboard

logging.basicConfig(level=logging.INFO)

db = SessionLocal()
try:
    data = compute_dashboard(db, "2026-05")
    print("Success!")
    print(f"Missing Records Count: {data['metrics']['missing_records']['count']}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
