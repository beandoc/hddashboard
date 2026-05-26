import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import time
from datetime import date
from fastapi.testclient import TestClient
from passlib.context import CryptContext

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

from database import Base, get_db, User, Patient, SessionRecord
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
    
    # Create test users with different roles
    users = [
        {"username": "testadmin", "role": "admin"},
        {"username": "teststaff", "role": "staff"},
        {"username": "testdoctor", "role": "doctor"}
    ]
    for u in users:
        if not db.query(User).filter(User.username == u["username"]).first():
            hashed_pw = pwd_context.hash("password123")
            user = User(
                username=u["username"], 
                full_name=f"Test {u['role'].capitalize()}", 
                hashed_password=hashed_pw, 
                role=u["role"], 
                is_active=True
            )
            db.add(user)
            
    # Create a test patient
    if not db.query(Patient).filter(Patient.id == 1).first():
        patient = Patient(id=1, name="John Doe", hid_no="HD101", is_active=True)
        db.add(patient)
        
    db.commit()
    db.close()

    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(autouse=True)
def clean_sessions():
    db = TestingSessionLocal()
    db.query(SessionRecord).delete()
    db.commit()
    db.close()

def test_staff_session_edit_redirect(client):
    db = TestingSessionLocal()
    session_rec = SessionRecord(id=10, patient_id=1, session_date=date(2026, 4, 1), record_month="2026-04")
    db.add(session_rec)
    db.commit()
    db.close()

    token = serializer.dumps(f"staff:teststaff:{int(time.time())}")
    client.cookies.clear()
    
    response = client.post("/sessions/10/edit", data={
        "session_date": "2026-04-01",
        "symptoms": []
    }, cookies={"hd_session": token}, follow_redirects=False)
    
    assert response.status_code == 303
    assert response.headers["Location"] == "/patients/1/profile"

def test_admin_session_edit_redirect(client):
    db = TestingSessionLocal()
    session_rec = SessionRecord(id=11, patient_id=1, session_date=date(2026, 4, 1), record_month="2026-04")
    db.add(session_rec)
    db.commit()
    db.close()

    token = serializer.dumps(f"staff:testadmin:{int(time.time())}")
    client.cookies.clear()
    
    response = client.post("/sessions/11/edit", data={
        "session_date": "2026-04-01",
        "symptoms": []
    }, cookies={"hd_session": token}, follow_redirects=False)
    
    assert response.status_code == 303
    assert response.headers["Location"] == "/analytics/patients/1"

def test_staff_session_delete_redirect(client):
    db = TestingSessionLocal()
    session_rec = SessionRecord(id=12, patient_id=1, session_date=date(2026, 4, 1), record_month="2026-04")
    db.add(session_rec)
    db.commit()
    db.close()

    token = serializer.dumps(f"staff:teststaff:{int(time.time())}")
    client.cookies.clear()
    
    response = client.post("/sessions/12/delete", cookies={"hd_session": token}, follow_redirects=False)
    
    assert response.status_code == 303
    assert response.headers["Location"] == "/patients/1/profile"

def test_doctor_session_delete_redirect(client):
    db = TestingSessionLocal()
    session_rec = SessionRecord(id=13, patient_id=1, session_date=date(2026, 4, 1), record_month="2026-04")
    db.add(session_rec)
    db.commit()
    db.close()

    token = serializer.dumps(f"staff:testdoctor:{int(time.time())}")
    client.cookies.clear()
    
    response = client.post("/sessions/13/delete", cookies={"hd_session": token}, follow_redirects=False)
    
    assert response.status_code == 303
    assert response.headers["Location"] == "/analytics/patients/1"
