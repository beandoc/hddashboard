import pytest
import math
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Setup test db
SQLALCHEMY_DATABASE_URL = "sqlite://"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

import database
database.SessionLocal = TestingSessionLocal

from database import Base, Patient, MonthlyRecord, DryWeightAssessment, ResearchRecord, SessionRecord
from db.models.clinical import AccessSurveillanceRecord, AccessEpisode
from ml_twin import run_scenario, _estimate_cardiac_output

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    # 1. Create a test patient with high height and weight
    p = Patient(id=99, name="Test Twin Patient", hid_no="TT001", is_active=True, sex="Male", age=45, height=180.0, dry_weight=80.0)
    db.add(p)
    db.commit()
    
    # 2. Add baseline session records
    s1 = SessionRecord(
        patient_id=p.id, 
        session_date=date(2026, 5, 1), 
        record_month="2026-05", 
        blood_flow_rate=300.0, 
        dialysate_flow=500.0,
        actual_uf_volume=2000.0, 
        uf_volume=2000.0,
        bp_pre_sys=130.0, 
        bp_pre_dia=80.0,
        arterial_line_pressure=-150.0, 
        venous_line_pressure=180.0
    )
    db.add(s1)
    
    # 3. Add monthly records
    r1 = MonthlyRecord(
        patient_id=p.id, 
        record_month="2026-05", 
        hb=11.0, 
        serum_ferritin=300.0, 
        tsat=25.0, 
        pre_dialysis_urea=100.0, 
        post_dialysis_urea=35.0, 
        serum_creatinine=10.0
    )
    db.add(r1)
    
    # 4. Add BIA research record
    # Note: Using Jyoti Balgude's BIA data format
    bia_research = ResearchRecord(
        patient_id=p.id,
        test_type="BIA",
        test_date=date(2026, 5, 6),
        data='{"tbw_liters": "25.0", "phase_angle": "4.5", "fat_free_mass": "34.0", "body_fat_mass": "10.0"}'
    )
    db.add(bia_research)
    
    # 5. Add Doppler Access record
    ep = AccessEpisode(patient_id=p.id, access_class="AVF", creation_date=date(2026, 1, 1))
    db.add(ep)
    db.commit()
    
    doppler = AccessSurveillanceRecord(
        patient_id=p.id,
        episode_id=ep.id,
        surveillance_date=date(2026, 5, 6),
        clinical_trigger="Routine",
        qa_by_imaging=350.0, # low flow, Qb=400 will cause recirculation
        psv_at_stenosis=220.0,
        stenosis_pct=40.0,
        finding="mild_stenosis"
    )
    db.add(doppler)
    db.commit()
    
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)

def test_cardiac_output_estimation():
    # Male, 45 years old, 180cm, 80kg
    co = _estimate_cardiac_output("Male", 45, 180.0, 80.0)
    assert 4.5 <= co <= 6.5
    
    # Check default fallback
    co_default = _estimate_cardiac_output(None, None, None, None)
    assert math.isclose(co_default, 5.429, abs_tol=0.01)

def test_digital_twin_recirculation_and_bia():
    db = TestingSessionLocal()
    from routers.twin import _build_patient_info, _build_baseline_session, _past_sessions_dicts, _monthly_records_dicts
    
    patient = db.query(Patient).filter(Patient.id == 99).first()
    records = _monthly_records_dicts(db, patient.id)
    past_sessions = _past_sessions_dicts(db, patient.id)
    
    patient_info = _build_patient_info(patient, records, db)
    baseline_session = _build_baseline_session(past_sessions)
    
    # Verify patient_info correctly extracted BIA and Doppler metrics
    assert patient_info["bia"] is not None
    assert patient_info["bia"]["tbw_l"] == 25.0
    assert patient_info["bia"]["phase_angle"] == 4.5
    assert patient_info["doppler"] is not None
    assert patient_info["doppler"]["qa"] == 350.0
    
    # Verify baseline session has Qb and line pressures
    assert baseline_session["qb_ml_min"] == 300.0
    assert baseline_session["arterial_line_pressure"] == -150.0
    assert baseline_session["venous_line_pressure"] == 180.0
    
    # Run simulation with scenario having Qb = 400 mL/min (which exceeds Qa = 350)
    scenario = {
        "qb_ml_min": 400.0,
        "qd_ml_min": 500.0
    }
    
    result = run_scenario(
        patient_id=patient.id,
        records=records,
        patient_info=patient_info,
        baseline_session=baseline_session,
        past_sessions=past_sessions,
        monthly_data=records[0],
        monthly_records_3mo=records[:3],
        scenario=scenario
    )
    
    # Verify hemodynamics shunt calculations
    assert result["hemodynamics"] is not None
    assert result["hemodynamics"]["qa"] == 350.0
    assert result["hemodynamics"]["shunt_ratio"] is not None
    assert result["hemodynamics"]["cardiac_strain"] == "low"  # because Qa < 600
    
    # Verify access recirculation and penalized clearances in scenario
    ktv_ext = result["ktv_extended"]
    assert ktv_ext is not None
    
    # Baseline Qb = 300 <= Qa = 350, so baseline ar_fraction should be 0.0
    assert ktv_ext["baseline"]["ar_fraction"] == 0.0
    
    # Scenario Qb = 400 > Qa = 350, so scenario ar_fraction should be (400-350)/400 = 12.5%
    assert ktv_ext["scenario"]["ar_fraction"] == 0.125
    assert ktv_ext["scenario"]["kd_effective"] < ktv_ext["scenario"]["kd"]
    
    # Verify BIA variables are propagated in result payload
    assert result["bia"] is not None
    assert result["bia"]["tbw_l"] == 25.0
    assert result["doppler"] is not None
    assert result["doppler"]["qa"] == 350.0
    
    db.close()


def test_measured_cardiac_output():
    db = TestingSessionLocal()
    from routers.twin import _build_patient_info, _build_baseline_session, _past_sessions_dicts, _monthly_records_dicts
    
    # 1. Update the patient's cardiac record with Echo measurements
    p = db.query(Patient).filter(Patient.id == 99).first()
    p.lvot_diameter = 2.0
    p.lvot_vti = 20.0
    p.heart_rate = 75
    
    # Auto-calculated values from form would be:
    # CSA = pi * (2.0 / 2)^2 = 3.14159265
    # SV = 3.14159265 * 20.0 = 62.83 mL
    # CO = (62.8318 * 75) / 1000 = 4.71 L/min
    p.stroke_volume = 62.83
    p.cardiac_output = 4.71
    db.commit()
    
    records = _monthly_records_dicts(db, p.id)
    past_sessions = _past_sessions_dicts(db, p.id)
    
    patient_info = _build_patient_info(p, records, db)
    
    # Verify patient_info has the measured cardiac output
    assert patient_info["cardiac_output"] == 4.71
    
    # Run the simulation
    scenario = {"qb_ml_min": 300.0, "qd_ml_min": 500.0}
    result = run_scenario(
        patient_id=p.id,
        records=records,
        patient_info=patient_info,
        baseline_session=_build_baseline_session(past_sessions),
        past_sessions=past_sessions,
        monthly_data=records[0],
        monthly_records_3mo=records[:3],
        scenario=scenario
    )
    
    # Verify co_is_measured is True and estimated_co is 4.71
    assert result["hemodynamics"]["co_is_measured"] is True
    assert result["hemodynamics"]["estimated_co"] == 4.71
    
    db.close()


def test_twin_simulation_fluid_volume_params():
    from db.models.ml import TwinSimulation
    db = TestingSessionLocal()
    
    # Save a TwinSimulation record with fluid_volume_params
    sim = TwinSimulation(
        patient_id=99,
        scenario_json='{"uf_rate": 10.0}',
        baseline_session_json='{}',
        hb_sim_json='{}',
        ktv_sim_json='{}',
        idh_sim_json='{}',
        uf_curve_json='{}',
        fluid_volume_params={"optimal_uf_rate_ml_kg_h": 8.5}
    )
    db.add(sim)
    db.commit()
    
    # Retrieve it and verify
    retrieved = db.query(TwinSimulation).filter(TwinSimulation.patient_id == 99).first()
    assert retrieved is not None
    assert retrieved.fluid_volume_params is not None
    assert retrieved.fluid_volume_params["optimal_uf_rate_ml_kg_h"] == 8.5
    
    db.close()


def test_patient_access_failure_risk_endpoint():
    from unittest.mock import MagicMock
    import asyncio
    import routers.api_v1
    from db.models.clinical import AccessSurveillanceRecord

    # Add a second AccessSurveillanceRecord so patient 99 has >= 2 records
    db = TestingSessionLocal()
    p = db.query(Patient).filter(Patient.id == 99).first()
    ep = p.access_episodes[0]
    
    # Add second Doppler surveillance record
    doppler2 = AccessSurveillanceRecord(
        patient_id=p.id,
        episode_id=ep.id,
        surveillance_date=date(2026, 5, 10),
        clinical_trigger="Followup",
        qa_by_imaging=320.0,
        psv_at_stenosis=240.0,
        stenosis_pct=50.0,
        finding="moderate_stenosis"
    )
    db.add(doppler2)
    db.commit()
    
    # Monkeypatch _require_staff to bypass authentication checks
    original_require_staff = routers.api_v1._require_staff
    routers.api_v1._require_staff = lambda req: MagicMock()
    
    try:
        mock_req = MagicMock()
        # Call the endpoint function directly
        coro = routers.api_v1.v1_patient_access_failure_risk(patient_id=99, request=mock_req, db=db)
        res = asyncio.run(coro)
        
        # Assertions
        assert res is not None
        assert res["available"] is True
        assert "probability_90d" in res
        assert "risk_level" in res
    finally:
        routers.api_v1._require_staff = original_require_staff
        db.close()
