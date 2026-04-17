import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, Patient, MonthlyRecord
from dashboard_logic import compute_dashboard, THRESHOLDS

# Setup in-memory SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

def test_hb_drop_alert(db):
    # Setup patient
    p = Patient(name="Test Patient", hid_no="T001", is_active=True)
    db.add(p)
    db.commit()

    # Previous month: High Hb
    prev_r = MonthlyRecord(patient_id=p.id, record_month="2026-03", hb=13.0)
    # Current month: Dropped Hb (drop = 2.0 > 1.5 threshold)
    curr_r = MonthlyRecord(patient_id=p.id, record_month="2026-04", hb=11.0)
    db.add_all([prev_r, curr_r])
    db.commit()

    data = compute_dashboard(db, "2026-04")
    
    # Check hb_drop_alert metric
    assert data["metrics"]["hb_drop_alert"]["count"] == 1
    assert "Test Patient" in data["metrics"]["hb_drop_alert"]["names"]
    
    # Check patient row alerts
    patient_row = next(r for r in data["patient_rows"] if r["name"] == "Test Patient")
    assert "Hb Drop" in patient_row["alerts"]

def test_dialysis_intensification_alert(db):
    p = Patient(name="Fluid Patient", hid_no="T002", is_active=True, hd_slot_3="")
    db.add(p)
    db.commit()

    # prev month: phos 5.0
    prev_r = MonthlyRecord(patient_id=p.id, record_month="2026-03", phosphorus=5.0)
    # curr month: phos 6.0 (rising), idwg 3.0 (high > 2.5)
    curr_r = MonthlyRecord(patient_id=p.id, record_month="2026-04", phosphorus=6.0, idwg=3.0)
    db.add_all([prev_r, curr_r])
    db.commit()

    data = compute_dashboard(db, "2026-04")
    assert data["metrics"]["dialysis_intensification"]["count"] == 1
    
    patient_row = next(r for r in data["patient_rows"] if r["name"] == "Fluid Patient")
    assert "Intensify Dialysis" in patient_row["alerts"]

def test_iv_iron_recommendation(db):
    p = Patient(name="Anemic Patient", hid_no="T003", is_active=True)
    db.add(p)
    db.commit()

    # hb < 10 AND (ferritin < 500 OR tsat < 30)
    r = MonthlyRecord(patient_id=p.id, record_month="2026-04", hb=9.5, serum_ferritin=400, tsat=25)
    db.add(r)
    db.commit()

    data = compute_dashboard(db, "2026-04")
    assert data["metrics"]["iv_iron_rec"]["count"] == 1
    assert "Anemic Patient" in data["metrics"]["iv_iron_rec"]["names"]
