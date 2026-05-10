
import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add the project directory to sys.path
sys.path.append('/Users/sachinsrivastava/Downloads/HD Dashboard')

from database import ResearchRecord, Patient, SessionLocal

db = SessionLocal()

try:
    # 1. Delete dummy data for Ajit Shinde
    ajit = db.query(Patient).filter(Patient.name == "Ajit Shinde").first()
    if ajit:
        deleted_count = db.query(ResearchRecord).filter(ResearchRecord.patient_id == ajit.id).delete()
        db.commit()
        print(f"✅ Deleted {deleted_count} research records for Ajit Shinde (ID: {ajit.id}).")
    else:
        print("❌ Patient Ajit Shinde not found.")

    # 2. Check for Ganesh Balgude data
    ganesh = db.query(Patient).filter(Patient.name == "Ganesh Balgude").first()
    if ganesh:
        ganesh_records = db.query(ResearchRecord).filter(ResearchRecord.patient_id == ganesh.id).all()
        if ganesh_records:
            print(f"✅ Found {len(ganesh_records)} research records for Ganesh Balgude:")
            for r in ganesh_records:
                print(f"  - [{r.test_type}] on {r.test_date}: {r.data}")
        else:
            print("⚠️ No research records found for Ganesh Balgude in ResearchRecord table.")
            
            # Maybe it's in DryWeightAssessment?
            from database import DryWeightAssessment
            dw_records = db.query(DryWeightAssessment).filter(DryWeightAssessment.patient_id == ganesh.id).all()
            if dw_records:
                print(f"✅ Found {len(dw_records)} Dry Weight Assessments for Ganesh Balgude.")
            else:
                print("⚠️ No Dry Weight Assessments found for Ganesh Balgude.")
    else:
        print("❌ Patient Ganesh Balgude not found.")

finally:
    db.close()
