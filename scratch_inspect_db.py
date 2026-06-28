import sys
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from database import SessionRecord, Patient

engine = create_engine("sqlite:///hd_dashboard.db")
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

print("--- Monthly counts of SessionRecords ---")
rows = db.query(SessionRecord.record_month, func.count(SessionRecord.id)).group_by(SessionRecord.record_month).all()
for row in rows:
    print(f"Month: {row[0]}, Count: {row[1]}")

print("\n--- Current active patients count ---")
active_count = db.query(Patient).filter(Patient.is_active == True).count()
print(f"Active patients: {active_count}")

# Check for a specific month, e.g. the latest one
if rows:
    latest_month = max(r[0] for r in rows if r[0])
    print(f"\n--- Patient session counts for {latest_month} ---")
    session_counts = (
        db.query(SessionRecord.patient_id, Patient.name, func.count(SessionRecord.id))
        .join(Patient, SessionRecord.patient_id == Patient.id)
        .filter(SessionRecord.record_month == latest_month)
        .group_by(SessionRecord.patient_id, Patient.name)
        .all()
    )
    for pid, name, count in session_counts[:15]:
        print(f"Patient {pid} ({name}): {count} sessions")
    print(f"Total patients with sessions in {latest_month}: {len(session_counts)}")
db.close()
