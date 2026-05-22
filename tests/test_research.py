import pytest
import json
import time
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# Setup database URL and engine
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

import database
database.SessionLocal = TestingSessionLocal

from main import app
import main
main.SessionLocal = TestingSessionLocal
main._check_schema_version = lambda: None

from database import Base, get_db, User, Patient, ResearchProject, ResearchRecord, MonthlyRecord
from passlib.context import CryptContext
from config import serializer

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
    db = TestingSessionLocal()
    
    # Create test users with admin and doctor roles
    if not db.query(User).filter(User.username == "res_admin").first():
        hashed_pw = pwd_context.hash("password123")
        admin = User(username="res_admin", full_name="Res Admin", hashed_password=hashed_pw, role="admin", is_active=True)
        db.add(admin)
    if not db.query(User).filter(User.username == "res_doctor").first():
        hashed_pw = pwd_context.hash("password123")
        doctor = User(username="res_doctor", full_name="Res Doctor", hashed_password=hashed_pw, role="doctor", is_active=True)
        db.add(doctor)
    if not db.query(User).filter(User.username == "res_staff").first():
        hashed_pw = pwd_context.hash("password123")
        staff = User(username="res_staff", full_name="Res Staff", hashed_password=hashed_pw, role="staff", is_active=True)
        db.add(staff)
        
    # Create two test patients
    p = Patient(name="Test Research Patient 1", hid_no="RP001", is_active=True, sex="Male", dm_status="None", htn_status=True, hd_wef_date=date(2025, 1, 1))
    p2 = Patient(name="Test Research Patient 2", hid_no="RP002", is_active=True, sex="Female", dm_status="DM", htn_status=False, hd_wef_date=date(2025, 2, 1))
    db.add_all([p, p2])
    db.commit()
    
    # Create monthly records for both patients
    r1 = MonthlyRecord(patient_id=p.id, record_month="2026-01", hb=11.2, serum_ferritin=350.0, tsat=28.0, pre_dialysis_urea=110.0, post_dialysis_urea=40.0, serum_creatinine=10.5)
    r2 = MonthlyRecord(patient_id=p.id, record_month="2026-02", hb=10.5, serum_ferritin=420.0, tsat=24.0, pre_dialysis_urea=115.0, post_dialysis_urea=42.0, serum_creatinine=11.0)
    r3 = MonthlyRecord(patient_id=p.id, record_month="2026-03", hb=12.0, serum_ferritin=510.0, tsat=32.0, pre_dialysis_urea=105.0, post_dialysis_urea=38.0, serum_creatinine=9.8)
    
    r4 = MonthlyRecord(patient_id=p2.id, record_month="2026-01", hb=10.2, serum_ferritin=290.0, tsat=20.0, pre_dialysis_urea=95.0, post_dialysis_urea=35.0, serum_creatinine=8.5)
    r5 = MonthlyRecord(patient_id=p2.id, record_month="2026-02", hb=9.8, serum_ferritin=310.0, tsat=22.0, pre_dialysis_urea=98.0, post_dialysis_urea=36.0, serum_creatinine=8.8)
    r6 = MonthlyRecord(patient_id=p2.id, record_month="2026-03", hb=10.5, serum_ferritin=330.0, tsat=21.0, pre_dialysis_urea=92.0, post_dialysis_urea=32.0, serum_creatinine=8.0)
    
    db.add_all([r1, r2, r3, r4, r5, r6])
    db.commit()
    
    db.close()

    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)

def test_research_hub_access_restricted(client):
    # Unauthenticated should redirect
    response = client.get("/research", follow_redirects=False)
    assert response.status_code == 303
    assert "/login" in response.headers.get("location", "")

def test_research_hub_and_project_lifecycle(client):
    # Log in as admin
    token = serializer.dumps(f"staff:res_admin:{int(time.time())}")
    client.cookies.set("hd_session", token)

    # 1. GET /research
    response = client.get("/research")
    assert response.status_code == 200
    assert "Research Hub" in response.text

    # 2. POST /research/projects (create project)
    response = client.post("/research/projects", data={"title": "Test Project", "description": "Testing description"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers.get("location") == "/research"

    db = TestingSessionLocal()
    project = db.query(ResearchProject).filter(ResearchProject.title == "Test Project").first()
    assert project is not None
    assert project.status == "Active"
    project_id = project.id
    db.close()

    # 3. GET /research/projects/{project_id}
    response = client.get(f"/research/projects/{project_id}")
    assert response.status_code == 200
    assert "Test Project" in response.text

    # 4. GET /research/projects/{project_id}/record
    db = TestingSessionLocal()
    patient = db.query(Patient).filter(Patient.hid_no == "RP001").first()
    patient_id = patient.id
    db.close()
    
    response = client.get(f"/research/projects/{project_id}/record?patient_id={patient_id}&test_type=HANDGRIP_STRENGTH")
    assert response.status_code == 200
    assert "Record HANDGRIP_STRENGTH" in response.text

    # 5. POST /research/projects/{project_id}/record
    # Try posting empty test-specific values first - should return 200 and error text
    response = client.post(f"/research/projects/{project_id}/record", data={
        "patient_id": patient_id,
        "test_type": "HANDGRIP_STRENGTH",
        "test_date": "2026-03-15",
        "notes": "Empty form notes"
    })
    assert response.status_code == 200
    assert "No research variable values were entered" in response.text

    # Post with correct test-specific values
    response = client.post(f"/research/projects/{project_id}/record", data={
        "patient_id": patient_id,
        "test_type": "HANDGRIP_STRENGTH",
        "test_date": "2026-03-15",
        "notes": "Testing record",
        "dominant_hand_kg": "28.5",
        "nondominant_hand_kg": "26.0"
    }, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers.get("location") == f"/research/projects/{project_id}"

    db = TestingSessionLocal()
    record = db.query(ResearchRecord).filter(ResearchRecord.project_id == project_id).first()
    assert record is not None
    assert record.test_type == "HANDGRIP_STRENGTH"
    assert record.notes == "Testing record"
    data_dict = json.loads(record.data)
    assert data_dict["dominant_hand_kg"] == "28.5"
    assert data_dict["nondominant_hand_kg"] == "26.0"
    record_id = record.id
    db.close()

    # 6. POST /research/projects/{project_id}/deactivate
    response = client.post(f"/research/projects/{project_id}/deactivate", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers.get("location") == "/research"

    db = TestingSessionLocal()
    project = db.query(ResearchProject).filter(ResearchProject.id == project_id).first()
    assert project.status == "Inactive"
    db.close()

    # 7. POST /research/projects/{project_id}/reactivate
    response = client.post(f"/research/projects/{project_id}/reactivate", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers.get("location") == "/research"

    db = TestingSessionLocal()
    project = db.query(ResearchProject).filter(ResearchProject.id == project_id).first()
    assert project.status == "Active"
    db.close()

    # 8. POST /research/projects/{project_id}/records/{record_id}/delete
    response = client.post(f"/research/projects/{project_id}/records/{record_id}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers.get("location") == f"/research/projects/{project_id}"

    db = TestingSessionLocal()
    record = db.query(ResearchRecord).filter(ResearchRecord.id == record_id).first()
    assert record is None
    db.close()

def test_research_stats_access(client):
    # Log in as doctor
    token = serializer.dumps(f"staff:res_doctor:{int(time.time())}")
    client.cookies.set("hd_session", token)

    # GET /research/stats
    response = client.get("/research/stats")
    assert response.status_code == 200
    assert "Statistical Analysis" in response.text

def test_research_stats_run_descriptive(client):
    token = serializer.dumps(f"staff:res_doctor:{int(time.time())}")
    client.cookies.set("hd_session", token)

    payload = {
        "test_type": "descriptive",
        "variable": "hb",
        "date_from": "2026-01",
        "date_to": "2026-03"
    }
    response = client.post("/research/stats/run", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["test_type"] == "descriptive"
    assert data["variable"] == "Hemoglobin"
    assert "stats" in data
    assert data["stats"]["n"] == 2
    # Note: Shapiro-Wilk requires n>=3 patients with observations to run, since we only have 1 patient, it shouldn't raise exception but stats should be correct.
    # The stats list has 1 value (mean value for the patient RP001).

def test_research_stats_run_group_comparison(client):
    token = serializer.dumps(f"staff:res_doctor:{int(time.time())}")
    client.cookies.set("hd_session", token)

    payload = {
        "test_type": "group_comparison",
        "variable": "hb",
        "group_by": "sex",
        "date_from": "2026-01",
        "date_to": "2026-03"
    }
    response = client.post("/research/stats/run", json=payload)
    assert response.status_code == 200
    # Should say error or insufficient because we only have 1 patient/group
    data = response.json()
    assert "error" in data or "groups" in data

def test_research_stats_run_correlation(client):
    token = serializer.dumps(f"staff:res_doctor:{int(time.time())}")
    client.cookies.set("hd_session", token)

    payload = {
        "test_type": "correlation",
        "variable": "hb",
        "variable2": "serum_creatinine",
        "date_from": "2026-01",
        "date_to": "2026-03"
    }
    response = client.post("/research/stats/run", json=payload)
    assert response.status_code == 200
    data = response.json()
    # We only have 1 patient, so n_both = 1 < 3. Should return error message.
    assert "error" in data
    assert "Insufficient paired data" in data["error"]

def test_research_stats_run_trend(client):
    token = serializer.dumps(f"staff:res_doctor:{int(time.time())}")
    client.cookies.set("hd_session", token)

    payload = {
        "test_type": "trend",
        "variable": "hb",
        "date_from": "2026-01",
        "date_to": "2026-03"
    }
    response = client.post("/research/stats/run", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["test_type"] == "trend"
    assert len(data["months"]) == 3
    assert data["trend_direction"] in ("increasing", "decreasing")

def test_research_stats_run_survival_and_logrank(client):
    token = serializer.dumps(f"staff:res_doctor:{int(time.time())}")
    client.cookies.set("hd_session", token)

    # Survival
    payload = {
        "test_type": "survival",
        "date_to": "2026-12"
    }
    response = client.post("/research/stats/run", json=payload)
    assert response.status_code == 200
    data = response.json()
    # n < 5 patients with HD start dates, should return error
    assert "error" in data
    assert "Insufficient data" in data["error"]

    # Log-Rank
    payload = {
        "test_type": "logrank",
        "group_by": "sex",
        "date_to": "2026-12"
    }
    response = client.post("/research/stats/run", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "error" in data
    assert "Need ≥2 groups" in data["error"]

def test_research_stats_run_cox(client):
    token = serializer.dumps(f"staff:res_doctor:{int(time.time())}")
    client.cookies.set("hd_session", token)

    payload = {
        "test_type": "cox",
        "covariates": ["sex", "dm_status", "htn_status"],
        "date_to": "2026-12"
    }
    response = client.post("/research/stats/run", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "error" in data
    assert "Insufficient complete-case data" in data["error"]

def test_research_stats_run_bayes_mlm(client):
    token = serializer.dumps(f"staff:res_doctor:{int(time.time())}")
    client.cookies.set("hd_session", token)

    payload = {
        "test_type": "bayes_mlm",
        "variable": "hb",
        "covariates": ["sex", "htn_status"],
        "date_from": "2026-01",
        "date_to": "2026-03"
    }
    response = client.post("/research/stats/run", json=payload)
    assert response.status_code == 200
    data = response.json()
    # Need n_obs >= 10, should return error
    assert "error" in data
    assert "Insufficient data for Bayesian MLM" in data["error"]
