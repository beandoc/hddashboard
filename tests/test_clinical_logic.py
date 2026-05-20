import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, Patient, MonthlyRecord
from dashboard_logic import compute_dashboard

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

def test_mircera_10_days_normalization():
    from ml_esa import normalize_epo_dose
    # 1. Test ML normalizer with "Once in every 10 days"
    res = normalize_epo_dose("Mircera (CERA) 75mcg Once in every 10 days")
    assert res["drug_type"] == "mircera"
    assert res["frequency"] == "every_10_days"
    assert res["dose_value"] == 75.0
    # Expected weekly_iu = (75 / 10.0) * 7.0 * 208 = 7.5 * 7.0 * 208 = 10920.0
    assert res["weekly_iu_iv"] == 10920.0

    # 2. Test Bayesian interval parsing fallback for Mircera every 10 days
    from bayesian_analytics import _intervention_pseudo_beta
    # We construct a mock DataFrame that has Mircera every 10 days
    # To trigger bayesian analytics _mircera_weekly, we can test it directly
    # or by calling it through _intervention_pseudo_beta or a helper.
    # Let's inspect _mircera_weekly logic.
    mock_record_10d = {
        "epo_mircera_dose": "Mircera (CERA) 75mcg Once in every 10 days",
        "epo_mircera_interval_days": None
    }
    mock_record_2w = {
        "epo_mircera_dose": "Mircera (CERA) 75mcg Every 2 Weeks",
        "epo_mircera_interval_days": None
    }
    
    # We can invoke the _intervention_pseudo_beta with a list of dictionaries.
    # Since _intervention_pseudo_beta handles "mircera_increase", we can pass a list of dicts.
    df = [
        {"epo_mircera_dose": "Mircera (CERA) 75mcg Once in every 10 days", "month": "2026-04", "epo_weekly_units": 10500},
        {"epo_mircera_dose": "Mircera (CERA) 50mcg Once in every 10 days", "month": "2026-03", "epo_weekly_units": 7000}
    ]
    # This should parse interval = 10.0 correctly and detect the dose increase.
    rate, detected = _intervention_pseudo_beta(df, "hb")
    assert detected is True  # Dose increased from 50mcg (35 equivalent weekly) to 75mcg (52.5 equivalent weekly)

def test_tlc_and_neutrophil_boundary_normalization(db):
    from services.entry_service import save_monthly_record
    p = Patient(name="Boundary Patient", hid_no="T004", is_active=True)
    db.add(p)
    db.commit()

    # TLC / wbc_count is entered as /cmm (6500) which should be divided by 1000 to become 6.5
    # Neutrophils / neutrophil_count is entered as % (69) which should be divided by 100 to become 0.69
    data = {
        "month_str": "2026-04",
        "wbc_count": 6500.0,
        "neutrophil_count": 69.0,
        "hb": 10.5,
        "albumin": 3.8,
        "calcium": 9.0,
        "phosphorus": 4.5,
        "serum_ferritin": 450.0,
        "serum_creatinine": 12.0,
        "serum_potassium": 4.8,
        "serum_sodium": 140.0,
    }
    
    record = save_monthly_record(db, p.id, data, actor="testadmin")
    
    # Assert values saved in database are normalized/scaled
    assert record.wbc_count == 6.5
    assert record.neutrophil_count == 0.69


