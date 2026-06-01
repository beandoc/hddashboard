import os
import pytest
import time
from datetime import date
from fastapi.testclient import TestClient
from main import app
from config import serializer, pwd_context
import database

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_TESTS") != "1",
    reason="Live integration tests are skipped by default. Set RUN_LIVE_TESTS=1 to run."
)
from database import User, Patient, ResearchRecord, MonthlyRecord, SessionRecord, Base, get_db

import main
main.SessionLocal = database.SessionLocal

def override_get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(autouse=True)
def setup_test_data():
    db = database.SessionLocal()
    # Ensure all tables exist in the current database context (e.g. SQLite testing DB)
    Base.metadata.create_all(bind=db.bind)
    
    # 1. Create admin user if not exists
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        admin = User(username="admin", hashed_password=pwd_context.hash("admin123"), role="admin", is_active=True)
        db.add(admin)
        db.commit()

    # 2. Create Patient 6 if not exists
    p = db.query(Patient).filter(Patient.id == 6).first()
    if not p:
        p = Patient(id=6, name="Jyoti Balgude", hid_no="JB006", is_active=True, sex="Female", age=45, height=155.0, dry_weight=50.0)
        db.add(p)
        db.commit()

    # 3. Create BIA ResearchRecord for Patient 6 if not exists
    bia = db.query(ResearchRecord).filter(ResearchRecord.patient_id == 6, ResearchRecord.test_type == "BIA").first()
    if not bia:
        bia = ResearchRecord(
            patient_id=6,
            test_type="BIA",
            test_date=date(2026, 5, 6),
            data='{"phase_angle": "2.3", "body_fat_mass": "8.7", "fat_free_mass": "29.6", "percentage_body_fat": "22.7", "tbw_liters": "21.5"}'
        )
        db.add(bia)
        db.commit()

    # 4. Create MonthlyRecord for Patient 6 if not exists
    mr = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == 6).first()
    if not mr:
        mr = MonthlyRecord(
            patient_id=6,
            record_month="2026-05",
            hb=12.4,
            pre_dialysis_urea=31.0
        )
        db.add(mr)
        db.commit()

    # 5. Create SessionRecord for Patient 6 if not exists
    sr = db.query(SessionRecord).filter(SessionRecord.patient_id == 6).first()
    if not sr:
        sr = SessionRecord(
            patient_id=6,
            session_date=date(2026, 5, 6),
            record_month="2026-05",
            blood_flow_rate=250.0,
            dialysate_flow=500.0,
            arterial_line_pressure=-140.0,
            venous_line_pressure=160.0
        )
        db.add(sr)
        db.commit()

    db.close()

def test_live_twin_page_jyoti():
    client = TestClient(app)
    # Bypass login
    token = serializer.dumps(f"staff:admin:{int(time.time())}")
    client.cookies.set("hd_session", token)
    
    response = client.get("/twin/6")
    assert response.status_code == 200
    
    html = response.text
    assert "Jyoti Balgude" in html
    assert "21.5" in html  # TBW
    assert "2.3" in html   # Phase angle
    assert "29.6" in html  # Lean/Fat-free mass
    assert "8.7" in html   # Body fat mass
    assert "22.7" in html  # Body fat percentage

def test_live_twin_simulate_jyoti():
    client = TestClient(app)
    # Bypass login
    token = serializer.dumps(f"staff:admin:{int(time.time())}")
    client.cookies.set("hd_session", token)
    
    response = client.post(
        "/twin/6/simulate",
        json={"scenario": {"qb_ml_min": 300.0, "qd_ml_min": 550.0}}
    )
    assert response.status_code == 200
    res_json = response.json()
    assert "result" in res_json
    assert "plotly" in res_json
    
    result = res_json["result"]
    assert result["bia"] is not None
    assert result["bia"]["tbw_l"] == 21.5
    assert result["bia"]["phase_angle"] == 2.3
    assert result["bia"]["lean_muscle_mass"] == 29.6
