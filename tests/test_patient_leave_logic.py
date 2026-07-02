import pytest
import math
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Setup SQLite file for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_patient_leave_logic.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

import database
database.SessionLocal = TestingSessionLocal

import main  # Trigger compute_dashboard monkeypatch
from database import Base, Patient, MonthlyRecord, SessionRecord, ClinicalEvent
from dashboard_logic import compute_dashboard

@pytest.fixture
def db():
    import dashboard_logic
    dashboard_logic._DASHBOARD_CACHE.clear()
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        dashboard_logic._DASHBOARD_CACHE.clear()

def test_ode_stability_on_large_step():
    from ml_acm_ode import ode_step_2c
    # Setup test parameters with k_loss = 0.4 and step_days = 90.0.
    # Without sub-stepping, the Euler decay coefficient would be 1.0 - 0.4 * 3.0 = -0.2 (negative!).
    # With sub-stepping, it runs 90 daily steps of step_days=1.0, preserving stability and positivity.
    hb0 = 10.0
    r0 = 0.0
    epo_norm = 0.0
    iron_frac = 0.0
    crp = 0.0
    params = (0.0, 0.0, 0.4)  # k_epo, k_prod, k_loss
    
    hb_next, r_next = ode_step_2c(hb0, r0, epo_norm, iron_frac, crp, params, step_days=90.0)
    
    # Assert that hb_next remains positive and within valid physiologic bounds
    assert hb_next >= 6.0
    assert not math.isnan(hb_next)

def test_calendar_aware_feature_extraction():
    from ml_acm import _extract_acm_features
    # Construct sequence with a 60-day gap:
    # Record 0: 2026-05-28
    # Record 1: 2026-03-28 (60 days ago) - April is missing!
    # Record 2: 2026-02-28 (89 days ago)
    records = [
        {"hb": 11.0, "record_month": "2026-05"},
        {"hb": 12.0, "record_month": "2026-03"},
        {"hb": 13.0, "record_month": "2026-02"},
    ]
    
    feats = _extract_acm_features(records)
    assert feats is not None
    
    # Index 1: delta_hb_1mo (should be NaN because no record was found in the 15-45 days window)
    assert math.isnan(feats[1])
    # Index 2: delta_hb_3mo (should be 11.0 - 13.0 = -2.0, matching the record ~90 days ago)
    assert feats[2] == -2.0

def test_adherence_monitor_temporary_leave_bypass(db):
    # Setup patient
    p = Patient(name="Leave Patient", hid_no="L001", is_active=True, hd_frequency=3)
    db.add(p)
    db.commit()
    
    # Case 1: No leave event, 0 sessions in May 2026 -> expect skipped sessions alert
    data = compute_dashboard(db, "2026-05")
    row = next(r for r in data["patient_rows"] if r["name"] == "Leave Patient")
    assert "Skipped Sessions" in row["alerts"]
    assert "Skipped Sessions" in row["adherence_flags"]
    assert data["metrics"]["adherence_risk"]["count"] == 1
    
    # Case 2: Add Temporary Leave event in May 2026 -> expect bypass
    ev = ClinicalEvent(
        patient_id=p.id,
        event_date=datetime.date(2026, 5, 10),
        event_type="Temporary Leave",
        notes="Away on leave dialyzing at another center"
    )
    db.add(ev)
    db.commit()
    
    # Re-compute dashboard. "Skipped Sessions" should now be bypassed/excused!
    data2 = compute_dashboard(db, "2026-05")
    row2 = next(r for r in data2["patient_rows"] if r["name"] == "Leave Patient")
    assert "Skipped Sessions" not in row2["alerts"]
    assert "Skipped Sessions" not in row2.get("adherence_flags", [])
    assert data2["metrics"]["adherence_risk"]["count"] == 0

def test_adherence_monitor_rejoin_via_session_record(db):
    # Setup patient who goes on leave in May and returns in June via SessionRecord
    p = Patient(name="Session Return Patient", hid_no="L002", is_active=True, hd_frequency=3)
    db.add(p)
    db.commit()  # Generate patient ID
    
    # Leave event: May 10th
    ev = ClinicalEvent(
        patient_id=p.id,
        event_date=datetime.date(2026, 5, 10),
        event_type="Temporary Leave"
    )
    db.add(ev)
    db.commit()
    
    # In May: Should be on leave and excused
    data_may = compute_dashboard(db, "2026-05")
    row_may = next(r for r in data_may["patient_rows"] if r["name"] == "Session Return Patient")
    assert "Skipped Sessions" not in row_may.get("adherence_flags", [])
    
    # In June: Add a SessionRecord on June 15th
    sess = SessionRecord(
        patient_id=p.id,
        session_date=datetime.date(2026, 6, 15),
        record_month="2026-06",
        duration_hours=4.0
    )
    db.add(sess)
    db.commit()
    
    # In June: Since return is June 15th, they were on leave for part of June. They should still be excused.
    data_june = compute_dashboard(db, "2026-06")
    row_june = next(r for r in data_june["patient_rows"] if r["name"] == "Session Return Patient")
    assert "Skipped Sessions" not in row_june.get("adherence_flags", [])
    
    # In July: Since they returned in June, they are fully active in July.
    # Because they have 0 July sessions, they should trigger the "Skipped Sessions" alert again.
    data_july = compute_dashboard(db, "2026-07")
    row_july = next(r for r in data_july["patient_rows"] if r["name"] == "Session Return Patient")
    assert "Skipped Sessions" in row_july["alerts"]
    assert "Skipped Sessions" in row_july["adherence_flags"]

def test_adherence_monitor_rejoin_via_event(db):
    # Setup patient who goes on leave in May and returns in June via "Return from Leave" event
    p = Patient(name="Event Return Patient", hid_no="L003", is_active=True, hd_frequency=3)
    db.add(p)
    db.commit()  # Generate patient ID
    
    # Leave event: May 10th
    ev = ClinicalEvent(
        patient_id=p.id,
        event_date=datetime.date(2026, 5, 10),
        event_type="Temporary Leave"
    )
    db.add(ev)
    db.commit()
    
    # Return event: June 15th
    rev = ClinicalEvent(
        patient_id=p.id,
        event_date=datetime.date(2026, 6, 15),
        event_type="Return from Leave"
    )
    db.add(rev)
    db.commit()
    
    # In June: Excused
    data_june = compute_dashboard(db, "2026-06")
    row_june = next(r for r in data_june["patient_rows"] if r["name"] == "Event Return Patient")
    assert "Skipped Sessions" not in row_june.get("adherence_flags", [])
    
    # In July: Alert triggers (fully active, 0 sessions)
    data_july = compute_dashboard(db, "2026-07")
    row_july = next(r for r in data_july["patient_rows"] if r["name"] == "Event Return Patient")
    assert "Skipped Sessions" in row_july["alerts"]
    assert "Skipped Sessions" in row_july["adherence_flags"]
