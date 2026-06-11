import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, Patient, MonthlyRecord
from dashboard_logic import compute_dashboard

# Setup SQLite file for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_clinical_logic.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

import database
database.SessionLocal = TestingSessionLocal

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
    # Expected weekly_iu_sc = (75 / 10.0) * 7.0 * 200 = 7.5 * 7.0 * 200 = 10500.0
    assert res["weekly_iu_sc"] == 10500.0

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
    assert record.neutrophil_count == 4.485

def test_backend_ktv_calculation(db):
    from services.entry_service import save_monthly_record
    p = Patient(name="KTV Patient", hid_no="T005", is_active=True, dry_weight=70.0)
    db.add(p)
    db.commit()

    data = {
        "month_str": "2026-04",
        "pre_dialysis_urea": 120.0,
        "post_dialysis_urea": 35.0,
        "idwg": 3.0,
        "last_prehd_weight": 73.0,
        "target_dry_weight": 70.0,
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
    assert record.single_pool_ktv == 1.47
    assert record.equilibrated_ktv == 1.43

def test_backend_tsat_calculation(db):
    from services.entry_service import save_monthly_record
    p = Patient(name="TSAT Patient", hid_no="T011", is_active=True)
    db.add(p)
    db.commit()

    data = {
        "month_str": "2026-04",
        "serum_iron": 60.0,
        "tibc": 300.0,
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
    assert record.tsat == 20.0

def test_phosphate_binder_dose_calculation(db):
    from services.entry_service import save_monthly_record
    p = Patient(name="PB Patient", hid_no="T006", is_active=True)
    db.add(p)
    db.commit()

    data = {
        "month_str": "2026-04",
        "pb_strength": 667.0,
        "phosphate_binder_freq": "TDS",
        "phosphate_binder_dose_mg": None,
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
    assert record.phosphate_binder_dose_mg == 2001.0

def test_residual_urine_output_carry_forward(db):
    from services.entry_service import save_monthly_record
    p = Patient(name="RUO Patient", hid_no="T007", is_active=True)
    db.add(p)
    db.commit()

    # Prior month record with RUO
    prior_r = MonthlyRecord(
        patient_id=p.id,
        record_month="2026-03",
        residual_urine_output=400.0,
        hb=10.5,
        albumin=3.8,
        calcium=9.0,
        phosphorus=4.5,
        serum_ferritin=450.0,
        serum_creatinine=12.0,
        serum_potassium=4.8,
        serum_sodium=140.0,
    )
    db.add(prior_r)
    db.commit()

    # Current month record with missing RUO
    data = {
        "month_str": "2026-04",
        "residual_urine_output": None,
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
    assert record.residual_urine_output == 400.0

def test_backend_nutrition_aggregation_and_carry_forward(db):
    from services.entry_service import save_monthly_record
    from database import PatientMealRecord
    from datetime import date
    p = Patient(name="Nutrition Patient", hid_no="T008", is_active=True, dry_weight=70.0)
    db.add(p)
    db.commit()

    # Add PatientMealRecord logs for 2026-04
    meal1 = PatientMealRecord(patient_id=p.id, date=date(2026, 4, 10), calories=1500.0, protein=60.0)
    meal2 = PatientMealRecord(patient_id=p.id, date=date(2026, 4, 15), calories=1700.0, protein=80.0)
    db.add_all([meal1, meal2])
    db.commit()

    data = {
        "month_str": "2026-04",
        "av_daily_calories": None,
        "av_daily_protein": None,
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
    # Avg calories: (1500+1700)/2 = 1600.0
    # Avg protein: (60+80)/2 = 70.0. Scaled: 70.0 / 70.0 = 1.00
    assert record.av_daily_calories == 1600.0
    assert record.av_daily_protein == 1.00

    # Save for next month without logs. Should carry forward.
    data_may = {
        "month_str": "2026-05",
        "av_daily_calories": None,
        "av_daily_protein": None,
        "hb": 10.5,
        "albumin": 3.8,
        "calcium": 9.0,
        "phosphorus": 4.5,
        "serum_ferritin": 450.0,
        "serum_creatinine": 12.0,
        "serum_potassium": 4.8,
        "serum_sodium": 140.0,
    }

    record_may = save_monthly_record(db, p.id, data_may, actor="testadmin")
    assert record_may.av_daily_calories == 1600.0
    assert record_may.av_daily_protein == 1.00


def test_role_based_clinical_field_restrictions(db):
    from services.entry_service import save_monthly_record
    p = Patient(name="Role Patient", hid_no="T009", is_active=True, clinical_background="Initial POMR")
    db.add(p)
    db.commit()

    # 1. Save as doctor: should successfully update issues and clinical_background
    data_doc = {
        "month_str": "2026-04",
        "issues": "Complications in April",
        "clinical_background": "Updated POMR by Doctor",
        "role": "doctor",
        "hb": 10.5,
        "albumin": 3.8,
        "calcium": 9.0,
        "phosphorus": 4.5,
        "serum_ferritin": 450.0,
        "serum_creatinine": 12.0,
        "serum_potassium": 4.8,
        "serum_sodium": 140.0,
    }
    rec = save_monthly_record(db, p.id, data_doc, actor="testdoctor")
    assert rec.issues == "Complications in April"
    assert p.clinical_background == "Updated POMR by Doctor"

    # 2. Save/Update as staff: issues and clinical_background should be protected (not overwritten/wiped out)
    data_staff = {
        "month_str": "2026-04",
        "issues": "",  # Form post sends empty fields because they are hidden
        "clinical_background": "",
        "role": "staff",
        "hb": 11.0,
        "albumin": 3.8,
        "calcium": 9.0,
        "phosphorus": 4.5,
        "serum_ferritin": 450.0,
        "serum_creatinine": 12.0,
        "serum_potassium": 4.8,
        "serum_sodium": 140.0,
    }
    rec2 = save_monthly_record(db, p.id, data_staff, actor="teststaff")
    assert rec2.issues == "Complications in April"  # Retained!
    assert p.clinical_background == "Updated POMR by Doctor"  # Retained!

    # 3. Save a new month as staff: issues should remain empty and clinical_background preserved
    data_staff_new = {
        "month_str": "2026-05",
        "issues": "",
        "clinical_background": "",
        "role": "staff",
        "hb": 11.2,
        "albumin": 3.8,
        "calcium": 9.0,
        "phosphorus": 4.5,
        "serum_ferritin": 450.0,
        "serum_creatinine": 12.0,
        "serum_potassium": 4.8,
        "serum_sodium": 140.0,
    }
    rec3 = save_monthly_record(db, p.id, data_staff_new, actor="teststaff")
    assert rec3.issues == ""
    assert p.clinical_background == "Updated POMR by Doctor"  # Retained!


def test_pds_analysis_matching(db):
    from datetime import date, datetime
    from database import PatientSymptomReport, SessionRecord
    from ml_cascade import analyze_pds
    
    # 1. Setup patient
    p = Patient(name="Binda Bai", hid_no="P001", is_active=True)
    db.add(p)
    db.commit()
    
    # 2. Setup Session on Saturday
    saturday = date(2026, 5, 16)
    sess = SessionRecord(
        patient_id=p.id,
        session_date=saturday,
        record_month="2026-05",
        duration_hours=4,
        duration_minutes=0,
        weight_pre=72.0,
        weight_post=70.0,
        idh_episode=False
    )
    db.add(sess)
    db.commit()
    
    # 3. Setup Symptom Report logged on Sunday morning (without explicit session_date, with reported_at)
    sunday_morning = datetime(2026, 5, 17, 9, 0, 0)
    rep1 = PatientSymptomReport(
        patient_id=p.id,
        reported_at=sunday_morning,
        dialysis_recovery_time="1-2 hours",
        fatigue_physical_exhaustion=5,
        fatigue_lack_of_energy=6
    )
    db.add(rep1)
    db.commit()
    
    # 4. Run analyze_pds
    res = analyze_pds(db, p.id)
    assert res["available"] is True
    assert len(res["events"]) == 1
    assert res["events"][0]["session_matched"] is True
    
    # 5. Setup Symptom Report logged on Monday morning with explicit session_date = Saturday
    monday_morning = datetime(2026, 5, 18, 10, 0, 0)
    rep2 = PatientSymptomReport(
        patient_id=p.id,
        reported_at=monday_morning,
        session_date=saturday,
        dialysis_recovery_time="2-6 hours",
        fatigue_physical_exhaustion=6,
        fatigue_lack_of_energy=5
    )
    db.add(rep2)
    db.commit()
    
    res2 = analyze_pds(db, p.id)
    assert len(res2["events"]) == 2
    
    # 6. Setup Symptom Report without recovery time or matched session (e.g. Wednesday)
    wednesday_morning = datetime(2026, 5, 20, 9, 0, 0)
    rep3 = PatientSymptomReport(
        patient_id=p.id,
        reported_at=wednesday_morning,
        dialysis_recovery_time=None,
        fatigue_physical_exhaustion=3,
        fatigue_lack_of_energy=7
    )
    db.add(rep3)
    db.commit()
    
    res3 = analyze_pds(db, p.id)
    assert len(res3["events"]) == 2  # Only the two matched ones in events (drt chart)
    assert len(res3["all_reports"]) == 3  # All three should be in all_reports
    assert res3["unmatched_count"] == 1


def test_new_clinical_alerts(db):
    from ml_trends import predict_phosphorus_trajectory
    from ml_cascade import analyze_idwg_velocity, analyze_bfr_trend

    # 1. Test Phosphorus Kalman Trend
    # Setup phosphorus values over 3 months
    df_phos = [
        {"month": "2026-02", "phosphorus": 4.5},
        {"month": "2026-03", "phosphorus": 5.2},
        {"month": "2026-04", "phosphorus": 6.1},  # elevated > 5.5
    ]
    res_phos = predict_phosphorus_trajectory(df_phos)
    assert res_phos["available"] is True
    assert res_phos["data"]["current"] == 6.1
    assert res_phos["data"]["alert"] is True
    assert res_phos["data"]["severity"] == "high"
    assert res_phos["data"]["next_predicted"] is not None

    # 2. Test IDWG Velocity
    sessions = [
        {"session_date": "2026-05-10", "weight_pre": 72.0, "weight_post": 70.0},
        {"session_date": "2026-05-12", "weight_pre": 73.6, "weight_post": 71.0}, # IDWG = 73.6 - 70.0 = 3.6 over 2 days -> 1.8 kg/day velocity
        {"session_date": "2026-05-14", "weight_pre": 75.0, "weight_post": 72.0}, # IDWG = 75.0 - 71.0 = 4.0 over 2 days -> 2.0 kg/day velocity
    ]
    res_idwg = analyze_idwg_velocity(sessions, dry_weight=70.0)
    assert res_idwg["available"] is True
    assert res_idwg["avg_velocity"] == 1.9  # avg of 1.8 and 2.0
    assert res_idwg["alert_level"] == "critical"  # > 1.5 is critical

    # 3. Test BFR Rolling Slope / Stenosis Warning
    bfr_sessions = [
        {"session_date": "2026-05-01", "actual_blood_flow_rate": 350.0, "blood_flow_rate": 350.0},
        {"session_date": "2026-05-03", "actual_blood_flow_rate": 330.0, "blood_flow_rate": 350.0},
        {"session_date": "2026-05-05", "actual_blood_flow_rate": 310.0, "blood_flow_rate": 350.0},
        {"session_date": "2026-05-07", "actual_blood_flow_rate": 280.0, "blood_flow_rate": 350.0},
        {"session_date": "2026-05-09", "actual_blood_flow_rate": 250.0, "blood_flow_rate": 350.0},
        {"session_date": "2026-05-11", "actual_blood_flow_rate": 210.0, "blood_flow_rate": 350.0}, # rolling slope ~ -27 mL/min/session (highly negative)
    ]
    res_bfr = analyze_bfr_trend(bfr_sessions)
    assert res_bfr["available"] is True
    assert res_bfr["rolling_slope"] is not None
    assert res_bfr["rolling_slope"] <= -5.0
    assert res_bfr["alert_level"] == "critical"
    assert "Progressive decline" in "; ".join(res_bfr["alert_reasons"])


def test_multiple_phosphate_binders_and_pbe_calculation(db):
    from services.entry_service import save_monthly_record
    from phosphate_model import calculate_record_pbe
    from ml_twin import run_scenario

    p = Patient(name="Multiple Binders Patient", hid_no="T010", is_active=True)
    db.add(p)
    db.commit()

    # Enter multiple binders
    data = {
        "month_str": "2026-04",
        "phosphate_binder_type": ["Sevelamer Carbonate", "Calcium Acetate"],
        "pb_strength": [800.0, 667.0],
        "phosphate_binder_freq": ["BD", "TDS"],
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
    
    # Assertions on saved database record
    # 1. Total Daily Dose = 800 * 2 + 667 * 3 = 1600 + 2001 = 3601.0
    assert record.phosphate_binder_dose_mg == 3601.0
    
    # 2. Backwards compatibility legacy fields (should map to primary / first binder)
    assert record.phosphate_binder_type == "Sevelamer Carbonate"
    assert record.pb_strength == 800.0
    assert record.phosphate_binder_freq == "BD"
    
    # 3. Details JSON serialization
    import json
    details = json.loads(record.phosphate_binder_details)
    assert len(details) == 2
    assert details[0]["name"] == "Sevelamer Carbonate"
    assert details[0]["dose"] == 1600.0
    assert details[1]["name"] == "Calcium Acetate"
    assert details[1]["dose"] == 2001.0

    # 4. PBE Calculation
    # PBE coefficient of Sevelamer: 0.75 -> 1.6 * 0.75 = 1.2
    # PBE coefficient of Calcium Acetate: 1.0 -> 2.001 * 1.0 = 2.001
    # Total PBE = 1.2 + 2.001 = 3.201 -> rounded to 3.2
    pbe = calculate_record_pbe(record)
    assert pbe == 3.2

    # 5. ML Twin run_scenario baseline PBE
    # Set up some dummy records/sessions for the scenario run
    records_list = [{
        "hb":                 record.hb,
        "serum_ferritin":     record.serum_ferritin,
        "tsat":               record.tsat or 25,
        "albumin":            record.albumin,
        "single_pool_ktv":    record.single_pool_ktv,
        "last_prehd_weight":  record.last_prehd_weight or 70.0,
        "weight":             record.last_prehd_weight or 70.0,
        "epo_mircera_dose":   record.epo_mircera_dose,
        "epo_weekly_units":   record.epo_weekly_units,
        "iv_iron_dose":       record.iv_iron_dose,
        "pre_dialysis_urea":  record.pre_dialysis_urea,
        "post_dialysis_urea": record.post_dialysis_urea,
        "phosphorus":         record.phosphorus,
        "ufr":                record.ufr,
        "record_month":       record.record_month,
        "phosphate_binder_type": record.phosphate_binder_type,
        "phosphate_binder_dose_mg": record.phosphate_binder_dose_mg,
        "phosphate_binder_details": record.phosphate_binder_details,
    }]
    patient_info = {"id": p.id, "sex": "m", "age": 50, "height": 170.0, "weight": 70.0}
    baseline_session = {"qb_ml_min": 300, "qd_ml_min": 500, "session_h": 4.0, "uf_volume": 2500}
    
    res = run_scenario(
        patient_id=p.id,
        records=records_list,
        patient_info=patient_info,
        baseline_session=baseline_session,
        past_sessions=[],
        monthly_data=records_list[0],
        monthly_records_3mo=records_list,
        scenario={},
        db=db
    )
    
    assert res["phosphate"]["baseline_pbe"] == 3.2


def test_esa_modification_date_simulation_merge(db):
    from services.entry_service import save_monthly_record
    from services.interim_hb_service import merge_hb_sequence
    from ml_acm import _row_to_dict
    import datetime

    p = Patient(name="ESA Mod Patient", hid_no="T012", is_active=True)
    db.add(p)
    db.commit()

    # 1. Prior month record with Mircera 100mcg
    data_prior = {
        "month_str": "2026-05",
        "esa_type": "Mircera (CERA)",
        "epo_mircera_dose": "Mircera (CERA) 100mcg Every 2 Weeks",
        "epo_weekly_units": 14000.0,
        "hb": 10.5,
        "albumin": 3.8,
        "calcium": 9.0,
        "phosphorus": 4.5,
        "serum_ferritin": 450.0,
        "serum_creatinine": 12.0,
        "serum_potassium": 4.8,
        "serum_sodium": 140.0,
    }
    rec_prior = save_monthly_record(db, p.id, data_prior, actor="testadmin")

    # 2. Current month record with updated Mircera 75mcg and modified_at = 2026-06-09
    data_curr = {
        "month_str": "2026-06",
        "esa_type": "Mircera (CERA)",
        "epo_mircera_dose": "Mircera (CERA) 75mcg Every 2 Weeks",
        "epo_weekly_units": 10500.0,
        "esa_modified_at": "2026-06-09",
        "hb": 11.0,
        "albumin": 3.8,
        "calcium": 9.0,
        "phosphorus": 4.5,
        "serum_ferritin": 450.0,
        "serum_creatinine": 12.0,
        "serum_potassium": 4.8,
        "serum_sodium": 140.0,
    }
    rec_curr = save_monthly_record(db, p.id, data_curr, actor="testadmin")

    # Verify db persistence
    assert rec_curr.esa_modified_at == datetime.date(2026, 6, 9)

    # 3. Fetch from DB newest-first to mock the lists
    recs = [rec_curr, rec_prior]
    monthly_dicts = [_row_to_dict(r) for r in recs]
    
    # CASE A: d = 2026-06-28 (which is >= mod_date 2026-06-09)
    # The June base monthly record retains the new dose (75mcg)
    merged_a = merge_hb_sequence(monthly_dicts, [])
    assert len(merged_a) == 3
    merged_asc_a = list(reversed(merged_a))
    
    # May 28th
    assert merged_asc_a[0]["record_month"] == "2026-05"
    assert merged_asc_a[0]["epo_mircera_dose"] == "Mircera (CERA) 100mcg Every 2 Weeks"
    # June 9th (Synthetic)
    assert merged_asc_a[1]["record_month"] == "2026-06"
    assert merged_asc_a[1]["record_date"] == "2026-06-09"
    assert merged_asc_a[1]["epo_mircera_dose"] == "Mircera (CERA) 75mcg Every 2 Weeks"
    assert merged_asc_a[1]["is_interim"] is True
    # June 28th (Base monthly)
    assert merged_asc_a[2]["record_month"] == "2026-06"
    assert merged_asc_a[2]["record_date"] == "2026-06-28"
    assert merged_asc_a[2]["epo_mircera_dose"] == "Mircera (CERA) 75mcg Every 2 Weeks"
    assert merged_asc_a[2]["is_interim"] is False

    # CASE B: d = 2026-06-01 (which is < mod_date 2026-06-09)
    # The June base monthly record gets overwritten with the old dose (100mcg)
    monthly_dicts_b = [_row_to_dict(r) for r in recs]
    monthly_dicts_b[0]["record_date"] = "2026-06-01"  # explicitly set record_date so d = 2026-06-01
    
    merged_b = merge_hb_sequence(monthly_dicts_b, [])
    assert len(merged_b) == 3
    merged_asc_b = list(reversed(merged_b))
    
    # June 1st (Base monthly)
    assert merged_asc_b[1]["record_month"] == "2026-06"
    assert merged_asc_b[1]["record_date"] == "2026-06-01"
    assert merged_asc_b[1]["epo_mircera_dose"] == "Mircera (CERA) 100mcg Every 2 Weeks" # Overwritten!
    assert merged_asc_b[1]["is_interim"] is False
    # June 9th (Synthetic)
    assert merged_asc_b[2]["record_month"] == "2026-06"
    assert merged_asc_b[2]["record_date"] == "2026-06-09"
    assert merged_asc_b[2]["epo_mircera_dose"] == "Mircera (CERA) 75mcg Every 2 Weeks" # Modified dose!
    assert merged_asc_b[2]["is_interim"] is True






