import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 1. Test DB setup and monkeypatching SessionLocal BEFORE importing app
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

import database
database.SessionLocal = TestingSessionLocal

from main import app
import main
main.SessionLocal = TestingSessionLocal
main._check_schema_version = lambda: None

from database import Base, get_db, User, Patient, InterimLabRecord, MonthlyRecord
from passlib.context import CryptContext
from fastapi.testclient import TestClient

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)
    # Create a test user
    db = TestingSessionLocal()
    if not db.query(User).filter(User.username == "testadmin").first():
        hashed_pw = pwd_context.hash("password123")
        user = User(username="testadmin", full_name="Test Admin", hashed_password=hashed_pw, role="admin", is_active=True)
        db.add(user)
        db.commit()
    db.close()

    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)

def test_login_and_access_dashboard(client):
    # Bypass login and set session cookie directly
    import time
    from config import serializer
    token = serializer.dumps(f"staff:testadmin:{int(time.time())}")
    client.cookies.set("hd_session", token)
    response = client.get("/")
    assert response.status_code == 200
    assert "Dashboard" in response.text

def test_api_patients_search(client):
    # Bypass login and set session cookie directly
    import time
    from config import serializer
    token = serializer.dumps(f"staff:testadmin:{int(time.time())}")
    client.cookies.set("hd_session", token)
    
    response = client.get("/api/v1/patients?q=test")
    assert response.status_code == 200
    assert "patients" in response.json()

def test_api_dashboard_month(client):
    # Bypass login and set session cookie directly
    import time
    from config import serializer
    token = serializer.dumps(f"staff:testadmin:{int(time.time())}")
    client.cookies.set("hd_session", token)
    response = client.get("/api/v1/dashboard?month=2026-04")
    assert response.status_code == 200
    assert "data" in response.json()

def test_patients_page_renders_with_csrf_token(client):
    import time
    from config import serializer
    token = serializer.dumps(f"staff:testadmin:{int(time.time())}")
    client.cookies.set("hd_session", token)
    response = client.get("/patients")
    assert response.status_code == 200
    assert 'name="csrf_token"' in response.text

def test_mortality_risk_pagination(client):
    import time
    from config import serializer
    token = serializer.dumps(f"staff:testadmin:{int(time.time())}")
    client.cookies.set("hd_session", token)
    
    # Test main page access
    response = client.get("/analytics/mortality-risk?page=1&limit=10&tier=all&search=")
    assert response.status_code == 200
    assert "Mortality Risk" in response.text
    
    # Test out-of-bounds page query parameters
    response = client.get("/analytics/mortality-risk?page=9999&limit=10&tier=all&search=")
    assert response.status_code == 200
    assert "Mortality Risk" in response.text


def test_export_definitions_json(client):
    import time
    from config import serializer
    token = serializer.dumps(f"staff:testadmin:{int(time.time())}")
    client.cookies.set("hd_session", token)

    response = client.get("/variables/export/definitions?format=json")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    data = response.json()
    assert isinstance(data, list)
    assert any(d["name"] == "hb" for d in data)


def test_export_definitions_csv(client):
    import time
    from config import serializer
    token = serializer.dumps(f"staff:testadmin:{int(time.time())}")
    client.cookies.set("hd_session", token)

    response = client.get("/variables/export/definitions?format=csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment; filename=clinical_variable_definitions.csv" in response.headers["content-disposition"]
    assert "name,display_name" in response.text


def test_export_values_json(client):
    import time
    from config import serializer
    token = serializer.dumps(f"staff:testadmin:{int(time.time())}")
    client.cookies.set("hd_session", token)

    response = client.get("/variables/export/values?format=json")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    data = response.json()
    assert isinstance(data, list)


def test_export_values_csv(client):
    import time
    from config import serializer
    token = serializer.dumps(f"staff:testadmin:{int(time.time())}")
    client.cookies.set("hd_session", token)

    response = client.get("/variables/export/values?format=csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment; filename=patient_variables_data.csv" in response.headers["content-disposition"]
    assert "patient_id,patient_name" in response.text


def test_admin_backup_includes_variables(client):
    import time
    from config import serializer
    token = serializer.dumps(f"staff:testadmin:{int(time.time())}")
    client.cookies.set("hd_session", token)

    response = client.get("/admin/db/export")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    data = response.json()
    assert "variable_definitions" in data
    assert isinstance(data["variable_definitions"], list)


def test_at_risk_trends_interim_and_month_override(client):
    import time
    from config import serializer
    from database import Patient, InterimLabRecord, SessionLocal
    
    # 1. Create a test patient with interim record for Hb out-of-range (e.g. 5.9)
    db = SessionLocal()
    patient = Patient(name="Joyla", hid_no="J001", is_active=True)
    db.add(patient)
    db.commit()
    patient_id = patient.id
    
    from datetime import date
    interim = InterimLabRecord(
        patient_id=patient_id,
        parameter="hb",
        value=5.9,
        record_month="2026-06",
        lab_date=date(2026, 6, 5)
    )
    db.add(interim)
    db.commit()
    db.close()
    
    # 2. Query legacy at-risk trends API for parameter=hb and month=2026-06
    token = serializer.dumps(f"staff:testadmin:{int(time.time())}")
    client.cookies.set("hd_session", token)
    response = client.get("/analytics/api/at-risk-trends?parameter=hb&month=2026-06")
    assert response.status_code == 200
    
    data = response.json()
    assert "patients" in data
    patients_list = data["patients"]
    
    # Verify patient Joyla is returned in the list (because she is at risk)
    joyla_entries = [p for p in patients_list if p["name"] == "Joyla"]
    assert len(joyla_entries) == 1
    
    # Verify the trend contains the 5.9 interim lab value for 2026-06
    joyla_entry = joyla_entries[0]
    assert joyla_entry["trend"][-1] == 5.9
    
    # Clean up
    db = SessionLocal()
    db.query(InterimLabRecord).filter(InterimLabRecord.patient_id == patient_id).delete()
    db.query(Patient).filter(Patient.id == patient_id).delete()
    db.commit()
    db.close()

