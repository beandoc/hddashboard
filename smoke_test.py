import sys
import os
import json
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add current directory to path
sys.path.append(os.getcwd())

from main import app
from database import Base, engine, Patient, MonthlyRecord, get_db, User, to_dict
from dashboard_logic import compute_dashboard

print("🔍 Starting Clinical Smoke Test...")

# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./smoke_test.db"
test_engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

try:
    print("1. Testing Imports & Model Integrity...")
    Base.metadata.create_all(bind=test_engine)
    print("✅ Models mapped to database successfully.")

    print("2. Testing Patient CRUD & Data Entry Flow...")
    client = TestClient(app)
    
    # Mock admin user for session-based auth
    # Note: We skip the actual login check here by mocking the user in request state if needed,
    # or just creating a real one and logging in.
    db = TestingSessionLocal()
    from config import pwd_context
    if not db.query(User).filter(User.username == "smoke_admin").first():
        db.add(User(username="smoke_admin", hashed_password=pwd_context.hash("smoke123"), role="admin"))
        db.commit()
    
    # Login
    response = client.post("/login", data={"username": "smoke_admin", "password": "smoke123"}, follow_redirects=True)
    assert response.status_code == 200
    print("✅ Login successful.")

    # Create Patient
    patient_data = {
        "name": "Smoke Test Patient",
        "hid_no": "SMOKE001",
        "sex": "Male",
        "age": 45,
        "contact_no": "1234567890",
        "access_type": "AVF",
        "dry_weight": 70.0
    }
    response = client.post("/patients/register", data=patient_data, follow_redirects=True)
    assert response.status_code == 200
    print("✅ Patient registration successful.")

    # Data Entry
    p = db.query(Patient).filter(Patient.hid_no == "SMOKE001").first()
    month_str = datetime.now().strftime("%Y-%m")
    record_data = {
        "patient_id": p.id,
        "month": month_str,
        "hb": 9.5,
        "albumin": 2.0,
        "calcium": 7.5,
        "phosphorus": 6.0,
        "tsat": 20.0,
        "idwg": 3.0
    }
    response = client.post("/entry/save", data=record_data, follow_redirects=True)
    assert response.status_code == 200
    print("✅ Clinical data entry successful.")

    print("3. Testing Dashboard Update & Alerts...")
    data = compute_dashboard(db, month_str)
    patient_row = next((r for r in data["patient_rows"] if r["hid"] == "SMOKE001"), None)
    assert patient_row is not None
    assert "High Phos" in patient_row["alerts"]
    assert "Low Albumin" in patient_row["alerts"]
    print("✅ Dashboard alerts correctly triggered.")

    print("4. Testing Streaming Backup Integrity...")
    response = client.get("/admin/db/export")
    assert response.status_code == 200
    backup_data = response.json()
    assert "patients" in backup_data
    assert len(backup_data["patients"]) > 0
    print("✅ Streaming backup returns valid JSON.")

    print("\n🚀 SMOKE TEST PASSED: Application is ready for Render deployment.")

except Exception as e:
    print(f"\n❌ SMOKE TEST FAILED: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    if os.path.exists("./smoke_test.db"):
        os.remove("./smoke_test.db")
