import pytest
import json
import time
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

import database
database.SessionLocal = TestingSessionLocal

from main import app
import main
main.SessionLocal = TestingSessionLocal
main._check_schema_version = lambda: None

from database import Base, get_db, User, Patient, MonthlyRecord
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
    
    # Create test user
    if not db.query(User).filter(User.username == "alert_admin").first():
        hashed_pw = pwd_context.hash("password123")
        admin = User(username="alert_admin", full_name="Alert Admin", hashed_password=hashed_pw, role="admin", is_active=True)
        db.add(admin)
        
    # Create test patients
    p1 = Patient(name="Alert Patient 1", hid_no="AP001", is_active=True, contact_no="+919876543210", access_type="Permacath")
    p2 = Patient(name="Alert Patient 2", hid_no="AP002", is_active=True, contact_no="+919876543211", access_type="Permacath")
    p3 = Patient(name="Normal Patient 3", hid_no="AP003", is_active=True, contact_no="+919876543212", access_type="AVF")
    db.add_all([p1, p2, p3])
    db.commit()
    
    # Create monthly records to trigger alerts (Non-AVF alert is triggered because access_type="Permacath")
    r1 = MonthlyRecord(patient_id=p1.id, record_month="2026-05", hb=10.5, access_type="Permacath")
    r2 = MonthlyRecord(patient_id=p2.id, record_month="2026-05", hb=10.5, access_type="Permacath")
    r3 = MonthlyRecord(patient_id=p3.id, record_month="2026-05", hb=11.5, access_type="AVF")
    
    db.add_all([r1, r2, r3])
    db.commit()
    
    db.close()

    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)

def test_alerts_page_loading(client):
    # Log in
    token = serializer.dumps(f"staff:alert_admin:{int(time.time())}")
    client.cookies.set("hd_session", token)

    response = client.get("/alerts?month=2026-05")
    assert response.status_code == 200
    assert "Alert Patient 1" in response.text
    assert "Alert Patient 2" in response.text
    
    # Assert that Normal Patient 3 is not inside the alerts tab section
    html = response.text
    alerts_tab_start = html.find('id="alertsTab"')
    assert alerts_tab_start != -1
    reminders_tab_start = html.find('id="remindersTab"')
    assert reminders_tab_start != -1
    alerts_tab_html = html[alerts_tab_start:reminders_tab_start]
    assert "Normal Patient 3" not in alerts_tab_html

def test_send_whatsapp_bulk_filtering(client):
    token = serializer.dumps(f"staff:alert_admin:{int(time.time())}")
    client.cookies.set("hd_session", token)

    db = TestingSessionLocal()
    p1 = db.query(Patient).filter(Patient.hid_no == "AP001").first()
    p2 = db.query(Patient).filter(Patient.hid_no == "AP002").first()
    p1_id, p2_id = p1.id, p2.id
    db.close()

    # 1. Send to all by passing patient_ids as None
    response = client.post("/alerts/send-whatsapp?month=2026-05", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    # Should include both alerts patients
    results_ids = [res["id"] for res in data.get("results", [])]
    assert p1_id in results_ids
    assert p2_id in results_ids

    # 2. Filter to only patient 1
    response = client.post("/alerts/send-whatsapp?month=2026-05", json={"patient_ids": [p1_id]})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    results_ids = [res["id"] for res in data.get("results", [])]
    assert p1_id in results_ids
    assert p2_id not in results_ids

def test_send_email_bulk_filtering(client):
    token = serializer.dumps(f"staff:alert_admin:{int(time.time())}")
    client.cookies.set("hd_session", token)

    db = TestingSessionLocal()
    p1 = db.query(Patient).filter(Patient.hid_no == "AP001").first()
    p1_id = p1.id
    db.close()

    import alerts
    original_smtp_user = alerts.SMTP_USER
    alerts.SMTP_USER = ""
    
    try:
        # Send to only patient 1
        response = client.post("/alerts/send-email?month=2026-05", json={"patient_ids": [p1_id]})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
    finally:
        alerts.SMTP_USER = original_smtp_user
    # Verify simulated response or live SMTP response
    assert data.get("mode") in ("simulated", "smtp")
    if data.get("mode") == "simulated":
        assert "Email ward report prepared for 1 patients" in data["message"]
    else:
        assert "Email sent" in data["message"] or "✅" in data["message"]
