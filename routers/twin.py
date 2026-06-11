"""
routers/twin.py
===============
Digital Dialysis Twin HTTP endpoints.

Routes:
    GET  /twin/{patient_id}          — render scenario sandbox UI
    POST /twin/{patient_id}/simulate — run a scenario, return JSON results
    GET  /twin/{patient_id}/history  — list past simulation runs
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from config import templates
from database import (
    MonthlyRecord,
    Patient,
    SessionRecord,
    TwinSimulation,
    InterimLabRecord,
    DiaSenseCalibration,
    get_db,
)
from dependencies import get_user, _require_staff_role
from ml_twin import run_scenario, build_twin_plotly_data
from services.twin_validation import validate_scenario, ScenarioValidationError
from services.twin_utils import sanitize_json_floats

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/twin", tags=["twin"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_patient_or_404(db: Session, patient_id: int) -> Patient:
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    return p


def _monthly_records_dicts(db: Session, patient_id: int, limit: int = 12) -> list:
    recs = (
        db.query(MonthlyRecord)
        .filter(MonthlyRecord.patient_id == patient_id)
        .order_by(MonthlyRecord.record_month.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "hb":                   rec.hb,
            "serum_ferritin":       rec.serum_ferritin,
            "tsat":                 rec.tsat,
            "albumin":              rec.albumin,
            "single_pool_ktv":      rec.single_pool_ktv,
            "crp":                  getattr(rec, "crp", None),
            "last_prehd_weight":    rec.last_prehd_weight,
            "weight":               rec.last_prehd_weight,
            "epo_mircera_dose":     rec.epo_mircera_dose,
            "epo_weekly_units":     rec.epo_weekly_units,
            "desidustat_dose":      getattr(rec, "desidustat_dose", None),
            "esa_type":             getattr(rec, "esa_type", None),
            "esa_modified_at":      getattr(rec, "esa_modified_at", None),
            "desidustat_modified_at":       getattr(rec, "desidustat_modified_at", None),
            "phosphate_binder_modified_at": getattr(rec, "phosphate_binder_modified_at", None),
            "iv_iron_dose":         rec.iv_iron_dose,
            "pre_dialysis_urea":    rec.pre_dialysis_urea,
            "post_dialysis_urea":   rec.post_dialysis_urea,
            "phosphorus":           rec.phosphorus,
            "ufr":                  rec.ufr,
            "record_month":         rec.record_month,
            "phosphate_binder_type":     rec.phosphate_binder_type,
            "phosphate_binder_dose_mg":  rec.phosphate_binder_dose_mg,
            "phosphate_binder_freq":     getattr(rec, "phosphate_binder_freq", None),
            "phosphate_binder_details":  getattr(rec, "phosphate_binder_details", None),
        }
        for rec in recs
    ]


def _merged_records_for_twin(db: Session, patient_id: int, limit: int = 12) -> list:
    """Monthly records merged with interim Hb entries and synthetic dose-change entries.

    Uses merge_hb_sequence so the twin ODE sees mid-month ESA/Desidustat/phosphate
    binder changes and interim Hb observations rather than flat end-of-month snapshots.
    """
    from services.interim_hb_service import get_interim_hbs, merge_hb_sequence
    monthly = _monthly_records_dicts(db, patient_id, limit=limit)
    interim = get_interim_hbs(db, patient_id, limit=limit * 3)
    return merge_hb_sequence(monthly, interim)


def _past_sessions_dicts(db: Session, patient_id: int, limit: int = 10) -> list:
    sessions = (
        db.query(SessionRecord)
        .filter(SessionRecord.patient_id == patient_id)
        .order_by(SessionRecord.session_date.desc())
        .limit(limit)
        .all()
    )
    result = []
    for s in sessions:
        result.append({
            "session_date":         str(s.session_date) if s.session_date else None,
            "pre_hd_sbp":           getattr(s, "bp_pre_sys", None),
            "pre_hd_dbp":           getattr(s, "bp_pre_dia", None),
            "bp_nadir_sys":         getattr(s, "bp_nadir_sys", None),
            "idh_episode":          getattr(s, "idh_episode", None),
            "uf_volume":            getattr(s, "uf_volume", None),
            "actual_session_time":  getattr(s, "actual_session_time", None),
            "idwg_kg":              getattr(s, "idwg_kg", None),
            "weight_pre":           getattr(s, "weight_pre", None),
            "weight_post":          getattr(s, "weight_post", None),
            "dialysate_temp":       getattr(s, "dialysate_temp", None),
            "dialysate_sodium":     getattr(s, "dialysate_sodium", None),
            "antihypertensive_prehd": getattr(s, "antihypertensive_prehd", None),
            "intradialytic_meals":  getattr(s, "intradialytic_meals", None),
            "blood_flow_rate":      getattr(s, "blood_flow_rate", None),
            "dialysate_flow":        getattr(s, "dialysate_flow", None),
            "arterial_line_pressure": getattr(s, "arterial_line_pressure", None),
            "venous_line_pressure":   getattr(s, "venous_line_pressure", None),
            "sp_ktv":                 getattr(s, "sp_ktv", None),
        })
    return result


def _build_patient_info(patient: Patient, monthly_records: list, db: Session) -> dict:
    from db.models.records import DryWeightAssessment
    from db.models.clinical import AccessSurveillanceRecord
    from db.models.research import ResearchRecord
    import json

    latest = monthly_records[0] if monthly_records else {}
    
    # 1. Fetch BIA metrics from DryWeightAssessment and ResearchRecord
    latest_bia = (
        db.query(DryWeightAssessment)
        .filter(DryWeightAssessment.patient_id == patient.id,
                DryWeightAssessment.bia_total_body_water != None)
        .order_by(DryWeightAssessment.assessment_date.desc())
        .first()
    )
    
    latest_research_bia = (
        db.query(ResearchRecord)
        .filter(ResearchRecord.patient_id == patient.id,
                ResearchRecord.test_type.ilike("%BIA%"))
        .order_by(ResearchRecord.test_date.desc())
        .first()
    )
    
    tbw_val = None
    phase_angle_val = None
    fluid_overload_val = None
    overhydration_pct_val = None
    lean_mass_val = None
    body_fat_mass_val = None
    pct_body_fat_val = None
    visceral_fat_val = None
    whr_val = None
    obesity_degree_val = None
    skeletal_muscle_val = None
    bmi_val = None
    
    if latest_bia:
        tbw_val = latest_bia.bia_total_body_water
        phase_angle_val = latest_bia.bia_phase_angle
        fluid_overload_val = latest_bia.bia_fluid_overload_litres
        overhydration_pct_val = latest_bia.bia_overhydration_percent

    if latest_research_bia and latest_research_bia.data:
        try:
            r_data = json.loads(latest_research_bia.data)
            if r_data.get("tbw_liters") is not None:
                tbw_val = float(r_data["tbw_liters"])
            if r_data.get("phase_angle") is not None:
                phase_angle_val = float(r_data["phase_angle"])
            if r_data.get("fat_free_mass") is not None:
                lean_mass_val = float(r_data["fat_free_mass"])
            elif r_data.get("skeletal_muscle_mass") is not None:
                lean_mass_val = float(r_data["skeletal_muscle_mass"])
            if r_data.get("body_fat_mass") is not None:
                body_fat_mass_val = float(r_data["body_fat_mass"])
            if r_data.get("percentage_body_fat") is not None:
                pct_body_fat_val = float(r_data["percentage_body_fat"])
            if r_data.get("visceral_fat_level") is not None:
                visceral_fat_val = float(r_data["visceral_fat_level"])
            if r_data.get("whr") is not None:
                whr_val = float(r_data["whr"])
            if r_data.get("obesity_degree") is not None:
                obesity_degree_val = float(r_data["obesity_degree"])
            if r_data.get("skeletal_muscle_mass") is not None:
                skeletal_muscle_val = float(r_data["skeletal_muscle_mass"])
            if r_data.get("bmi") is not None:
                bmi_val = float(r_data["bmi"])
        except Exception:
            pass

    bia_dict = None
    if tbw_val is not None:
        if lean_mass_val is None:
            lean_mass_val = tbw_val / 0.73
            
        bia_dict = {
            "tbw_l":             tbw_val,
            "phase_angle":       phase_angle_val,
            "fluid_overload":    fluid_overload_val,
            "overhydration_pct": overhydration_pct_val,
            "ecw_l":             tbw_val * 0.38,
            "icw_l":             tbw_val * 0.62,
            "lean_muscle_mass":  lean_mass_val,
            "body_fat_mass":     body_fat_mass_val,
            "percentage_body_fat": pct_body_fat_val,
            "visceral_fat_level": visceral_fat_val,
            "whr":               whr_val,
            "obesity_degree":    obesity_degree_val,
            "skeletal_muscle_mass": skeletal_muscle_val,
            "bmi":               bmi_val,
        }
        
    # 2. Fetch latest Doppler access flow
    latest_doppler = (
        db.query(AccessSurveillanceRecord)
        .filter(AccessSurveillanceRecord.patient_id == patient.id,
                AccessSurveillanceRecord.qa_by_imaging != None)
        .order_by(AccessSurveillanceRecord.surveillance_date.desc())
        .first()
    )
    doppler_dict = None
    if latest_doppler:
        doppler_dict = {
            "qa":           latest_doppler.qa_by_imaging,
            "psv":          latest_doppler.psv_at_stenosis,
            "stenosis_pct": latest_doppler.stenosis_pct,
            "finding":      latest_doppler.finding,
        }
        
    # Comorbidities
    cm = patient.comorbidity_profile
    dm = getattr(cm, "dm_status", "no") != "no" if cm else False
    chf = getattr(cm, "chf_status", False) if cm else False
    cad = getattr(cm, "cad_status", False) if cm else False

    return {
        "id":           patient.id,
        "age":          patient.age,
        "sex":          patient.sex,
        "height":       patient.height,
        "dm":           dm,
        "chf":          chf,
        "cad":          cad,
        "albumin":      latest.get("albumin"),
        "weight":       latest.get("last_prehd_weight") or latest.get("weight"),
        "bia":          bia_dict,
        "doppler":      doppler_dict,
        "cardiac_output": patient.cardiac.cardiac_output if patient.cardiac else None,
    }


def _fallback_ktv(records: list, past_sessions: list):
    """Scan all monthly records for the first valid Daugirdas spKt/V estimate."""
    from ml_twin import calculate_ktv_daugirdas, _UREA_MG_DL_TO_BUN
    uf_L      = (past_sessions[0].get("uf_volume") or 1500) / 1000 if past_sessions else 1.5
    session_h = (past_sessions[0].get("actual_session_time") or 240) / 60 if past_sessions else 4.0
    for rec in records:
        pre = rec.get("pre_dialysis_urea")
        post = rec.get("post_dialysis_urea")
        wt   = rec.get("last_prehd_weight") or rec.get("weight")
        if pre and post and wt:
            ktv = calculate_ktv_daugirdas(
                pre  * _UREA_MG_DL_TO_BUN,
                post * _UREA_MG_DL_TO_BUN,
                session_h, uf_L, wt - uf_L,
            )
            if ktv is not None and 0.5 <= ktv <= 4.0:
                return round(ktv, 2)
    return None

def _resolve_current_ktv(db: Session, patient_id: int, records: list, past_sessions: list):
    current_ktv = None
    ktv_is_recorded = False

    latest_interim = (
        db.query(InterimLabRecord)
        .filter(
            InterimLabRecord.patient_id == patient_id,
            InterimLabRecord.parameter == "sp_ktv",
            InterimLabRecord.value != None
        )
        .order_by(InterimLabRecord.lab_date.desc())
        .first()
    )

    candidates = []
    if latest_interim:
        candidates.append((latest_interim.lab_date, latest_interim.value))
    
    for s in past_sessions:
        if s.get("sp_ktv") and s.get("session_date"):
            from datetime import datetime
            try:
                s_date = datetime.strptime(s["session_date"], "%Y-%m-%d").date()
                candidates.append((s_date, s["sp_ktv"]))
            except Exception:
                pass

    if records and records[0].get("single_pool_ktv") and records[0].get("record_month"):
        from datetime import datetime
        try:
            m_date = datetime.strptime(records[0]["record_month"], "%Y-%m").date()
            candidates.append((m_date, records[0]["single_pool_ktv"]))
        except Exception:
            pass

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        current_ktv = candidates[0][1]
        ktv_is_recorded = True

    if current_ktv is None:
        current_ktv = _fallback_ktv(records, past_sessions)
        
    if current_ktv is not None:
        current_ktv = round(float(current_ktv), 2)
        
    return current_ktv, ktv_is_recorded



def _build_baseline_session(past_sessions: list) -> dict:
    """Use the most recent session as the baseline session plan.

    Real patient values are derived here so the twin starts from actual
    prescription, not hardcoded defaults.  Qd and UF rate use the median
    of up to the last 10 sessions so a single anomalous session doesn't
    skew the baseline.
    """
    if not past_sessions:
        return {}
    s = past_sessions[0]
    session_duration_h = (s.get("actual_session_time") or 240) / 60

    # Median Qd over up to last 10 sessions (fall back to 500 if unavailable)
    qd_values = [
        float(x["dialysate_flow"]) for x in past_sessions
        if x.get("dialysate_flow") is not None
    ]
    qd_ml_min = round(sorted(qd_values)[len(qd_values) // 2]) if qd_values else 500.0

    # Median UF rate (mL/kg/h) over last 10 sessions
    uf_rate_values = []
    for x in past_sessions:
        uf_vol = x.get("uf_volume")
        wt     = x.get("weight_pre")
        dur_h  = (x.get("actual_session_time") or 240) / 60
        if uf_vol and wt and dur_h > 0:
            rate = float(uf_vol) / float(wt) / dur_h
            if 3.5 <= rate <= 16.0:
                uf_rate_values.append(rate)
    if uf_rate_values:
        uf_rate_ml_kg_h = round(sorted(uf_rate_values)[len(uf_rate_values) // 2], 1)
    else:
        uf_vol = s.get("uf_volume") or 2000
        wt     = s.get("weight_pre") or 70
        uf_rate_ml_kg_h = round(max(3.5, min(16.0, uf_vol / wt / session_duration_h)), 1)

    return {
        "pre_hd_sbp":             s.get("pre_hd_sbp"),
        "uf_volume":              s.get("uf_volume"),
        "dialysate_temp":         s.get("dialysate_temp") or 36.5,
        "dialysate_sodium":       s.get("dialysate_sodium") or 138,
        "idwg_kg":                s.get("idwg_kg"),
        "session_duration_h":     session_duration_h,
        "duration_hours":         session_duration_h,
        "weight_pre":             s.get("weight_pre"),
        "antihypertensive_prehd": s.get("antihypertensive_prehd", False),
        "intradialytic_meals":    s.get("intradialytic_meals", False),
        "qb_ml_min":              s.get("blood_flow_rate") or 300.0,
        "qd_ml_min":              qd_ml_min,
        "uf_rate_ml_kg_h":        uf_rate_ml_kg_h,
        "arterial_line_pressure": s.get("arterial_line_pressure"),
        "venous_line_pressure":   s.get("venous_line_pressure"),
    }



# ── Scenario sandbox page ─────────────────────────────────────────────────────


@router.get("/{patient_id}", response_class=HTMLResponse)
async def twin_sandbox(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_staff_role(request)
    user    = get_user(request)
    patient = _get_patient_or_404(db, patient_id)

    records       = _monthly_records_dicts(db, patient_id)
    past_sessions = _past_sessions_dicts(db, patient_id)
    baseline_session = _build_baseline_session(past_sessions)

    # Page load carries empty defaults; the JS triggers runSimulation() on DOMContentLoaded.
    default_result = {}
    default_plotly = {}

    # Previous simulation history
    sim_history = (
        db.query(TwinSimulation)
        .filter(TwinSimulation.patient_id == patient_id)
        .order_by(TwinSimulation.created_at.desc())
        .limit(5)
        .all()
    )

    # Current ESA dose (for slider default)
    current_iu = None
    current_pbe = 3.0
    if records:
        from ml_esa import _resolve_weekly_iu_sc
        from phosphate_model import calculate_record_pbe
        current_iu = _resolve_weekly_iu_sc(records[0])
        current_pbe = calculate_record_pbe(records[0])
        if current_pbe <= 0.0:
            current_pbe = 3.0

    # spKt/V: prefer machine-derived recorded value (Interim, Session, Monthly) over calculated fallback
    current_ktv, ktv_is_recorded = _resolve_current_ktv(db, patient_id, records, past_sessions)

    return templates.TemplateResponse("digital_twin.html", {
        "request":          request,
        "user":             user,
        "patient":          patient,
        "records":          records,
        "baseline_session": baseline_session,
        "default_plotly":   json.dumps(default_plotly),
        "default_result":   json.dumps(default_result),
        "sim_history":      sim_history,
        "current_iu":          current_iu or 0,
        "current_pbe":         current_pbe,
        "current_tsat":        records[0].get("tsat") if records else 25,
        "current_hb":          records[0].get("hb") if records else None,
        "current_ktv":         current_ktv,
        "ktv_is_recorded":     ktv_is_recorded,
        "current_phosphorus":  records[0].get("phosphorus") if records else None,
    })


# ── Run a simulation scenario (AJAX) ─────────────────────────────────────────


@router.post("/{patient_id}/simulate")
async def twin_simulate(
    patient_id: int,
    request:    Request,
    db:         Session = Depends(get_db),
):
    _require_staff_role(request)
    user    = get_user(request)
    patient = _get_patient_or_404(db, patient_id)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="Request body must be JSON")

    raw_scenario = body.get("scenario", {})

    # Validate + clean scenario inputs; 422 on hard-limit violations
    sim_warnings: list = []
    try:
        scenario, sim_warnings = validate_scenario(raw_scenario)
    except ScenarioValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Raw monthly records for patient_info / baseline building (needs end-of-month anchors).
    records          = _monthly_records_dicts(db, patient_id)
    past_sessions    = _past_sessions_dicts(db, patient_id)
    patient_info     = _build_patient_info(patient, records, db)
    baseline_session = _build_baseline_session(past_sessions)

    if not records:
        raise HTTPException(status_code=422, detail="No monthly records available for simulation")

    # Merged sequence (interim Hb + synthetic dose-change entries) for ODE fitting.
    ode_records = _merged_records_for_twin(db, patient_id)

    try:
        current_ktv, _ = _resolve_current_ktv(db, patient_id, records, past_sessions)
        
        result = run_scenario(
            patient_id          = patient_id,
            records             = ode_records,
            patient_info        = patient_info,
            baseline_session    = baseline_session,
            past_sessions       = past_sessions,
            monthly_data        = records[0],
            monthly_records_3mo = records[:3],
            scenario            = scenario,
            current_ktv         = current_ktv,
            db                  = db,
        )
        plotly_data = build_twin_plotly_data(result)
    except Exception as e:
        logger.error(f"Digital Twin simulation failed for patient {patient_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Simulation error: {e}")

    # Sanitize NaN/inf/numpy scalars before persisting and before JSON serialisation
    result      = sanitize_json_floats(result)
    plotly_data = sanitize_json_floats(plotly_data)

    # Persist simulation run
    simulation_id = None
    try:
        sim = TwinSimulation(
            patient_id            = patient_id,
            created_by            = getattr(user, "username", str(user)) if user else "unknown",
            scenario_json         = json.dumps(scenario),
            baseline_session_json = json.dumps(baseline_session),
            hb_sim_json           = json.dumps(result.get("hb_sim")),
            ktv_sim_json          = json.dumps({
                "ktv_sim":      result.get("ktv_sim"),
                "ktv_extended": result.get("ktv_extended"),
            }),
            idh_sim_json          = json.dumps(result.get("idh_sim")),
            uf_curve_json         = json.dumps({
                "uf_curve":  result.get("uf_curve"),
                "phosphate": result.get("phosphate"),
                "cascade":   result.get("cascade"),
            }),
            fluid_volume_params   = result.get("fluid_volume"),
        )
        db.add(sim)
        db.commit()
        db.refresh(sim)
        simulation_id = sim.id
    except Exception as e:
        db.rollback()
        logger.warning(f"Failed to persist simulation run: {e}")

    return JSONResponse({
        "plotly":        plotly_data,
        "result":        result,
        "simulation_id": simulation_id,
        "warnings":      sim_warnings,
        "persisted":     simulation_id is not None,
    })


# ── Adopt a simulation scenario ──────────────────────────────────────────────


@router.post("/{patient_id}/simulations/{sim_id}/adopt")
async def twin_adopt(
    patient_id: int,
    sim_id:     int,
    request:    Request,
    db:         Session = Depends(get_db),
):
    """Mark a simulation as adopted (clinician decided to implement the scenario).

    Request body (all optional):
        adopted:          bool   — True to adopt, False to un-adopt
        clinician_notes:  str    — free-text rationale (max 2000 chars)
    """
    from datetime import datetime as _dt

    _require_staff_role(request)
    user = get_user(request)
    _get_patient_or_404(db, patient_id)

    sim = (
        db.query(TwinSimulation)
        .filter(
            TwinSimulation.id == sim_id,
            TwinSimulation.patient_id == patient_id,
        )
        .first()
    )
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")

    try:
        body = await request.json()
    except Exception:
        body = {}

    adopted = bool(body.get("adopted", True))
    notes   = body.get("clinician_notes", "")
    if notes and len(notes) > 2000:
        raise HTTPException(status_code=422, detail="clinician_notes exceeds 2000 characters")

    try:
        sim.adopted          = adopted
        sim.adopted_at       = _dt.utcnow() if adopted else None
        sim.adopted_by       = (getattr(user, "username", str(user)) if user else "unknown") if adopted else None
        sim.clinician_notes  = notes or sim.clinician_notes
        db.add(sim)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Failed to record adoption for sim %s: %s", sim_id, exc)
        raise HTTPException(status_code=500, detail="Failed to record adoption")

    # Best-effort: backfill outcomes if actual data is already available
    try:
        from services.twin_feedback import backfill_twin_outcomes
        backfill_twin_outcomes(db, patient_id=patient_id)
    except Exception as exc:
        logger.debug("Outcome backfill skipped: %s", exc)

    return JSONResponse({"adopted": adopted, "sim_id": sim_id})


# ── Simulation history ────────────────────────────────────────────────────────


@router.get("/{patient_id}/history")
async def twin_history(
    patient_id: int,
    request:    Request,
    db:         Session = Depends(get_db),
):
    _require_staff_role(request)
    _get_patient_or_404(db, patient_id)

    sims = (
        db.query(TwinSimulation)
        .filter(TwinSimulation.patient_id == patient_id)
        .order_by(TwinSimulation.created_at.desc())
        .limit(20)
        .all()
    )

    return JSONResponse([
        {
            "id":         s.id,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "created_by": s.created_by,
            "scenario":   json.loads(s.scenario_json) if s.scenario_json else {},
            "adopted":    s.adopted,
        }
        for s in sims
    ])


# ── DiaSense optical-sensor calibration ingest ───────────────────────────────


@router.post("/{patient_id}/diasense/ingest")
async def twin_diasense_ingest(
    patient_id: int,
    request:    Request,
    db:         Session = Depends(get_db),
):
    """Ingest a DiaSense optical-sensor session and persist a calibration row.

    Closes the sensor → digital-twin loop:
      optical RBV curve  →  k_r_measured  →  stored in diasense_calibrations
      next run_scenario  →  fetches k_r    →  passes as k_r_override to fluid model

    Expected JSON body
    ------------------
    {
      "diasense_session_id": "AGD09_HA1_213320",   // optional
      "session_date":        "2026-05-29",
      "session_duration_min": 240,
      "weight_pre_kg":       39.0,
      "dry_weight_kg":       38.0,
      "albumin_g_dl":        3.8,           // optional, default 3.8
      "hematocrit":          0.35,          // optional, default 0.35
      "uf_target_ml":        700,
      "uf_actual_ml":        700,           // weight-derived or machine readout
      "uf_rate_ml_kg_h":     4.49,          // optional, computed if absent

      // RBV curve — every ~2-min row from DiaSense CSV
      "rbv_curve": [
        {"t_min": 0.06,  "rbv_drop_pct": 0.0},
        {"t_min": 2.06,  "rbv_drop_pct": 0.815},
        ...
      ],

      // Intradialytic BP trend — optional, from machine or BPM log
      "bp_trend": [
        {"time_min": 0,   "sbp": 160, "dbp": 100, "map": 120, "pulse": 103},
        ...
      ],

      // Post-HD symptoms — optional
      "post_hd_dyspnea_likert": 2,
      "post_hd_fatigue_likert": 3,
      "post_hd_cramps":         false,
      "post_hd_nausea":         false,
      "post_hd_headache":       false,

      // Post-HD BCM/BIA — optional (also auto-fetched from ResearchRecord if absent)
      "bcm_post_fluid_overload_l": 0.4,
      "bcm_post_tbw_l":            21.5,
      "bcm_post_phase_angle":      5.1,
      "bcm_delta_overhydration_l": 0.6,

      // Optical sensor summary — optional, used for display only
      "he_od_mean":          0.475,
      "ha_od_mean":          0.494,
      "delta_od_mean":       -0.019,
      "he_od_slope_per_hr":  0.041,
      "grade2plus_count":    0,

      "idh_observed": false,
      "notes":        ""
    }
    """
    from datetime import date as _date
    from fluid_volume_model import calibrate_k_r_from_rbv_curve

    _require_staff_role(request)
    user = get_user(request)
    _get_patient_or_404(db, patient_id)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="Request body must be JSON")

    # ── Required fields ───────────────────────────────────────────────────────
    try:
        session_date = _date.fromisoformat(body["session_date"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=422, detail="session_date (YYYY-MM-DD) is required")

    rbv_curve_raw = body.get("rbv_curve", [])
    if not isinstance(rbv_curve_raw, list) or len(rbv_curve_raw) < 3:
        raise HTTPException(status_code=422, detail="rbv_curve must be a list with ≥ 3 rows")

    weight_pre = float(body.get("weight_pre_kg") or 0)
    uf_target  = float(body.get("uf_target_ml")  or 0)
    session_min = float(body.get("session_duration_min") or 0)
    if weight_pre <= 0 or uf_target <= 0 or session_min <= 0:
        raise HTTPException(
            status_code=422,
            detail="weight_pre_kg, uf_target_ml, and session_duration_min are required and must be > 0",
        )

    # ── Parse RBV curve ───────────────────────────────────────────────────────
    try:
        rbv_drop_series = [float(r["rbv_drop_pct"]) for r in rbv_curve_raw]
        time_min_series = [float(r["t_min"])         for r in rbv_curve_raw]
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"rbv_curve row error: {exc}")

    uf_actual   = float(body.get("uf_actual_ml") or uf_target)
    albumin     = float(body.get("albumin_g_dl") or 3.8)
    hematocrit  = float(body.get("hematocrit")   or 0.35)
    dry_weight  = float(body.get("dry_weight_kg") or (weight_pre - uf_target / 1000))
    uf_rate_ml_min = uf_actual / session_min

    # ── k_r calibration ───────────────────────────────────────────────────────
    cal_result = calibrate_k_r_from_rbv_curve(
        rbv_drop_series = rbv_drop_series,
        time_min_series = time_min_series,
        uf_rate_ml_min  = uf_rate_ml_min,
        weight_kg       = weight_pre,
        albumin_g_dl    = albumin,
        hematocrit      = hematocrit,
    )
    if not cal_result.get("success"):
        raise HTTPException(status_code=422, detail=f"k_r calibration failed: {cal_result.get('error')}")

    # ── UF achievement ────────────────────────────────────────────────────────
    uf_achievement = round((uf_actual / uf_target) * 100, 1) if uf_target > 0 else None
    uf_rate_ml_kg_h_val = body.get("uf_rate_ml_kg_h") or round(
        (uf_actual / session_min * 60) / weight_pre, 3
    )

    # ── BP trend nadir ────────────────────────────────────────────────────────
    bp_trend = body.get("bp_trend") or []
    bp_nadir_sys_val = bp_nadir_map_val = bp_nadir_t_val = None
    if bp_trend:
        sbp_vals = [(r.get("sbp"), r.get("map"), r.get("time_min")) for r in bp_trend if r.get("sbp")]
        if sbp_vals:
            bp_nadir_row = min(sbp_vals, key=lambda x: x[0])
            bp_nadir_sys_val = bp_nadir_row[0]
            bp_nadir_map_val = bp_nadir_row[1]
            bp_nadir_t_val   = bp_nadir_row[2]

    # ── Auto-fetch post-HD BCM from ResearchRecord if not supplied ────────────
    bcm_post_fo  = body.get("bcm_post_fluid_overload_l")
    bcm_post_tbw = body.get("bcm_post_tbw_l")
    bcm_phase    = body.get("bcm_post_phase_angle")
    bcm_delta    = body.get("bcm_delta_overhydration_l")
    if bcm_post_fo is None:
        try:
            from db.models.research import ResearchRecord
            bcm_rec = (
                db.query(ResearchRecord)
                .filter(
                    ResearchRecord.patient_id == patient_id,
                    ResearchRecord.test_type.ilike("%BCM%"),
                    ResearchRecord.test_date >= session_date,
                )
                .order_by(ResearchRecord.test_date.asc())
                .first()
            )
            if bcm_rec and bcm_rec.data:
                import json as _json
                bcm_data = _json.loads(bcm_rec.data)
                bcm_post_fo  = bcm_data.get("fluid_overload") or bcm_data.get("overhydration_l")
                bcm_post_tbw = bcm_data.get("tbw_liters") or bcm_post_tbw
                bcm_phase    = bcm_data.get("phase_angle") or bcm_phase
        except Exception as _bcm_exc:
            logger.debug("BCM auto-fetch skipped: %s", _bcm_exc)

    # ── Sampled RBV curve for storage (every 5th point) ───────────────────────
    sampled = [
        {"t_min": time_min_series[i], "rbv_drop_pct": rbv_drop_series[i]}
        for i in range(0, len(time_min_series), 5)
    ]

    # ── Persist ───────────────────────────────────────────────────────────────
    try:
        cal = DiaSenseCalibration(
            patient_id              = patient_id,
            session_date            = session_date,
            diasense_session_id     = body.get("diasense_session_id"),
            diasense_k_r            = cal_result["k_r_measured"],
            k_r_estimated           = cal_result["k_r_estimated"],
            rbv_nadir_pct           = cal_result["rbv_nadir_pct"],
            rbv_nadir_time_min      = cal_result["rbv_nadir_time_min"],
            rbv_breach              = cal_result["rbv_breach"],
            plasma_refill_rate_ml_min = cal_result["plasma_refill_rate_ml_min"],
            uf_target_ml            = uf_target,
            uf_actual_ml            = uf_actual,
            uf_rate_ml_kg_h         = uf_rate_ml_kg_h_val,
            uf_achievement_pct      = uf_achievement,
            session_duration_min    = session_min,
            weight_pre_kg           = weight_pre,
            dry_weight_kg           = dry_weight,
            albumin_g_dl            = albumin,
            bp_trend_json           = json.dumps(bp_trend) if bp_trend else None,
            bp_nadir_sys            = bp_nadir_sys_val,
            bp_nadir_map            = bp_nadir_map_val,
            bp_nadir_time_min       = bp_nadir_t_val,
            idh_observed            = bool(body.get("idh_observed", False)),
            post_hd_dyspnea_likert  = body.get("post_hd_dyspnea_likert"),
            post_hd_fatigue_likert  = body.get("post_hd_fatigue_likert"),
            post_hd_cramps          = body.get("post_hd_cramps"),
            post_hd_nausea          = body.get("post_hd_nausea"),
            post_hd_headache        = body.get("post_hd_headache"),
            bcm_post_fluid_overload_l  = bcm_post_fo,
            bcm_post_tbw_l             = bcm_post_tbw,
            bcm_post_phase_angle       = bcm_phase,
            bcm_delta_overhydration_l  = bcm_delta,
            he_od_mean              = body.get("he_od_mean"),
            ha_od_mean              = body.get("ha_od_mean"),
            delta_od_mean           = body.get("delta_od_mean"),
            he_od_slope_per_hr      = body.get("he_od_slope_per_hr"),
            grade2plus_count        = body.get("grade2plus_count"),
            rbv_curve_json          = json.dumps(sampled),
            notes                   = body.get("notes"),
            created_by              = getattr(user, "username", str(user)) if user else "unknown",
        )
        db.add(cal)
        db.commit()
        db.refresh(cal)
    except Exception as exc:
        db.rollback()
        logger.error("Failed to persist DiaSense calibration for patient %s: %s", patient_id, exc)
        raise HTTPException(status_code=500, detail="Failed to persist calibration")

    return JSONResponse({
        "calibration_id":            cal.id,
        "patient_id":                patient_id,
        "session_date":              str(session_date),
        "diasense_k_r":              cal_result["k_r_measured"],
        "k_r_estimated":             cal_result["k_r_estimated"],
        "k_r_ratio":                 round(cal_result["k_r_measured"] / cal_result["k_r_estimated"], 3),
        "rbv_nadir_pct":             cal_result["rbv_nadir_pct"],
        "rbv_nadir_time_min":        cal_result["rbv_nadir_time_min"],
        "rbv_breach":                cal_result["rbv_breach"],
        "plasma_refill_rate_ml_min": cal_result["plasma_refill_rate_ml_min"],
        "uf_target_ml":              uf_target,
        "uf_actual_ml":              uf_actual,
        "uf_achievement_pct":        uf_achievement,
        "uf_rate_ml_kg_h":           uf_rate_ml_kg_h_val,
        "message": (
            "k_r calibrated and stored — next simulation for this patient will use "
            f"diasense_k_r={cal_result['k_r_measured']:.5f} mL/min/mmHg as k_r_override."
        ),
    })
