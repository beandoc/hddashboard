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
    get_db,
)
from dependencies import get_user, _require_staff_role
from ml_twin import run_scenario, build_twin_plotly_data

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
            "hb":                 rec.hb,
            "serum_ferritin":     rec.serum_ferritin,
            "tsat":               rec.tsat,
            "albumin":            rec.albumin,
            "single_pool_ktv":    rec.single_pool_ktv,
            "crp":                getattr(rec, "crp", None),
            "last_prehd_weight":  rec.last_prehd_weight,
            "weight":             rec.last_prehd_weight,
            "epo_mircera_dose":   rec.epo_mircera_dose,
            "epo_weekly_units":   rec.epo_weekly_units,
            "iv_iron_dose":       rec.iv_iron_dose,
            "pre_dialysis_urea":  rec.pre_dialysis_urea,
            "post_dialysis_urea": rec.post_dialysis_urea,
            "phosphorus":         rec.phosphorus,
            "ufr":                rec.ufr,
            "record_month":       rec.record_month,
        }
        for rec in recs
    ]


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
            "arterial_line_pressure": getattr(s, "arterial_line_pressure", None),
            "venous_line_pressure":   getattr(s, "venous_line_pressure", None),
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


def _build_baseline_session(past_sessions: list) -> dict:
    """Use the most recent session as the baseline session plan."""
    if not past_sessions:
        return {}
    s = past_sessions[0]
    return {
        "pre_hd_sbp":             s.get("pre_hd_sbp"),
        "uf_volume":              s.get("uf_volume"),
        "dialysate_temp":         s.get("dialysate_temp", 36.5),
        "dialysate_sodium":       s.get("dialysate_sodium", 138),
        "idwg_kg":                s.get("idwg_kg"),
        "session_duration_h":     (s.get("actual_session_time") or 240) / 60,
        "antihypertensive_prehd": s.get("antihypertensive_prehd", False),
        "intradialytic_meals":    s.get("intradialytic_meals", False),
        "qb_ml_min":              s.get("blood_flow_rate", 300.0),
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
    patient_info  = _build_patient_info(patient, records, db)
    baseline_session = _build_baseline_session(past_sessions)

    # Run the default scenario (no changes = baseline vs itself)
    default_result = {}
    default_plotly = {}
    if records:
        try:
            default_result = run_scenario(
                patient_id          = patient_id,
                records             = records,
                patient_info        = patient_info,
                baseline_session    = baseline_session,
                past_sessions       = past_sessions,
                monthly_data        = records[0] if records else {},
                monthly_records_3mo = records[:3],
                scenario            = {},
                db                  = db,
            )
            default_plotly = build_twin_plotly_data(default_result)
        except Exception as e:
            logger.warning(f"Digital Twin default run failed for patient {patient_id}: {e}")

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
    if records:
        from ml_esa import _resolve_weekly_iu_sc
        current_iu = _resolve_weekly_iu_sc(records[0])

    # spKt/V: prefer recorded monthly value → simulation baseline → compute from
    # most recent monthly record that has both pre and post urea
    current_ktv = None
    if records:
        current_ktv = records[0].get("single_pool_ktv")
        if current_ktv is None:
            current_ktv = (default_result.get("ktv_sim", {}).get("baseline_ktv")
                           if default_result else None)
        if current_ktv is None:
            from ml_twin import calculate_ktv_daugirdas, _UREA_MG_DL_TO_BUN
            uf_L = (past_sessions[0].get("uf_volume") or 1500) / 1000 if past_sessions else 1.5
            session_h = (past_sessions[0].get("actual_session_time") or 240) / 60 if past_sessions else 4.0
            for rec in records:
                pre  = rec.get("pre_dialysis_urea")
                post = rec.get("post_dialysis_urea")
                wt   = rec.get("last_prehd_weight") or rec.get("weight")
                if pre and post and wt:
                    post_wt = wt - uf_L
                    # Convert urea (mg/dL) → BUN (mg/dL) before Daugirdas formula
                    ktv = calculate_ktv_daugirdas(
                        pre  * _UREA_MG_DL_TO_BUN,
                        post * _UREA_MG_DL_TO_BUN,
                        session_h, uf_L, post_wt,
                    )
                    if ktv is not None and 0.5 <= ktv <= 4.0:
                        current_ktv = round(ktv, 2)
                    break
        if current_ktv is not None:
            current_ktv = round(float(current_ktv), 2)

    ktv_is_recorded = bool(records and records[0].get("single_pool_ktv"))

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

    scenario = body.get("scenario", {})

    records          = _monthly_records_dicts(db, patient_id)
    past_sessions    = _past_sessions_dicts(db, patient_id)
    patient_info     = _build_patient_info(patient, records, db)
    baseline_session = _build_baseline_session(past_sessions)

    if not records:
        raise HTTPException(status_code=422, detail="No monthly records available for simulation")

    try:
        result = run_scenario(
            patient_id          = patient_id,
            records             = records,
            patient_info        = patient_info,
            baseline_session    = baseline_session,
            past_sessions       = past_sessions,
            monthly_data        = records[0],
            monthly_records_3mo = records[:3],
            scenario            = scenario,
            db                  = db,
        )
        plotly_data = build_twin_plotly_data(result)
    except Exception as e:
        logger.error(f"Digital Twin simulation failed for patient {patient_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Simulation error: {e}")

    # Persist simulation run
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
    except Exception as e:
        logger.warning(f"Failed to persist simulation run: {e}")

    return JSONResponse({"plotly": plotly_data, "result": result})


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
