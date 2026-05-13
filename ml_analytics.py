"""
ml_analytics.py
===============
Slim entry-point / orchestrator for the HD clinical ML engine.

All heavy logic has been split into focused sub-modules:
  ml_esa.py      — ESA dose normalization and hyporesponse detection
  ml_trends.py   — Kalman / OLS trend prediction (Hb, Albumin, Iron)
  ml_risk.py     — Deterioration and mortality risk models
  ml_cascade.py  — MIA, cardiorenal, AVF, PDS, BFR cascade analyses

Re-exports everything so `from ml_analytics import predict_mortality_risk`
etc. still works without breaking existing router imports.
"""
import json
import re
import math
import statistics
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any

import numpy as np
from sqlalchemy.orm import Session

from database import MonthlyRecord, Patient, ResearchRecord

# ── Re-exports from sub-modules ──────────────────────────────────────────────

from ml_esa import (
    normalize_epo_dose,
    get_mircera_equivalent,
    _parse_epo_dose,
    detect_epo_hyporesponse,
    _resolve_weekly_iu_iv,
    _MIRCERA_SYNONYMS,
    _DARBE_SYNONYMS,
    _EPOETIN_SYNONYMS,
)

from ml_trends import (
    predict_hb_trajectory,
    assess_albumin_decline,
    classify_iron_status,
    compute_ml_readiness,
    _month_to_ordinal,
    _linear_trend_with_ci,
    _hb_endo,
    _hb_kalman,
    _albumin_kalman,
    _kalman_trend,
    _hb_trajectory_severity,
    _hb_trajectory_message,
)

from ml_risk import (
    predict_mortality_risk,
    compute_deterioration_risk,
    train_deterioration_model,
    get_deterioration_model_status,
    compute_davies_score,
    get_all_patients_mortality_risk,
    get_high_risk_mortality_count,
    DETERIORATION_FEATURE_NAMES,
    _build_feature_vector,
    _extract_record_features_for_training,
    _extract_analytics_features_for_inference,
    _load_deterioration_model,
    _DETERIORATION_MODEL,
    _MODEL_LOAD_TIME,
    _MODEL_PATH,
    _MODEL_META_PATH,
    _load_xgb_models,
    _sigmoid,
    _mortality_uncertainty_band,
    _rule_based_log_odds_fallback,
    _XGB_MODELS,
    _XGB_LOAD_ATTEMPTED,
)

from ml_cascade import (
    compute_mia_score,
    analyze_mia_cascade,
    analyze_cardiorenal_cascade,
    analyze_avf_maturation,
    analyze_pds,
    analyze_bfr_trend,
    detect_occult_overload,
    _compute_gnri,
)

logger = logging.getLogger(__name__)


# ── Functions that remain in this entry-point module ─────────────────────────

def get_patient_research_data(db: Session, patient_id: int) -> Dict[str, Any]:
    """
    Retrieve and parse all specialized academic/research tests for a patient.
    """
    records = db.query(ResearchRecord).filter(
        ResearchRecord.patient_id == patient_id
    ).order_by(ResearchRecord.test_date.desc()).all()

    research_data = {}
    for r in records:
        if r.test_type not in research_data:
            try:
                parsed = json.loads(r.data) if r.data else {}
                research_data[r.test_type] = {
                    "date": r.test_date.isoformat(),
                    "metrics": parsed
                }
            except json.JSONDecodeError:
                pass

    return research_data


def get_month_label(month_str: str) -> str:
    try:
        return datetime.strptime(month_str, "%Y-%m").strftime("%B %Y")
    except (ValueError, TypeError):
        return month_str


def compute_target_score(df: List[Dict]) -> Dict:
    """
    Calculate 10-point clinical achievement score based on KDOQI/KDIGO targets.
    """
    if not df:
        return {"score": 0, "status": "No Data"}
    latest = df[0]
    points = 0
    available = 0
    missing_fields = []

    def _score(met: bool):
        nonlocal points, available
        available += 1
        if met:
            points += 1

    hb = latest.get("hb")
    if hb is not None:          _score(hb >= 10)
    else:                       missing_fields.append("Hb")

    albumin = latest.get("albumin")
    if albumin is not None:     _score(albumin >= 3.5)
    else:                       missing_fields.append("Albumin")

    phosphorus = latest.get("phosphorus")
    if phosphorus is not None:  _score(phosphorus <= 5.5)
    else:                       missing_fields.append("Phosphorus")

    idwg = latest.get("idwg")
    if idwg is not None:        _score(idwg <= 2.5)
    else:                       missing_fields.append("IDWG")

    urr = latest.get("urr")
    if urr is not None:         _score(urr >= 65)
    else:                       missing_fields.append("URR")

    ipth = latest.get("ipth")
    if ipth is not None:        _score(150 <= ipth <= 600)
    else:                       missing_fields.append("iPTH")

    ferritin = latest.get("serum_ferritin")
    if ferritin is not None:    _score(ferritin >= 200)
    else:                       missing_fields.append("Ferritin")

    tsat = latest.get("tsat")
    if tsat is not None:        _score(tsat >= 20)
    else:                       missing_fields.append("TSAT")

    bp_sys = latest.get("bp_sys")
    if bp_sys is not None:
        _score(bp_sys <= 140)
        _score(bp_sys >= 110)
    else:
        missing_fields.append("BP Systolic")

    if available == 0:
        return {
            "available": False,
            "error":     "No clinical targets measurable.",
            "data": {
                "score": 0, "raw_score": 0, "available": 0, "status": "No Data", "label": "No Data", "inputs_missing": missing_fields
            }
        }

    normalized = round(points / available * 10)
    status = "Optimal" if normalized >= 8 else "Sub-optimal" if normalized >= 6 else "Critical"
    return {
        "available": True,
        "error":     None,
        "data": {
            "score": normalized,
            "raw_score": points,
            "available": available,
            "status": status,
            "label": status,
            "inputs_missing": missing_fields
        }
    }


def run_patient_analytics(
    db: Session,
    patient_id: int,
    prefetched_records: Optional[List[MonthlyRecord]] = None
) -> Dict:
    if prefetched_records is not None:
        records = prefetched_records
    else:
        records = (
            db.query(MonthlyRecord)
            .filter(MonthlyRecord.patient_id == patient_id)
            .all()
        )

    # Deduplicate monthly records (latest entry wins)
    seen_months = {}
    deduped = []
    for r in records:
        if r.record_month not in seen_months:
            seen_months[r.record_month] = True
            deduped.append(r)
    records = deduped

    # Defensive sort (descending) to ensure df[0] is always the most recent month
    records.sort(key=lambda x: x.record_month, reverse=True)

    df = [
        {
            "month": r.record_month,
            "hb": r.hb,
            "albumin": r.albumin,
            "phosphorus": r.phosphorus,
            "idwg": r.idwg,
            "urr": r.urr,
            "serum_ferritin": r.serum_ferritin,
            "tsat": r.tsat,
            "ipth": r.ipth,
            "bp_sys": r.bp_sys,
            "epo_weekly_units": r.epo_weekly_units,
            "epo_mircera_dose": r.epo_mircera_dose,
            "desidustat_dose": getattr(r, "desidustat_dose", None),
            "weight": r.target_dry_weight or (r.patient.dry_weight if r.patient else None),
            # mortality model inputs
            "wbc_count":                  r.wbc_count,
            # BUG 4 FIX: add neutrophil_count to the per-record dict
            "neutrophil_count":           r.neutrophil_count,
            "crp":                        r.crp,
            "hospitalization_this_month": r.hospitalization_this_month,
            "transfusion_units":          getattr(r, "blood_transfusion_units", None) or 0,
            "transfusion_date":           getattr(r, "transfusion_date", None),
            # Bayesian intervention fields
            "iv_iron_dose":               r.iv_iron_dose,
            "phosphate_binder_type":      r.phosphate_binder_type,
            "residual_urine_output":      r.residual_urine_output,
            "vit_d":                      r.vit_d,
            "nt_probnp":                  r.nt_probnp,
        }
        for r in records
    ]

    logger.debug("PATIENT %d: loaded %d record(s)", patient_id, len(df))

    if not df:
        return {"status": "no_data"}

    # Apply interim lab overrides to the most recent month's row
    if df:
        from database import InterimLabRecord
        _interim_overridable = ("hb", "albumin", "phosphorus", "calcium")
        _interim_rows = (
            db.query(InterimLabRecord)
            .filter(
                InterimLabRecord.patient_id == patient_id,
                InterimLabRecord.record_month == df[0]["month"],
                InterimLabRecord.parameter.in_(_interim_overridable),
            )
            .order_by(InterimLabRecord.lab_date.asc())
            .all()
        )
        for il in _interim_rows:
            df[0][il.parameter] = il.value

    def _get_latest_info(key: str, default=None):
        for i, entry in enumerate(df):
            if entry.get(key) is not None:
                return entry[key], i
        return default, None

    # Latest available for sparse/infrequent labs (scan last 12 months)
    latest_sparse = {}
    lab_staleness = {}

    _sparse_keys = [
        "serum_ferritin", "tsat", "serum_iron", "ipth", "vit_d", "crp",
        "nt_probnp", "residual_urine_output", "ejection_fraction",
        "diastolic_dysfunction", "echo_date"
    ]

    for k in _sparse_keys:
        val, months_ago = _get_latest_info(k)
        latest_sparse[k] = val
        if months_ago is not None:
            lab_staleness[k] = months_ago

    # Update the most recent record with these carry-forward values for analysis
    df[0] = {**df[0], **latest_sparse}

    # Build patient-level info for mortality model from ORM relationship
    patient_obj = records[0].patient if records else None
    patient_info: Dict = {}
    if patient_obj:
        patient_info["cad_status"]        = getattr(patient_obj, "cad_status",        None)
        patient_info["dm_status"]         = getattr(patient_obj, "dm_status",         None)
        patient_info["chf_status"]        = getattr(patient_obj, "chf_status",        None)
        patient_info["age"]               = getattr(patient_obj, "age",               None)
        patient_info["history_of_pvd"]    = getattr(patient_obj, "history_of_pvd",    None)
        patient_info["dm_end_organ_damage"] = getattr(patient_obj, "dm_end_organ_damage", None)
        patient_info["solid_tumor"]       = getattr(patient_obj, "solid_tumor",       None)
        patient_info["leukemia"]          = getattr(patient_obj, "leukemia",          None)
        patient_info["lymphoma"]          = getattr(patient_obj, "lymphoma",          None)

        ef_raw = latest_sparse.get("ejection_fraction")
        if ef_raw is None:
            ef_raw = getattr(patient_obj, "ejection_fraction", None)
        patient_info["ef"] = ef_raw

        dd_raw = latest_sparse.get("diastolic_dysfunction")
        if dd_raw is None:
            dd_raw = getattr(patient_obj, "diastolic_dysfunction", None)
        patient_info["diastolic_dysfunction"] = dd_raw

    from bayesian_analytics import compute_bayesian_alert_profile, augment_mortality_risk

    # BUG 6 FIX: log exceptions with full traceback and expose error key in result
    try:
        hb_traj    = predict_hb_trajectory(df)
        epo_resp   = detect_epo_hyporesponse(df, hb_traj)
        alb_risk   = assess_albumin_decline(df)
        iron_stat  = classify_iron_status(df[0], lab_staleness)
        target_sc  = compute_target_score(df)
        det_risk   = compute_deterioration_risk(hb_traj, alb_risk, target_sc, epo_resp, patient_info)
        mort_risk  = predict_mortality_risk(df, patient_info)
        mia_status = compute_mia_score(db, patient_id)
        bay_profile = compute_bayesian_alert_profile(df, patient_info)
        mort_risk   = augment_mortality_risk(mort_risk, bay_profile)
        davies      = compute_davies_score(patient_info, df[0])
        analytics_error = None
    except Exception as e:
        logger.exception("Error in patient analytics sub-components for patient %d: %s", patient_id, e)
        analytics_error = str(e)
        hb_traj = hb_traj if 'hb_traj' in locals() else {"available": False, "data": {}}
        epo_resp = epo_resp if 'epo_resp' in locals() else {"available": False, "data": {}}
        alb_risk = alb_risk if 'alb_risk' in locals() else {"available": False, "data": {}}
        iron_stat = iron_stat if 'iron_stat' in locals() else {"available": False, "data": {}}
        target_sc = target_sc if 'target_sc' in locals() else {"available": False, "data": {}}
        det_risk = det_risk if 'det_risk' in locals() else {"available": False, "data": {}}
        mort_risk = mort_risk if 'mort_risk' in locals() else {"available": False, "data": {}}
        mia_status = mia_status if 'mia_status' in locals() else {"available": False, "data": {}}
        bay_profile = bay_profile if 'bay_profile' in locals() else {"available": False, "data": {}}
        davies = davies if 'davies' in locals() else {"available": False, "data": {}}

    result = {
        "status": "ok",
        "hb_trajectory": hb_traj,
        "epo_response": epo_resp,
        "albumin_risk": alb_risk,
        "iron_status": iron_stat,
        "target_score": target_sc,
        "deterioration_risk": det_risk,
        "mortality_risk": mort_risk,
        "mia_status": mia_status,
        "bay_profile": bay_profile,
        "davies": davies,
        "history_count": len(df),
        "n_months": len(df),
        "lab_staleness": lab_staleness,
    }
    if analytics_error:
        result["analytics_error"] = analytics_error
    return result


def run_cohort_analytics(db: Session) -> Dict:
    # PERF FIX 1: filter to last 13 months instead of loading all records
    from datetime import date
    import calendar
    today = date.today()
    cutoff = f"{today.year - 1}-{str(today.month).zfill(2)}"

    records = (
        db.query(MonthlyRecord)
        .filter(MonthlyRecord.record_month >= cutoff)
        .order_by(MonthlyRecord.record_month)
        .all()
    )
    if not records:
        return {"available": False}

    # Define parameters to track
    params = [
        "hb", "albumin", "phosphorus", "calcium", "serum_ferritin",
        "tsat", "single_pool_ktv", "urr", "ipth", "serum_potassium", "serum_creatinine", "idwg"
    ]

    trends: Dict = {}
    for r in records:
        m = r.record_month
        if m not in trends:
            trends[m] = {p: [] for p in params}

        for p in params:
            val = getattr(r, p, None)
            if val is not None:
                trends[m][p].append(val)

    months = sorted(trends.keys())[-12:]
    result = {
        "available": True,
        "months": months,
        "latest_month": months[-1] if months else None,
    }

    # N_IQR_RELIABLE: minimum patients per month required to display a meaningful IQR.
    # Below this, p25/p75 are set to None so charts suppress the IQR band entirely,
    # preventing false clinical confidence from small-cohort box plots.
    N_IQR_RELIABLE = 10

    for p in params:
        stats_list = []
        for m in months:
            vals = trends[m][p]
            if not vals:
                stats_list.append({
                    "median": None, "p25": None, "p75": None,
                    "n": 0, "reliable": False, "warning": "No data this month"
                })
                continue

            med = statistics.median(vals)
            sv  = sorted(vals)
            n   = len(sv)

            if n < N_IQR_RELIABLE:
                # Suppress IQR — show only median and warn
                stats_list.append({
                    "median":   round(med, 2),
                    "p25":      None,   # None signals chart to hide IQR band
                    "p75":      None,
                    "n":        n,
                    "reliable": False,
                    "warning":  (
                        f"n={n} — IQR hidden (need ≥{N_IQR_RELIABLE} patients for reliable percentiles). "
                        "Median shown only."
                    )
                })
                continue

            # Sufficient N — show full statistics
            stats_list.append({
                "median":   round(med, 2),
                "p25":      round(float(np.percentile(sv, 25)), 2),
                "p75":      round(float(np.percentile(sv, 75)), 2),
                "n":        n,
                "reliable": True,
                "warning":  None
            })
        result[p] = stats_list

    return result


def get_at_risk_trends(db: Session, parameter: str, month: str = None) -> Dict:
    """
    Find patients whose current report for 'parameter' is out of range,
    and return their trend for the last 4 months.
    """
    if not month:
        from dashboard_logic import get_current_month_str
        month = get_current_month_str()

    thresholds = {
        "hb": {"min": 10.0},
        "albumin": {"min": 3.5},
        "phosphorus": {"max": 5.5},
        "calcium": {"min": 8.4, "max": 10.2},
        "serum_ferritin": {"min": 200},
        "tsat": {"min": 20},
        "single_pool_ktv": {"min": 1.2},
        "urr": {"min": 65},
        "ipth": {"min": 150, "max": 600},
        "serum_potassium": {"min": 3.5, "max": 5.5},
        "idwg": {"max": 2.5}
    }

    thresh = thresholds.get(parameter)
    if not thresh:
        return {"patients": []}

    curr_records = db.query(MonthlyRecord).filter(MonthlyRecord.record_month == month).all()
    at_risk_patient_ids = []

    for r in curr_records:
        val = getattr(r, parameter, None)
        if parameter == "calcium" and r.calcium is not None and r.albumin is not None:
            val = r.calcium + 0.8 * (3.5 - r.albumin)

        if val is None: continue

        is_out = False
        if "min" in thresh and val < thresh["min"]: is_out = True
        if "max" in thresh and val > thresh["max"]: is_out = True

        if is_out:
            at_risk_patient_ids.append(r.patient_id)

    if not at_risk_patient_ids:
        return {"patients": []}

    from datetime import datetime, timedelta
    def get_prev_month(m_str):
        try:
            dt = datetime.strptime(m_str, "%Y-%m")
            prev = dt.replace(day=1) - timedelta(days=1)
            return prev.strftime("%Y-%m")
        except Exception:
            return m_str

    target_months = [month]
    m = month
    for _ in range(3):
        m = get_prev_month(m)
        target_months.append(m)
    target_months.reverse()  # [m-3, m-2, m-1, m]

    # Batch Fetch Data to Avoid N+1 Problem
    patients = db.query(Patient).filter(Patient.id.in_(at_risk_patient_ids)).all()
    patient_map = {p.id: p for p in patients}

    all_history = (
        db.query(MonthlyRecord)
        .filter(
            MonthlyRecord.patient_id.in_(at_risk_patient_ids),
            MonthlyRecord.record_month.in_(target_months)
        )
        .order_by(MonthlyRecord.record_month.asc())
        .all()
    )

    history_by_patient = {}
    for h in all_history:
        if h.patient_id not in history_by_patient:
            history_by_patient[h.patient_id] = {}

        h_val = getattr(h, parameter, None)
        if parameter == "calcium" and h.calcium is not None and h.albumin is not None:
            h_val = h.calcium + 0.8 * (3.5 - h.albumin)

        history_by_patient[h.patient_id][h.record_month] = h_val

    results = []
    for pid in at_risk_patient_ids:
        patient = patient_map.get(pid)
        if not patient:
            continue

        hist_map = history_by_patient.get(pid, {})

        results.append({
            "id": patient.id,
            "name": patient.name,
            "trend": [round(hist_map.get(m), 2) if hist_map.get(m) is not None else None for m in target_months]
        })

    return {
        "months": target_months,
        "patients": results,
        "parameter": parameter
    }
