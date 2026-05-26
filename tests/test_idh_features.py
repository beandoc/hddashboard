import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, Patient, SessionRecord, MonthlyRecord, PatientSymptomReport
from ml_idh import (
    _extract_idh_features_for_training,
    _extract_idh_features_for_inference,
    compute_idh_risk,
    IDH_FEATURE_NAMES
)

# Setup SQLite file for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_idh_features.db"
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

def test_extract_idh_features_training_and_inference(db):
    # 1. Create mock patient
    p = Patient(
        name="IDH Test Patient",
        hid_no="IDH001",
        age=65,
        dm_status="Type 2 Diabetes Mellitus",
        chf_status=1,
        cad_status=1,
        history_of_pvd=1,
        af_status=1,
        liver_disease="Chronic Liver Disease",
        ejection_fraction=45.0,
        diastolic_dysfunction="Grade II",
        dry_weight=68.0,
        hd_frequency=3,
        hd_wef_date=date(2025, 5, 26),
        is_active=True,
    )
    db.add(p)
    db.commit()

    # 2. Create monthly record for the patient
    mr = MonthlyRecord(
        patient_id=p.id,
        record_month="2026-05",
        albumin=3.6,
        antihypertensive_count=2,
        hb=10.8,
        calcium=8.9,
        phosphorus=4.2,
    )
    db.add(mr)
    db.commit()

    # 3. Create historical sessions (past_sessions)
    # Session 1 (older)
    s1 = SessionRecord(
        patient_id=p.id,
        session_date=date(2026, 5, 10),
        record_month="2026-05",
        weight_pre=70.0,
        weight_post=68.0,
        uf_volume=2000.0,
        actual_uf_volume=1800.0,
        bp_pre_sys=130.0,
        bp_pre_dia=80.0,
        bp_nadir_sys=100.0,
        bp_nadir_dia=60.0,
        dialysate_temperature=36.5,
        dialysate_sodium=137.0,
        muscle_cramps=False,
        nausea_vomiting=False,
        actual_blood_flow_rate=250.0,
        blood_flow_rate=250.0,
        arterial_line_pressure=-120.0,
        venous_line_pressure=140.0,
    )
    db.add(s1)
    db.commit()

    # Create symptom report for s1
    sr1 = PatientSymptomReport(
        patient_id=p.id,
        session_id=s1.id,
        session_date=s1.session_date,
        symptoms="Dizziness, Cramps",
        dialysis_recovery_time_mins=180,
    )
    db.add(sr1)
    db.commit()

    # Session 2 (current session to be evaluated)
    s2 = SessionRecord(
        patient_id=p.id,
        session_date=date(2026, 5, 12),
        record_month="2026-05",
        weight_pre=70.5,
        weight_post=68.0,
        uf_volume=2500.0,
        actual_uf_volume=2500.0,
        bp_pre_sys=140.0,
        bp_pre_dia=85.0,
        bp_nadir_sys=110.0,
        bp_nadir_dia=70.0,
        dialysate_temperature=37.0,
        dialysate_sodium=138.0,
        muscle_cramps=True,
        nausea_vomiting=True,
        actual_blood_flow_rate=280.0,
        blood_flow_rate=250.0,
        arterial_line_pressure=-140.0,
        venous_line_pressure=160.0,
    )
    db.add(s2)
    db.commit()

    # Create symptom report for s2
    sr2 = PatientSymptomReport(
        patient_id=p.id,
        session_id=s2.id,
        session_date=s2.session_date,
        symptoms="Nausea",
        dialysis_recovery_time_mins=240,
    )
    db.add(sr2)
    db.commit()

    # 4. Verify ORM feature extraction for training on s2 (using s1 as the sole past session)
    feats_train = _extract_idh_features_for_training(
        session=s2,
        patient=p,
        past_sessions=[s1],
        monthly_record=mr,
        monthly_records_3mo=[mr],
    )

    assert len(feats_train) == 41
    
    # Feature 26: hd_frequency (3.0)
    assert feats_train[26] == 3.0
    # Feature 27: dialysis_vintage (session_date - hd_wef_date) = (2026-05-12 - 2025-05-26) = 351 days
    assert feats_train[27] == 351.0
    # Feature 28: hb (10.8)
    assert feats_train[28] == 10.8
    # Feature 29: calcium (8.9)
    assert feats_train[29] == 8.9
    # Feature 30: phosphorus (4.2)
    assert feats_train[30] == 4.2
    # Feature 31: prev_muscle_cramps (s1.muscle_cramps = False -> 0.0)
    assert feats_train[31] == 0.0
    # Feature 32: prev_nausea_vomiting (s1.nausea_vomiting = False -> 0.0)
    assert feats_train[32] == 0.0
    # Feature 33: prev_giddiness ("Dizziness" is in s1's symptom report -> 1.0)
    assert feats_train[33] == 1.0
    # Feature 34: prev_recovery_time (s1 recovery time = 180 mins)
    assert feats_train[34] == 180.0
    # Feature 35: prev_blood_flow_rate (s1.actual_blood_flow_rate = 250.0)
    assert feats_train[35] == 250.0
    # Feature 36: prev_arterial_pressure (s1.arterial_line_pressure = -120.0)
    assert feats_train[36] == -120.0
    # Feature 37: prev_venous_pressure (s1.venous_line_pressure = 140.0)
    assert feats_train[37] == 140.0
    # Feature 38: heart_rate_variation (None)
    assert feats_train[38] is None
    # Feature 39: prior_dialysate_temp_mean (s1 temp = 36.5)
    assert feats_train[39] == 36.5
    # Feature 40: prior_dialysate_sodium_mean (s1 sodium = 137.0)
    assert feats_train[40] == 137.0

    # 5. Verify dictionary-based feature extraction for inference
    session_plan = {
        "session_date": "2026-05-12",
        "pre_hd_sbp": 140.0,
        "uf_volume": 2500.0,
        "duration_hours": 4,
        "duration_minutes": 0,
        "dialysate_temp": 37.0,
        "dialysate_sodium": 138.0,
        "antihypertensive_prehd": 0,
        "weight_pre": 70.5,
    }
    patient_info = {
        "id": p.id,
        "age": p.age,
        "dm_status": p.dm_status,
        "chf_status": p.chf_status,
        "cad_status": p.cad_status,
        "history_of_pvd": p.history_of_pvd,
        "af_status": p.af_status,
        "liver_disease": p.liver_disease,
        "ejection_fraction": p.ejection_fraction,
        "diastolic_dysfunction": p.diastolic_dysfunction,
        "dry_weight": p.dry_weight,
        "hd_frequency": p.hd_frequency,
        "hd_wef_date": p.hd_wef_date,
    }
    monthly_data = {
        "albumin": mr.albumin,
        "antihypertensive_count": mr.antihypertensive_count,
        "hb": mr.hb,
        "calcium": mr.calcium,
        "phosphorus": mr.phosphorus,
    }
    
    # We pass s1 as the past session (ORM object or serializable dict)
    feats_inf_orm = _extract_idh_features_for_inference(
        session_plan=session_plan,
        patient_info=patient_info,
        past_sessions_list=[s1],
        monthly_data=monthly_data,
        monthly_records_3mo=[mr],
    )
    assert len(feats_inf_orm) == 41
    assert feats_inf_orm[26] == 3.0
    assert feats_inf_orm[27] == 351.0
    assert feats_inf_orm[28] == 10.8
    assert feats_inf_orm[33] == 1.0
    assert feats_inf_orm[34] == 180.0
    assert feats_inf_orm[35] == 250.0

    # Let's also check with serializable dict representation of s1
    s1_dict = {
        "weight_post": s1.weight_post,
        "uf_volume": s1.uf_volume,
        "actual_uf_volume": s1.actual_uf_volume,
        "bp_pre_sys": s1.bp_pre_sys,
        "bp_nadir_sys": s1.bp_nadir_sys,
        "dialysate_temperature": s1.dialysate_temperature,
        "dialysate_sodium": s1.dialysate_sodium,
        "muscle_cramps": s1.muscle_cramps,
        "nausea_vomiting": s1.nausea_vomiting,
        "actual_blood_flow_rate": s1.actual_blood_flow_rate,
        "blood_flow_rate": s1.blood_flow_rate,
        "arterial_line_pressure": s1.arterial_line_pressure,
        "venous_line_pressure": s1.venous_line_pressure,
        "symptom_report": {
            "symptoms": sr1.symptoms,
            "dialysis_recovery_time_mins": sr1.dialysis_recovery_time_mins,
        }
    }
    feats_inf_dict = _extract_idh_features_for_inference(
        session_plan=session_plan,
        patient_info=patient_info,
        past_sessions_list=[s1_dict],
        monthly_data=monthly_data,
        monthly_records_3mo=[mr],
    )
    assert len(feats_inf_dict) == 41
    assert feats_inf_dict[26] == 3.0
    assert feats_inf_dict[27] == 351.0
    assert feats_inf_dict[28] == 10.8
    assert feats_inf_dict[33] == 1.0
    assert feats_inf_dict[34] == 180.0
    assert feats_inf_dict[35] == 250.0

    # 6. Verify compute_idh_risk runs fallback successfully and returns correct response format
    risk_result = compute_idh_risk(
        session_plan=session_plan,
        patient_info=patient_info,
        past_sessions_list=[s1],
        monthly_data=monthly_data,
        monthly_records_3mo=[mr],
        log_prediction=False,
    )
    assert risk_result["available"] is True
    assert "risk_score" in risk_result["data"]
    assert "risk_factors" in risk_result["data"]
