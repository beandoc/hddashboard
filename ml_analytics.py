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
            # cardiac / echo fields (sparse — carried forward via _sparse_keys)
            "serum_iron":                 r.serum_iron,
            "ejection_fraction":          r.ejection_fraction,
            "diastolic_dysfunction":      r.diastolic_dysfunction,
            "echo_date":                  r.echo_date,
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

        # IDH fraction: fraction of last 20 sessions with intradialytic hypotension.
        # This is the correct Xu et al. "IDH" feature — NOT coronary artery disease.
        from database import SessionRecord
        _sess_flags = (
            db.query(SessionRecord.idh_episode)
            .filter(
                SessionRecord.patient_id == patient_id,
                SessionRecord.idh_episode.isnot(None),
            )
            .order_by(SessionRecord.session_date.desc())
            .limit(20)
            .all()
        )
        if _sess_flags:
            _flags = [r[0] for r in _sess_flags]
            patient_info["idh_fraction"] = round(sum(1 for f in _flags if f) / len(_flags), 3)

    from bayesian_analytics import compute_bayesian_alert_profile, attach_bayesian_signal

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
        mort_risk   = attach_bayesian_signal(mort_risk, bay_profile)
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
                    "mean":     None,
                    "std":      None,
                    "cv_percent": None,
                    "is_normal": False,
                    "shapiro_p": None,
                    "outliers": [],
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
            mean_val = statistics.mean(vals)
            std_val = statistics.stdev(vals) if n > 1 else 0.0
            cv_percent = round((std_val / mean_val * 100), 1) if mean_val != 0 else 0.0

            # Shapiro-Wilk Test for Normality
            is_normal = False
            shapiro_p = None
            if n >= 3:
                try:
                    from scipy.stats import shapiro
                    stat, p_val = shapiro(vals)
                    shapiro_p = round(p_val, 4)
                    is_normal = bool(p_val >= 0.05)
                except ImportError:
                    pass
                except Exception:
                    pass

            # Outlier Detection using Robust Z-Score (MAD-based)
            mad = statistics.median([abs(x - med) for x in vals])
            outliers = []
            if mad > 0:
                for x in vals:
                    robust_z = abs(x - med) / (1.4826 * mad)
                    if robust_z > 3.0: # threshold for outlier
                        outliers.append(x)
            
            stats_list.append({
                "median":   round(med, 2),
                "mean":     round(mean_val, 2),
                "std":      round(std_val, 2),
                "cv_percent": cv_percent,
                "is_normal": is_normal,
                "shapiro_p": shapiro_p,
                "outliers": list(set(outliers)),
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

# ── Group Comparison Analytics ────────────────────────────────────────────────

def run_group_comparison(groups: Dict[str, List[float]], test_type: str = "mann-whitney") -> Dict:
    """
    Perform statistical group comparisons.
    `groups` format for continuous data: {"Diabetic": [12.1, 10.5, ...], "Non-Diabetic": [11.2, 11.5, ...]}
    `groups` format for categorical data (Chi-Square): {"High-Flux": [10, 50], "Low-Flux": [25, 40]}
       where lists are counts [Events, Non-Events].
    `test_type`: "mann-whitney", "kruskal-wallis", "chi-square"
    """
    result = {
        "test_type": test_type,
        "available": False,
        "p_value": None,
        "statistic": None,
        "significant": False,
        "message": ""
    }

    try:
        from scipy import stats
    except ImportError:
        result["message"] = "scipy is required for advanced statistical tests."
        return result

    if test_type == "mann-whitney":
        keys = list(groups.keys())
        if len(keys) != 2:
            result["message"] = "Mann-Whitney requires exactly 2 groups."
            return result
        
        g1, g2 = groups[keys[0]], groups[keys[1]]
        # Filter Nones
        g1 = [x for x in g1 if x is not None]
        g2 = [x for x in g2 if x is not None]
        
        if len(g1) < 3 or len(g2) < 3:
            result["message"] = "Insufficient data points (minimum 3 per group required)."
            return result
            
        stat, p_val = stats.mannwhitneyu(g1, g2, alternative='two-sided')
        result.update({
            "available": True,
            "p_value": round(p_val, 4),
            "statistic": round(stat, 2),
            "significant": p_val < 0.05,
            "message": f"Mann-Whitney U Test: {'Significant' if p_val < 0.05 else 'No significant'} difference between {keys[0]} and {keys[1]} (p={p_val:.4f})."
        })

    elif test_type == "kruskal-wallis":
        valid_groups = []
        group_names = []
        for name, vals in groups.items():
            clean_vals = [x for x in vals if x is not None]
            if len(clean_vals) >= 3:
                valid_groups.append(clean_vals)
                group_names.append(name)
                
        if len(valid_groups) < 2:
            result["message"] = "Kruskal-Wallis requires at least 2 valid groups with >= 3 data points each."
            return result
            
        stat, p_val = stats.kruskal(*valid_groups)
        result.update({
            "available": True,
            "p_value": round(p_val, 4),
            "statistic": round(stat, 2),
            "significant": p_val < 0.05,
            "message": f"Kruskal-Wallis H-Test: {'Significant' if p_val < 0.05 else 'No significant'} variance across groups ({', '.join(group_names)}) (p={p_val:.4f})."
        })

    elif test_type == "chi-square":
        # expects a contingency table format: [[a,b], [c,d]]
        table = []
        keys = list(groups.keys())
        for k in keys:
            table.append(groups[k])
            
        # table must be 2D and have at least 2 rows and 2 columns
        if len(table) < 2 or not all(isinstance(row, list) and len(row) >= 2 for row in table):
            result["message"] = "Chi-Square requires a valid contingency table (e.g., counts of Event vs Non-Event for >= 2 groups)."
            return result
            
        stat, p_val, dof, expected = stats.chi2_contingency(table)
        min_expected = float(np.min(expected))
        chi_warning = (
            f"Warning: minimum expected cell count is {min_expected:.1f} (<5). "
            "Chi-square approximation may be unreliable; consider Fisher's exact test."
        ) if min_expected < 5 else None
        result.update({
            "available": True,
            "p_value": round(p_val, 4),
            "statistic": round(stat, 2),
            "significant": p_val < 0.05,
            "min_expected_cell": round(min_expected, 2),
            "warning": chi_warning,
            "message": (
                f"Chi-Square Test of Independence: {'Significant' if p_val < 0.05 else 'No significant'} "
                f"association found (p={p_val:.4f})."
                + (f" {chi_warning}" if chi_warning else "")
            ),
        })
        
    else:
        result["message"] = f"Unknown test type: {test_type}"

    return result

# ── Correlation Analytics ─────────────────────────────────────────────────────

def run_correlation_analysis(x: List[float], y: List[float], z: List[float] = None, method: str = "spearman") -> Dict:
    """
    Perform correlation analysis between two variables, optionally controlling for a third.
    method: "spearman" (default for clinical/biological data) or "pearson".
    If z is provided, performs Partial Correlation.
    """
    result = {
        "method": method,
        "is_partial": z is not None,
        "available": False,
        "r": None,
        "p_value": None,
        "significant": False,
        "message": ""
    }

    try:
        from scipy import stats
        import numpy as np
    except ImportError:
        result["message"] = "scipy/numpy required for correlation analysis."
        return result

    # Alignment and cleaning
    data = []
    if z is not None:
        for xi, yi, zi in zip(x, y, z):
            if xi is not None and yi is not None and zi is not None:
                data.append((float(xi), float(yi), float(zi)))
    else:
        for xi, yi in zip(x, y):
            if xi is not None and yi is not None:
                data.append((float(xi), float(yi)))

    if len(data) < 5:
        result["message"] = "Insufficient data points (minimum 5 required for correlation)."
        return result

    arr = np.array(data)
    
    def _ols_residuals(a, b):
        slope, intercept, _, _, _ = stats.linregress(b, a)
        return a - (slope * b + intercept)

    if z is None:
        # Standard Correlation
        if method == "spearman":
            r, p = stats.spearmanr(arr[:, 0], arr[:, 1])
        else:
            r, p = stats.pearsonr(arr[:, 0], arr[:, 1])
    else:
        if method == "spearman":
            # Spearman partial: rank all three variables first, then partial-correlate
            # the ranks via OLS residuals. Applying OLS residuals to raw values and
            # then computing Spearman produces an uninterpretable hybrid.
            rx = stats.rankdata(arr[:, 0]).astype(float)
            ry = stats.rankdata(arr[:, 1]).astype(float)
            rz = stats.rankdata(arr[:, 2]).astype(float)
            res_x = _ols_residuals(rx, rz)
            res_y = _ols_residuals(ry, rz)
            r, p = stats.pearsonr(res_x, res_y)
        else:
            # Pearson partial: OLS residuals on raw values
            res_x = _ols_residuals(arr[:, 0], arr[:, 2])
            res_y = _ols_residuals(arr[:, 1], arr[:, 2])
            r, p = stats.pearsonr(res_x, res_y)

    result.update({
        "available": True,
        "r": round(float(r), 4),
        "p_value": round(float(p), 4),
        "significant": p < 0.05,
        "message": f"{'Partial ' if z is not None else ''}{method.capitalize()} Correlation: r={r:.3f}, p={p:.4f} ({'Significant' if p < 0.05 else 'Not significant'})."
    })
    
    return result

# ── Survival / Event Analysis ────────────────────────────────────────────────

def run_survival_analysis(durations: List[float], events: List[int]) -> Dict:
    """
    Compute Kaplan-Meier survival curve.
    durations: time until event or censoring.
    events: 1 if event occurred, 0 if censored.
    """
    result = {"available": False, "timeline": [], "message": ""}
    
    if not durations or len(durations) != len(events):
        result["message"] = "Invalid survival data."
        return result

    try:
        import numpy as np
    except ImportError:
        result["message"] = "numpy required for survival analysis."
        return result

    # Sort by duration
    data = sorted(zip(durations, events))
    unique_times = sorted(list(set([d for d, e in data])))

    survival_prob = 1.0
    n_at_risk = len(data)
    greenwood_sum = 0.0  # running Greenwood variance accumulator: sum d/(n*(n-d))
    timeline = [{"time": 0, "survival": 1.0, "ci_lower": 1.0, "ci_upper": 1.0, "at_risk": n_at_risk}]

    for t in unique_times:
        d_t = sum(1 for dur, ev in data if dur == t and ev == 1)
        c_t = sum(1 for dur, ev in data if dur == t and ev == 0)

        if n_at_risk > 0:
            survival_prob *= (1 - d_t / n_at_risk)

            # Greenwood's formula: accumulate d_t / (n * (n - d_t)) at each event time
            denom = n_at_risk * (n_at_risk - d_t)
            if d_t > 0 and denom > 0:
                greenwood_sum += d_t / denom

            # 95% CI via plain Greenwood: S(t) ± 1.96 * S(t) * sqrt(greenwood_sum)
            se = survival_prob * math.sqrt(greenwood_sum)
            ci_lo = round(max(0.0, survival_prob - 1.96 * se), 4)
            ci_hi = round(min(1.0, survival_prob + 1.96 * se), 4)

            n_at_risk -= (d_t + c_t)
            timeline.append({
                "time": float(t),
                "survival": round(float(survival_prob), 4),
                "ci_lower": ci_lo,
                "ci_upper": ci_hi,
                "at_risk": int(n_at_risk),
                "events": int(d_t),
            })

    result.update({
        "available": True,
        "timeline": timeline,
        "median_survival": next((t["time"] for t in timeline if t["survival"] <= 0.5), None),
    })
    return result


def run_logrank_test(durations_a: List[float], events_a: List[int], 
                     durations_b: List[float], events_b: List[int]) -> Dict:
    """
    Compare survival curves of two groups using the Log-Rank test.
    """
    result = {"available": False, "p_value": None, "significant": False, "message": ""}
    
    try:
        import numpy as np
        from scipy import stats
    except ImportError:
        result["message"] = "numpy/scipy required for Log-Rank test."
        return result

    # Aggregate all unique event times
    all_times = sorted(list(set(durations_a + durations_b)))

    obs_a, exp_a, var_a = 0, 0, 0
    for t in all_times:
        na = sum(1 for d in durations_a if d >= t)
        nb = sum(1 for d in durations_b if d >= t)
        da = sum(1 for d, e in zip(durations_a, events_a) if d == t and e == 1)
        db = sum(1 for d, e in zip(durations_b, events_b) if d == t and e == 1)
        nt, dt = na+nb, da+db
        if nt > 0:
            obs_a += da
            ea = dt * (na / nt)
            exp_a += ea
            if nt > 1:
                var_a += (dt * (na / nt) * (nb / nt) * (nt - dt) / (nt - 1))

    if var_a > 0:
        stat = ((obs_a - exp_a)**2) / var_a
        p_val = 1 - stats.chi2.cdf(stat, df=1)
        
        result.update({
            "available": True,
            "statistic": round(float(stat), 4),
            "p_value": round(float(p_val), 4),
            "significant": p_val < 0.05,
            "message": f"Log-Rank Test: p={p_val:.4f} ({'Significant' if p_val < 0.05 else 'Not significant'})."
        })
    else:
        result["message"] = "Insufficient event data for Log-Rank test."

    return result


def run_cox_ph(
    durations: List[float],
    events: List[int],
    X: List[List[float]],
    covariate_names: List[str],
) -> Dict:
    """
    Cox Proportional Hazards via Breslow partial likelihood (Newton-Raphson).
    Returns HR, 95% CI, p-values, C-index.
    """
    result: Dict[str, Any] = {"available": False, "covariates": [], "message": ""}

    try:
        from scipy import stats as sp_stats
    except ImportError:
        result["message"] = "scipy required for Cox PH model."
        return result

    dur = np.array(durations, dtype=float)
    ev = np.array(events, dtype=int)
    Xm = np.array(X, dtype=float)
    n, p = Xm.shape

    if n < p + 5:
        result["message"] = f"Too few subjects ({n}) for {p} covariates (need n ≥ p+5)."
        return result
    if int(ev.sum()) < 3:
        result["message"] = "Too few events for Cox model (need ≥3 deaths)."
        return result

    # Standardize covariates for numerical stability; HRs back-transformed later
    X_mean = Xm.mean(axis=0)
    X_std = Xm.std(axis=0)
    X_std[X_std == 0] = 1.0
    Xs = (Xm - X_mean) / X_std

    # Sort by time ascending
    order = np.argsort(dur)
    t_s = dur[order]
    e_s = ev[order]
    Xs_s = Xs[order]

    # Newton-Raphson on partial log-likelihood (Breslow for ties)
    beta = np.zeros(p)
    converged = False

    for _ in range(100):
        eta = Xs_s @ beta
        eta -= eta.max()  # centre for exp stability
        exp_eta = np.exp(eta)

        score = np.zeros(p)
        info = np.zeros((p, p))

        unique_event_times = np.unique(t_s[e_s == 1])
        for t_ev in unique_event_times:
            ev_mask = (t_s == t_ev) & (e_s == 1)
            risk_mask = t_s >= t_ev

            X_ev = Xs_s[ev_mask]
            X_risk = Xs_s[risk_mask]
            exp_risk = exp_eta[risk_mask]
            n_ev = int(ev_mask.sum())

            sum_exp = exp_risk.sum()
            if sum_exp == 0:
                continue
            w = exp_risk / sum_exp
            mu = (X_risk * w[:, None]).sum(axis=0)

            score += X_ev.sum(axis=0) - n_ev * mu
            sigma2 = (X_risk * w[:, None]).T @ X_risk - np.outer(mu, mu)
            info += n_ev * sigma2

        if np.linalg.matrix_rank(info) < p:
            break
        try:
            delta = np.linalg.solve(info, score)
        except np.linalg.LinAlgError:
            break

        beta_new = beta + delta
        if np.max(np.abs(delta)) < 1e-8:
            beta = beta_new
            converged = True
            break
        beta = beta_new

    # Guard: suppress all estimates if Newton-Raphson did not converge.
    # Returning invalid HRs with only a message-string warning is dangerous
    # in a clinical context — callers must receive available=False explicitly.
    if not converged:
        result["available"] = False
        result["message"] = (
            f"Cox PH model did not converge after 100 iterations "
            f"({n} patients, {int(ev.sum())} events, {p} covariates). "
            "Common causes: collinear covariates, complete separation, or too few "
            "events per variable. Results suppressed."
        )
        return result

    # Back-transform to original covariate scale
    beta_orig = beta / X_std

    # Numerically stable SE: solve(info, I) instead of explicit inv(info)
    try:
        var_cov_s = np.linalg.solve(info, np.eye(p))
        se_orig = np.sqrt(np.diag(var_cov_s)) / X_std
    except np.linalg.LinAlgError:
        se_orig = np.full(p, np.nan)

    z_scores = beta_orig / se_orig
    p_vals = 2 * (1 - sp_stats.norm.cdf(np.abs(z_scores)))
    hr = np.exp(beta_orig)
    hr_lo = np.exp(beta_orig - 1.96 * se_orig)
    hr_hi = np.exp(beta_orig + 1.96 * se_orig)

    # Harrell's C-index
    lp = Xm @ beta_orig
    pairs = concordant = 0.0
    for i in range(n):
        if ev[i] == 0:
            continue
        for j in range(n):
            if i == j or dur[j] < dur[i]:
                continue
            pairs += 1
            if lp[i] > lp[j]:
                concordant += 1
            elif lp[i] == lp[j]:
                concordant += 0.5
    c_index = concordant / pairs if pairs > 0 else 0.5

    # ── Schoenfeld residuals — proportional hazards assumption test ──────────
    # r_ki = x_ki − E[x_k | R(t_i)] for each event i and covariate k.
    # Grambsch & Therneau (1994): significant Spearman(r_k, log t) → PH violated.
    sr_list: List[np.ndarray] = []
    sr_times: List[float] = []
    eta_final = Xs_s @ beta
    eta_final -= eta_final.max()
    exp_eta_final = np.exp(eta_final)

    for i in range(len(t_s)):
        if e_s[i] != 1:
            continue
        risk_mask = t_s >= t_s[i]
        s = exp_eta_final[risk_mask].sum()
        if s == 0:
            continue
        w = exp_eta_final[risk_mask] / s
        mu_k = (Xs_s[risk_mask] * w[:, None]).sum(axis=0)
        sr_list.append(Xs_s[i] - mu_k)
        sr_times.append(float(t_s[i]))

    ph_tests: List[Dict] = []
    ph_violated_any = False
    if len(sr_list) >= 3:
        sr_arr = np.array(sr_list)
        log_t = np.log(np.array(sr_times) + 1e-9)
        for k in range(p):
            rho, p_ph = sp_stats.spearmanr(log_t, sr_arr[:, k])
            violated = bool(p_ph < 0.05)
            if violated:
                ph_violated_any = True
            ph_tests.append({
                "name": covariate_names[k],
                "rho": round(float(rho), 4),
                "p_value": round(float(p_ph), 4),
                "ph_violated": violated,
            })

    ph_warning = (
        "PH assumption may be violated for: "
        + ", ".join(t["name"] for t in ph_tests if t["ph_violated"])
        + ". Consider time-varying coefficients or stratification."
    ) if ph_violated_any else None

    cov_out = []
    for k in range(p):
        cov_out.append({
            "name": covariate_names[k],
            "coef": round(float(beta_orig[k]), 4),
            "hr": round(float(hr[k]), 3),
            "hr_lower": round(float(hr_lo[k]), 3),
            "hr_upper": round(float(hr_hi[k]), 3),
            "se": round(float(se_orig[k]), 4),
            "z": round(float(z_scores[k]), 3),
            "p_value": round(float(p_vals[k]), 4),
            "significant": bool(p_vals[k] < 0.05),
        })

    result.update({
        "available": True,
        "n": int(n),
        "n_events": int(ev.sum()),
        "covariates": cov_out,
        "c_index": round(float(c_index), 3),
        "converged": True,
        "ph_tests": ph_tests,
        "ph_warning": ph_warning,
        "message": (
            f"Cox PH model fitted on {n} patients, {int(ev.sum())} events. "
            f"C-index: {c_index:.3f}. Converged."
            + (f" {ph_warning}" if ph_warning else "")
        ),
    })
    return result


def run_bayesian_multilevel(
    y: List[float],
    X_fixed: List[List[float]],
    patient_ids: List[int],
    predictor_names: List[str],
    n_warmup: int = 500,
    n_samples: int = 1000,
) -> Dict:
    """
    Bayesian linear mixed model (random intercept) via Gibbs sampling.

    Model: y_ij = mu + alpha_j + X_ij @ beta + eps_ij
      alpha_j ~ N(0, sigma2_a)    [patient random intercept]
      eps_ij  ~ N(0, sigma2_e)    [observation noise]

    Priors:
      mu     ~ N(0, 1000)
      beta_k ~ N(0, 100)
      sigma2_a ~ InvGamma(1, 1)
      sigma2_e ~ InvGamma(1, 1)

    Returns posterior means, 95% credible intervals, ICC.
    """
    result: Dict[str, Any] = {"available": False, "fixed_effects": [], "message": ""}

    y_arr = np.array(y, dtype=float)
    X_arr = np.array(X_fixed, dtype=float)
    pids = np.array(patient_ids, dtype=int)

    N = len(y_arr)
    p = X_arr.shape[1] if X_arr.ndim == 2 else 0
    unique_pids = np.unique(pids)
    J = len(unique_pids)
    pid_map = {pid: idx for idx, pid in enumerate(unique_pids)}
    j_idx = np.array([pid_map[pid] for pid in pids])

    if N < 10:
        result["message"] = "Too few observations (need ≥10)."
        return result
    if J < 3:
        result["message"] = "Too few patients (need ≥3) for multilevel model."
        return result

    # Centre outcome and predictors for faster mixing
    y_mean = y_arr.mean()
    y_c = y_arr - y_mean

    # Pre-compute per-patient observation indices
    patient_obs = [np.where(j_idx == j)[0] for j in range(J)]
    nj = np.array([len(obs) for obs in patient_obs])

    # ── Initialise parameters ────────────────────────────────────────────────
    mu = 0.0
    beta = np.zeros(p)
    alpha = np.zeros(J)
    sigma2_e = 1.0
    sigma2_a = 1.0

    # Prior hyperparameters
    tau2_mu = 1000.0
    tau2_beta = 100.0
    a_e = b_e = a_a = b_a = 1.0  # InvGamma(1,1) priors

    # Storage
    mu_samps = np.empty(n_warmup + n_samples)
    beta_samps = np.empty((n_warmup + n_samples, p))
    sigma2_e_samps = np.empty(n_warmup + n_samples)
    sigma2_a_samps = np.empty(n_warmup + n_samples)
    alpha_samps = np.empty((n_warmup + n_samples, J))

    rng = np.random.default_rng(42)

    def _inv_gamma_sample(a_post, b_post):
        # InvGamma(a, b): sample via 1/Gamma(a, 1/b)
        return 1.0 / rng.gamma(shape=a_post, scale=1.0 / b_post)

    # ── Gibbs sampler ────────────────────────────────────────────────────────
    for it in range(n_warmup + n_samples):
        resid_no_mu = y_c - (X_arr @ beta if p > 0 else 0.0) - alpha[j_idx]

        # --- sample mu (global intercept, conjugate normal) ---
        prec_mu = 1.0 / tau2_mu + N / sigma2_e
        mean_mu = (resid_no_mu.sum() / sigma2_e) / prec_mu
        mu = rng.normal(mean_mu, np.sqrt(1.0 / prec_mu))

        # --- sample beta_k (fixed effects, conjugate normal per covariate) ---
        for k in range(p):
            resid_k = y_c - mu - alpha[j_idx] - (
                X_arr @ beta - X_arr[:, k] * beta[k]
            )
            prec_k = 1.0 / tau2_beta + np.sum(X_arr[:, k] ** 2) / sigma2_e
            mean_k = (np.dot(X_arr[:, k], resid_k) / sigma2_e) / prec_k
            beta[k] = rng.normal(mean_k, np.sqrt(1.0 / prec_k))

        # --- sample alpha_j (patient random intercepts, conjugate normal) ---
        resid_no_alpha2 = y_c - mu - (X_arr @ beta if p > 0 else 0.0)
        for j in range(J):
            obs_j = patient_obs[j]
            prec_j = 1.0 / sigma2_a + nj[j] / sigma2_e
            mean_j = resid_no_alpha2[obs_j].sum() / sigma2_e / prec_j
            alpha[j] = rng.normal(mean_j, np.sqrt(1.0 / prec_j))
        # Centre random effects to maintain identifiability with mu
        alpha -= alpha.mean()

        # --- sample sigma2_e (residual variance, InvGamma) ---
        full_resid = y_c - mu - alpha[j_idx] - (X_arr @ beta if p > 0 else 0.0)
        a_e_post = a_e + N / 2.0
        b_e_post = b_e + np.dot(full_resid, full_resid) / 2.0
        sigma2_e = _inv_gamma_sample(a_e_post, b_e_post)
        sigma2_e = max(sigma2_e, 1e-6)

        # --- sample sigma2_a (between-patient variance, InvGamma) ---
        a_a_post = a_a + J / 2.0
        b_a_post = b_a + np.dot(alpha, alpha) / 2.0
        sigma2_a = _inv_gamma_sample(a_a_post, b_a_post)
        sigma2_a = max(sigma2_a, 1e-6)

        # Store
        mu_samps[it] = mu
        beta_samps[it] = beta.copy()
        sigma2_e_samps[it] = sigma2_e
        sigma2_a_samps[it] = sigma2_a
        alpha_samps[it] = alpha.copy()

    # ── Post-warmup summaries ───────────────────────────────────────────────
    def _summarise(samps_1d):
        s = samps_1d[n_warmup:]
        mn = float(np.mean(s))
        sd = float(np.std(s))
        lo, hi = float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))
        # Effective sample size (lag-1 autocorrelation approximation)
        s_c = s - mn
        acf1 = float(np.corrcoef(s_c[:-1], s_c[1:])[0, 1]) if len(s) > 2 else 0.0
        ess = int(n_samples * (1 - acf1) / (1 + acf1)) if acf1 < 1.0 else 1
        return {"mean": round(mn, 4), "sd": round(sd, 4),
                "ci_lower": round(lo, 4), "ci_upper": round(hi, 4),
                "ess": max(ess, 1)}

    def _rhat(samps_1d):
        """Split-chain R-hat (Gelman-Rubin). Values < 1.1 indicate convergence."""
        s = samps_1d[n_warmup:]
        n = len(s)
        half = n // 2
        if half < 2:
            return float("nan")
        c1, c2 = s[:half].astype(float), s[half: half * 2].astype(float)
        w = float((c1.var(ddof=1) + c2.var(ddof=1)) / 2.0)
        b = half * float(np.array([c1.mean(), c2.mean()]).var(ddof=1))
        if w == 0:
            return float("nan")
        var_plus = ((half - 1) / half) * w + b / half
        return round(float(math.sqrt(var_plus / w)), 3)

    mu_summary = _summarise(mu_samps)
    beta_summaries = [_summarise(beta_samps[:, k]) for k in range(p)]

    sigma2_e_summ = _summarise(sigma2_e_samps)
    sigma2_a_summ = _summarise(sigma2_a_samps)

    # ── Convergence: split-chain R-hat for key parameters ──────────────────
    rhat_values = (
        [_rhat(mu_samps), _rhat(sigma2_e_samps), _rhat(sigma2_a_samps)]
        + [_rhat(beta_samps[:, k]) for k in range(p)]
    )
    finite_rhats = [v for v in rhat_values if not math.isnan(v)]
    max_rhat = round(max(finite_rhats), 3) if finite_rhats else float("nan")
    converged = max_rhat < 1.1 if finite_rhats else False
    convergence_info = {
        "max_rhat": max_rhat,
        "converged": converged,
        "warning": (
            None if converged
            else f"Convergence concern: max R-hat = {max_rhat:.3f} (threshold 1.1). "
                 "Consider increasing n_warmup or n_samples."
        ),
    }

    # ICC = sigma2_a / (sigma2_a + sigma2_e) sampled pointwise
    icc_samps = sigma2_a_samps[n_warmup:] / (
        sigma2_a_samps[n_warmup:] + sigma2_e_samps[n_warmup:]
    )
    icc_summary = {
        "mean": round(float(np.mean(icc_samps)), 3),
        "ci_lower": round(float(np.percentile(icc_samps, 2.5)), 3),
        "ci_upper": round(float(np.percentile(icc_samps, 97.5)), 3),
    }

    # Random effects posterior (per patient) — report sorted
    alpha_post_mean = alpha_samps[n_warmup:].mean(axis=0)
    alpha_post_lo = np.percentile(alpha_samps[n_warmup:], 2.5, axis=0)
    alpha_post_hi = np.percentile(alpha_samps[n_warmup:], 97.5, axis=0)

    random_effects = []
    for j in range(J):
        random_effects.append({
            "patient_id": int(unique_pids[j]),
            "mean": round(float(alpha_post_mean[j]), 4),
            "ci_lower": round(float(alpha_post_lo[j]), 4),
            "ci_upper": round(float(alpha_post_hi[j]), 4),
            "n_obs": int(nj[j]),
        })
    random_effects.sort(key=lambda x: x["mean"])

    fixed_effects = [{"name": "Intercept (global mean)", **mu_summary}]
    for k, name in enumerate(predictor_names):
        fixed_effects.append({"name": name, **beta_summaries[k]})

    result.update({
        "available": True,
        "n_obs": N,
        "n_patients": J,
        "n_predictors": p,
        "fixed_effects": fixed_effects,
        "sigma2_e": sigma2_e_summ,
        "sigma2_a": sigma2_a_summ,
        "icc": icc_summary,
        "random_effects": random_effects,
        "n_samples": n_samples,
        "n_warmup": n_warmup,
        "convergence": convergence_info,
        "message": (
            f"Bayesian MLM fitted: {N} observations, {J} patients, "
            f"{p} predictor(s). ICC={icc_summary['mean']:.3f} "
            f"[{icc_summary['ci_lower']:.3f}, {icc_summary['ci_upper']:.3f}]. "
            f"{n_samples} posterior samples (after {n_warmup} warmup). "
            f"Max R-hat={max_rhat:.3f} ({'OK' if converged else 'WARN: not converged'})."
        ),
    })
    return result
