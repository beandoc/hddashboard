"""
ml_idh.py
=========
Intradialytic Hypotension (IDH) Prediction Model.

Computes a pre-session probability that the upcoming hemodialysis session will
be complicated by IDH, defined as:
    (A) Hybrid label — where BP data is available: SBP drop ≥ 20 mmHg
        (bp_pre_sys → bp_nadir_sys) OR nadir SBP < 90 mmHg.
    (B) Fallback: existing idh_episode boolean when nadir BP is not recorded.

Features (26):
    Patient/comorbidity (9): age, dm, chf, cad, pvd, af, liver_disease, lvef,
                              diastolic_dysfunction_grade
    Labs (2):                 albumin, antihypertensive_count
    Session plan (6):         pre_hd_sbp, idwg_kg, uf_volume_ml,
                              uf_rate_ml_kg_h, dialysate_temp, dialysate_sodium
    Session context (3):      uf_achievement_ratio, antihypertensive_prehd,
                              intradialytic_meals
    Temporal/prior (6):       prior_idh_count_7sess, prior_idh_rate_7sess,
                              prior_nadir_sbp_mean, pre_hd_sbp_slope_7sess,
                              albumin_slope_3mo, uf_rate_albumin_ratio

Model: XGBoost primary → Calibrated LogisticRegression fallback → heuristic.
"""

import hashlib
import json
import logging
import math
import os
import warnings
from datetime import date, timedelta
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Optional imports ──────────────────────────────────────────────────────────

try:
    import joblib
    _JOBLIB_AVAILABLE = True
except ImportError:
    _JOBLIB_AVAILABLE = False

try:
    from mapie.classification import MapieClassifier
    _MAPIE_AVAILABLE = True
except ImportError:
    _MAPIE_AVAILABLE = False

try:
    import xgboost as xgb
    _XGB_AVAILABLE = True
except ImportError:
    _XGB_AVAILABLE = False


def _get_drt_mins(sr) -> Optional[float]:
    if not sr:
        return None
    mapping = {
        "<1 hour": 30.0,
        "1-2 hours": 90.0,
        "2-6 hours": 240.0,
        "6-12 hours": 540.0,
        ">12 hours": 720.0,
        "Whole day": 1440.0,
        "Never fully recover before next dialysis": 2880.0,
    }
    if isinstance(sr, dict):
        drt = sr.get("dialysis_recovery_time")
        if drt and drt in mapping:
            return mapping[drt]
        try:
            val = sr.get("dialysis_recovery_time_mins")
            if val is not None:
                return float(val)
        except (ValueError, TypeError):
            pass
        return None
        
    drt = getattr(sr, "dialysis_recovery_time", None)
    if drt and drt in mapping:
        return mapping[drt]
    try:
        val = getattr(sr, "dialysis_recovery_time_mins", None)
        if val is not None:
            return float(val)
    except (ValueError, AttributeError, TypeError):
        pass
    return None


try:
    from sklearn.linear_model import LogisticRegression
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.impute import SimpleImputer
    from sklearn.model_selection import cross_val_predict, StratifiedKFold
    from sklearn.metrics import roc_auc_score
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

try:
    import shap as _shap
    _SHAP_AVAILABLE = True
except ImportError:
    _SHAP_AVAILABLE = False

# ── Feature schema — MUST stay in sync between training and inference ─────────

IDH_FEATURE_NAMES = [
    # Patient / comorbidities
    "age",                        # 0  — continuous
    "dm",                         # 1  — binary (any DM)
    "chf",                        # 2  — binary
    "cad",                        # 3  — binary
    "pvd",                        # 4  — binary (peripheral vascular disease)
    "af",                         # 5  — binary (atrial fibrillation)
    "liver_disease",              # 6  — binary (any liver disease present)
    "lvef",                       # 7  — continuous (%)
    "diastolic_dysfunction_grade",# 8  — ordinal 0-3
    # Labs (most recent monthly record)
    "albumin",                    # 9  — continuous g/dL
    "antihypertensive_count",     # 10 — ordinal
    # Session plan / prescription
    "pre_hd_sbp",                 # 11 — continuous mmHg
    "idwg_kg",                    # 12 — continuous kg (weight_pre − prev weight_post)
    "uf_volume_ml",               # 13 — continuous mL
    "uf_rate_ml_kg_h",            # 14 — continuous mL/kg/h (engineered)
    "dialysate_temp",             # 15 — continuous °C
    "dialysate_sodium",           # 16 — continuous mEq/L
    # Session context
    "uf_achievement_ratio",       # 17 — actual_uf / planned_uf (previous session)
    "antihypertensive_prehd",     # 18 — binary (took BP meds morning of session)
    "intradialytic_meals",        # 19 — binary
    # Temporal / prior-session trends (last 7 sessions)
    "prior_idh_count_7sess",      # 20 — count
    "prior_idh_rate_7sess",       # 21 — proportion 0–1
    "prior_nadir_sbp_mean",       # 22 — mean nadir SBP over last 7 sessions
    "pre_hd_sbp_slope_7sess",     # 23 — slope of pre_hd_sbp trend (mmHg/session)
    "albumin_slope_3mo",          # 24 — slope of monthly albumin trend (g/dL/month)
    "uf_rate_albumin_ratio",      # 25 — engineered: uf_rate / albumin
    
    # ── 15 New Clinical Feature Additions ──
    "hd_frequency",                 # 26 — continuous/integer
    "dialysis_vintage",             # 27 — continuous (days)
    "hb",                           # 28 — continuous g/dL
    "calcium",                      # 29 — continuous mg/dL
    "phosphorus",                   # 30 — continuous mg/dL
    "prev_muscle_cramps",           # 31 — binary
    "prev_nausea_vomiting",         # 32 — binary
    "prev_giddiness",               # 33 — binary
    "prev_recovery_time",           # 34 — continuous (mins)
    "prev_blood_flow_rate",         # 35 — continuous (mL/min)
    "prev_arterial_pressure",       # 36 — continuous (mmHg)
    "prev_venous_pressure",         # 37 — continuous (mmHg)
    "heart_rate_variation",         # 38 — continuous (placeholder)
    "prior_dialysate_temp_mean",    # 39 — continuous (°C)
    "prior_dialysate_sodium_mean",  # 40 — continuous (mEq/L)
]

# ── Model paths ───────────────────────────────────────────────────────────────

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_IDH_MODEL_PATH  = os.path.join(_BASE_DIR, "idh_model.joblib")
_IDH_MAPIE_PATH  = os.path.join(_BASE_DIR, "idh_mapie.joblib")
_IDH_META_PATH   = os.path.join(_BASE_DIR, "idh_model_meta.json")

# EPF thresholds
_N_FEATURES = len(IDH_FEATURE_NAMES)   # 41
_EPF_MIN    = 5
_EPF_WARN   = 10
_MIN_EVENTS = _N_FEATURES * _EPF_MIN   # 205

# Risk thresholds
_THRESHOLD_HIGH      = 0.60
_THRESHOLD_MODERATE  = 0.40
_THRESHOLD_LOW       = 0.20


# ── Diastolic dysfunction grade parser ───────────────────────────────────────

def _parse_dd_grade(value: Optional[str]) -> float:
    """Convert free-text diastolic dysfunction grade to ordinal 0–3."""
    if not value:
        return 0.0
    v = str(value).lower().strip()
    if "grade 3" in v or "severe" in v or "grade iii" in v:
        return 3.0
    if "grade 2" in v or "moderate" in v or "grade ii" in v:
        return 2.0
    if "grade 1" in v or "mild" in v or "grade i" in v:
        return 1.0
    if "normal" in v or "none" in v:
        return 0.0
    return 0.0


def _liver_disease_binary(value: Optional[str]) -> float:
    """1.0 if any liver disease documented, else 0.0."""
    if not value:
        return 0.0
    v = str(value).lower()
    if v in ("none", "no", "nil", "normal", "", "0"):
        return 0.0
    return 1.0


# ── Linear trend slope helper ─────────────────────────────────────────────────

def _slope(values: List[float]) -> float:
    """Ordinary-least-squares slope for a 1-D sequence. Returns 0 if < 2 pts."""
    clean = [v for v in values if v is not None and not math.isnan(v)]
    if len(clean) < 2:
        return 0.0
    n = len(clean)
    x = list(range(n))
    xm = sum(x) / n
    ym = sum(clean) / n
    num = sum((xi - xm) * (yi - ym) for xi, yi in zip(x, clean))
    den = sum((xi - xm) ** 2 for xi in x)
    return num / den if den != 0 else 0.0


def _month_to_int(month_str: Optional[str]) -> Optional[int]:
    if not month_str:
        return None
    try:
        parts = str(month_str).split("-")
        return int(parts[0]) * 12 + int(parts[1])
    except Exception:
        return None


def _slope_with_x(points: List[tuple[float, float]]) -> float:
    """Ordinary-least-squares slope for a 2-D sequence of (x, y) coordinates."""
    clean = [(x, y) for x, y in points if y is not None and not math.isnan(y)]
    if len(clean) < 2:
        return 0.0
    n = len(clean)
    xm = sum(p[0] for p in clean) / n
    ym = sum(p[1] for p in clean) / n
    num = sum((p[0] - xm) * (p[1] - ym) for p in clean)
    den = sum((p[0] - xm) ** 2 for p in clean)
    return num / den if den != 0 else 0.0


# ── IDH label logic ───────────────────────────────────────────────────────────

def _compute_idh_label(session) -> int:
    """
    Hybrid label (Plan Q1 option C):
      1. If bp_pre_sys AND bp_nadir_sys are both present:
         IDH = SBP drop ≥ 20 mmHg OR nadir SBP < 90 mmHg
      2. Else: fall back to idh_episode boolean.
    Returns 1 (IDH occurred) or 0.
    """
    pre  = session.bp_pre_sys
    nadir = session.bp_nadir_sys
    if pre is not None and nadir is not None:
        drop = pre - nadir
        return int(drop >= 20.0 or nadir < 90.0)
    # fallback
    return int(bool(session.idh_episode))


# ── Feature vector constructor ────────────────────────────────────────────────

def _build_idh_feature_vector(
    age:                        float,
    dm:                         float,
    chf:                        float,
    cad:                        float,
    pvd:                        float,
    af:                         float,
    liver_disease:              float,
    lvef:                       float,
    diastolic_dysfunction_grade: float,
    albumin:                    float,
    antihypertensive_count:     float,
    pre_hd_sbp:                 float,
    idwg_kg:                    float,
    uf_volume_ml:               float,
    uf_rate_ml_kg_h:            float,
    dialysate_temp:             float,
    dialysate_sodium:           float,
    uf_achievement_ratio:       float,
    antihypertensive_prehd:     float,
    intradialytic_meals:        float,
    prior_idh_count_7sess:      float,
    prior_idh_rate_7sess:       float,
    prior_nadir_sbp_mean:       float,
    pre_hd_sbp_slope_7sess:     float,
    albumin_slope_3mo:          float,
    uf_rate_albumin_ratio:      float,
    hd_frequency:               float = None,
    dialysis_vintage:           float = None,
    hb:                         float = None,
    calcium:                    float = None,
    phosphorus:                 float = None,
    prev_muscle_cramps:         float = None,
    prev_nausea_vomiting:       float = None,
    prev_giddiness:             float = None,
    prev_recovery_time:         float = None,
    prev_blood_flow_rate:       float = None,
    prev_arterial_pressure:     float = None,
    prev_venous_pressure:       float = None,
    heart_rate_variation:       float = None,
    prior_dialysate_temp_mean:  float = None,
    prior_dialysate_sodium_mean:float = None,
    is_training: bool = False,
) -> list:
    """Unified feature vector — identical ordering for training and inference."""
    if not is_training:
        # Inference-time imputation with clinically-safe defaults
        age                         = age if age is not None else 60.0
        albumin                     = albumin if albumin is not None else 3.5
        lvef                        = lvef if lvef is not None else 60.0
        pre_hd_sbp                  = pre_hd_sbp if pre_hd_sbp is not None else 140.0
        dialysate_temp              = dialysate_temp if dialysate_temp is not None else 37.0
        dialysate_sodium            = dialysate_sodium if dialysate_sodium is not None else 138.0
        prior_nadir_sbp_mean        = prior_nadir_sbp_mean if prior_nadir_sbp_mean is not None else 110.0
        antihypertensive_count      = antihypertensive_count if antihypertensive_count is not None else 0.0
        idwg_kg                     = idwg_kg if idwg_kg is not None else 2.0
        uf_volume_ml                = uf_volume_ml if uf_volume_ml is not None else 2000.0
        uf_rate_ml_kg_h             = uf_rate_ml_kg_h if uf_rate_ml_kg_h is not None else 8.0
        uf_achievement_ratio        = uf_achievement_ratio if uf_achievement_ratio is not None else 1.0
        diastolic_dysfunction_grade = diastolic_dysfunction_grade if diastolic_dysfunction_grade is not None else 0.0

    alb_safe = max(albumin or 0.1, 0.1)
    uf_rate_albumin_ratio = (uf_rate_ml_kg_h or 0.0) / alb_safe

    return [
        float(age or 60),
        float(dm or 0),
        float(chf or 0),
        float(cad or 0),
        float(pvd or 0),
        float(af or 0),
        float(liver_disease or 0),
        float(lvef if lvef is not None else 60.0),
        float(diastolic_dysfunction_grade or 0),
        float(albumin if albumin is not None else 3.5),
        float(antihypertensive_count or 0),
        float(pre_hd_sbp if pre_hd_sbp is not None else 140.0),
        float(idwg_kg if idwg_kg is not None else 2.0),
        float(uf_volume_ml if uf_volume_ml is not None else 2000.0),
        float(uf_rate_ml_kg_h if uf_rate_ml_kg_h is not None else 8.0),
        float(dialysate_temp if dialysate_temp is not None else 37.0),
        float(dialysate_sodium if dialysate_sodium is not None else 138.0),
        float(uf_achievement_ratio if uf_achievement_ratio is not None else 1.0),
        float(antihypertensive_prehd or 0),
        float(intradialytic_meals or 0),
        float(prior_idh_count_7sess or 0),
        float(prior_idh_rate_7sess or 0),
        float(prior_nadir_sbp_mean if prior_nadir_sbp_mean is not None else 110.0),
        float(pre_hd_sbp_slope_7sess or 0),
        float(albumin_slope_3mo or 0),
        float(uf_rate_albumin_ratio),
        
        # 15 new clinical features
        float(hd_frequency) if hd_frequency is not None else None,
        float(dialysis_vintage) if dialysis_vintage is not None else None,
        float(hb) if hb is not None else None,
        float(calcium) if calcium is not None else None,
        float(phosphorus) if phosphorus is not None else None,
        float(prev_muscle_cramps) if prev_muscle_cramps is not None else None,
        float(prev_nausea_vomiting) if prev_nausea_vomiting is not None else None,
        float(prev_giddiness) if prev_giddiness is not None else None,
        float(prev_recovery_time) if prev_recovery_time is not None else None,
        float(prev_blood_flow_rate) if prev_blood_flow_rate is not None else None,
        float(prev_arterial_pressure) if prev_arterial_pressure is not None else None,
        float(prev_venous_pressure) if prev_venous_pressure is not None else None,
        float(heart_rate_variation) if heart_rate_variation is not None else None,
        float(prior_dialysate_temp_mean) if prior_dialysate_temp_mean is not None else None,
        float(prior_dialysate_sodium_mean) if prior_dialysate_sodium_mean is not None else None,
    ]


# ── Training path — ORM-based feature extraction ─────────────────────────────

def _extract_idh_features_for_training(
    session,
    patient,
    past_sessions: list,
    monthly_record=None,
    monthly_records_3mo: list = None,
) -> list:
    """
    Extract the 41-feature vector from ORM objects for model training.
    'past_sessions' = sessions BEFORE the current session, sorted desc.
    'monthly_record' = MonthlyRecord for the session's month.
    'monthly_records_3mo' = up to 3 most recent MonthlyRecords (for albumin slope).
    """
    p = patient

    # ── Patient static features ───────────────────────────────────────────────
    age   = float(p.age or 60)
    dm    = 0.0 if not p.dm_status or str(p.dm_status).strip().lower() in ("", "none", "no", "0", "false", "n") else 1.0
    chf   = float(p.chf_status or 0)
    cad   = float(p.cad_status or 0)
    pvd   = float(p.history_of_pvd or 0)
    af    = float(p.af_status or 0)
    liver = _liver_disease_binary(p.liver_disease)
    lvef  = float(p.ejection_fraction or 60.0)
    dd    = _parse_dd_grade(p.diastolic_dysfunction)

    # ── Monthly lab features ──────────────────────────────────────────────────
    albumin          = monthly_record.albumin if monthly_record else None
    antihyp_count    = float(monthly_record.antihypertensive_count or 0) if monthly_record else 0.0

    # ── Session prescription features ─────────────────────────────────────────
    pre_sbp = session.bp_pre_sys

    # IDWG = weight_pre this session − weight_post of previous session
    idwg_kg = None
    if past_sessions and past_sessions[0].weight_post is not None and session.weight_pre is not None:
        idwg_kg = max(0.0, session.weight_pre - past_sessions[0].weight_post)

    uf_vol  = session.uf_volume
    hours   = (session.duration_hours or 4) + (session.duration_minutes or 0) / 60.0
    actual_wt = session.weight_pre or p.dry_weight or 70.0
    uf_rate = (uf_vol / actual_wt / hours) if (uf_vol and hours > 0) else None
    dt      = session.dialysate_temperature
    ds      = session.dialysate_sodium
    antihyp_prehd = float(session.antihypertensive_taken_prehd or 0)
    meals   = float(session.intradialytic_meals_eaten or 0)

    # UF achievement ratio from previous session (as a proxy for tolerance)
    uf_achiev = 1.0
    if past_sessions:
        prev = past_sessions[0]
        if prev.uf_volume and prev.actual_uf_volume:
            uf_achiev = prev.actual_uf_volume / prev.uf_volume

    # ── Temporal features from past 7 sessions ───────────────────────────────
    last7 = past_sessions[:7]
    idh_flags = [_compute_idh_label(s) for s in last7]
    prior_idh_count = float(sum(idh_flags))
    prior_idh_rate  = prior_idh_count / len(last7) if last7 else 0.0

    nadir_sbps = [s.bp_nadir_sys for s in last7 if s.bp_nadir_sys is not None]
    nadir_mean = float(np.mean(nadir_sbps)) if nadir_sbps else None

    pre_sbps = [s.bp_pre_sys for s in last7 if s.bp_pre_sys is not None]
    sbp_slope = _slope(list(reversed(pre_sbps)))  # oldest first

    # ── Albumin 3-month slope ─────────────────────────────────────────────────
    alb_slope = 0.0
    if monthly_records_3mo and len(monthly_records_3mo) >= 2:
        points = []
        for r in monthly_records_3mo:
            m_val = _month_to_int(getattr(r, "record_month", None))
            a_val = getattr(r, "albumin", None)
            if m_val is not None and a_val is not None:
                points.append((m_val, float(a_val)))
        alb_slope = _slope_with_x(points)

    # ── 15 New Clinical Features (Training / ORM) ─────────────────────────────
    hd_frequency = float(p.hd_frequency) if p.hd_frequency is not None else None
    
    dialysis_vintage = None
    if session.session_date and p.hd_wef_date:
        dialysis_vintage = float((session.session_date - p.hd_wef_date).days)
        
    hb = monthly_record.hb if monthly_record else None
    calcium = monthly_record.calcium if monthly_record else None
    phosphorus = monthly_record.phosphorus if monthly_record else None

    prev_muscle_cramps = None
    prev_nausea_vomiting = None
    prev_giddiness = None
    prev_recovery_time = None
    prev_blood_flow_rate = None
    prev_arterial_pressure = None
    prev_venous_pressure = None

    if past_sessions:
        prev = past_sessions[0]
        prev_muscle_cramps = 1.0 if prev.muscle_cramps else 0.0
        prev_nausea_vomiting = 1.0 if prev.nausea_vomiting else 0.0
        
        sr = prev.symptom_report
        if sr:
            if sr.symptoms:
                prev_giddiness = 1.0 if "dizziness" in str(sr.symptoms).lower() else 0.0
            else:
                prev_giddiness = 0.0
            drt_mins = _get_drt_mins(sr)
            if drt_mins is not None:
                prev_recovery_time = float(drt_mins)
        else:
            prev_giddiness = 0.0
            prev_recovery_time = None
        
        # Scan back for the actual values entered by the user
        for s in past_sessions:
            bfr_val = s.actual_blood_flow_rate if s.actual_blood_flow_rate is not None else s.blood_flow_rate
            if bfr_val is not None:
                prev_blood_flow_rate = float(bfr_val)
                break
        
        for s in past_sessions:
            if s.arterial_line_pressure is not None:
                prev_arterial_pressure = float(s.arterial_line_pressure)
                break
                
        for s in past_sessions:
            if s.venous_line_pressure is not None:
                prev_venous_pressure = float(s.venous_line_pressure)
                break

    heart_rate_variation = None

    prior_temp_vals = [s.dialysate_temperature for s in last7 if s.dialysate_temperature is not None]
    prior_dialysate_temp_mean = float(np.mean(prior_temp_vals)) if prior_temp_vals else None

    prior_sod_vals = [s.dialysate_sodium for s in last7 if s.dialysate_sodium is not None]
    prior_dialysate_sodium_mean = float(np.mean(prior_sod_vals)) if prior_sod_vals else None

    return _build_idh_feature_vector(
        age=age, dm=dm, chf=chf, cad=cad, pvd=pvd, af=af,
        liver_disease=liver, lvef=lvef, diastolic_dysfunction_grade=dd,
        albumin=albumin, antihypertensive_count=antihyp_count,
        pre_hd_sbp=pre_sbp, idwg_kg=idwg_kg, uf_volume_ml=uf_vol,
        uf_rate_ml_kg_h=uf_rate, dialysate_temp=dt, dialysate_sodium=ds,
        uf_achievement_ratio=uf_achiev,
        antihypertensive_prehd=antihyp_prehd,
        intradialytic_meals=meals,
        prior_idh_count_7sess=prior_idh_count,
        prior_idh_rate_7sess=prior_idh_rate,
        prior_nadir_sbp_mean=nadir_mean,
        pre_hd_sbp_slope_7sess=sbp_slope,
        albumin_slope_3mo=alb_slope,
        uf_rate_albumin_ratio=0.0,  # recomputed inside _build_idh_feature_vector
        hd_frequency=hd_frequency,
        dialysis_vintage=dialysis_vintage,
        hb=hb,
        calcium=calcium,
        phosphorus=phosphorus,
        prev_muscle_cramps=prev_muscle_cramps,
        prev_nausea_vomiting=prev_nausea_vomiting,
        prev_giddiness=prev_giddiness,
        prev_recovery_time=prev_recovery_time,
        prev_blood_flow_rate=prev_blood_flow_rate,
        prev_arterial_pressure=prev_arterial_pressure,
        prev_venous_pressure=prev_venous_pressure,
        heart_rate_variation=heart_rate_variation,
        prior_dialysate_temp_mean=prior_dialysate_temp_mean,
        prior_dialysate_sodium_mean=prior_dialysate_sodium_mean,
        is_training=True,
    )


# ── Inference path — dict-based feature extraction ───────────────────────────

def _extract_idh_features_for_inference(
    session_plan: dict,
    patient_info: dict,
    past_sessions_list: list,
    monthly_data: dict = None,
    monthly_records_3mo: list = None,
) -> list:
    """
    Extract features for real-time pre-session inference.

    session_plan keys (all optional — will be imputed):
        pre_hd_sbp, uf_volume, duration_hours, duration_minutes,
        dialysate_temp, dialysate_sodium, antihypertensive_prehd,
        intradialytic_meals_planned, weight_pre, session_date

    patient_info keys:
        id, age, dm_status, chf_status, cad_status, history_of_pvd,
        af_status, liver_disease, ejection_fraction, diastolic_dysfunction,
        dry_weight, hd_frequency, hd_wef_date

    past_sessions_list: list of dicts or ORM objects with keys from SessionRecord
    monthly_data: dict with albumin, antihypertensive_count, hb, calcium, phosphorus
    """
    sp  = session_plan or {}
    pi  = patient_info or {}
    md  = monthly_data or {}
    mr3 = monthly_records_3mo or []

    # ── Patient features ──────────────────────────────────────────────────────
    age   = float(pi.get("age") or 60)
    dm    = 0.0 if not pi.get("dm_status") or str(pi.get("dm_status")).strip().lower() in ("", "none", "no", "0", "false", "n") else 1.0
    chf   = float(pi.get("chf_status") or 0)
    cad   = float(pi.get("cad_status") or 0)
    pvd   = float(pi.get("history_of_pvd") or 0)
    af    = float(pi.get("af_status") or 0)
    liver = _liver_disease_binary(pi.get("liver_disease"))
    lvef  = float(pi.get("ejection_fraction") or 60.0)
    dd    = _parse_dd_grade(pi.get("diastolic_dysfunction"))

    # ── Monthly labs ──────────────────────────────────────────────────────────
    albumin       = md.get("albumin")
    antihyp_count = float(md.get("antihypertensive_count") or 0)

    # ── Session plan ──────────────────────────────────────────────────────────
    pre_sbp = sp.get("pre_hd_sbp")
    uf_vol  = sp.get("uf_volume")
    hours   = (sp.get("duration_hours") or 4) + (sp.get("duration_minutes") or 0) / 60.0
    weight_pre = sp.get("weight_pre")
    actual_wt = float(weight_pre) if weight_pre is not None else float(pi.get("dry_weight") or 70.0)
    uf_rate = (uf_vol / actual_wt / hours) if (uf_vol and hours > 0) else None
    dt      = sp.get("dialysate_temp")
    ds      = sp.get("dialysate_sodium")
    antihyp_prehd = float(sp.get("antihypertensive_prehd") or 0)
    meals   = float(sp.get("intradialytic_meals_planned") or 0)

    # IDWG
    idwg_kg = None
    weight_pre = sp.get("weight_pre")
    if past_sessions_list:
        prev_wt_post = past_sessions_list[0].get("weight_post") if isinstance(past_sessions_list[0], dict) else getattr(past_sessions_list[0], "weight_post", None)
        if prev_wt_post is not None and weight_pre is not None:
            idwg_kg = max(0.0, float(weight_pre) - float(prev_wt_post))

    # UF achievement ratio from previous session
    uf_achiev = 1.0
    if past_sessions_list:
        prev = past_sessions_list[0]
        if isinstance(prev, dict):
            prev_uf_vol    = prev.get("uf_volume")
            prev_actual_uf = prev.get("actual_uf_volume")
        else:
            prev_uf_vol    = getattr(prev, "uf_volume", None)
            prev_actual_uf = getattr(prev, "actual_uf_volume", None)
        if prev_uf_vol and prev_actual_uf:
            uf_achiev = float(prev_actual_uf) / float(prev_uf_vol)

    # ── Temporal features ─────────────────────────────────────────────────────
    def _get(s, attr):
        return s.get(attr) if isinstance(s, dict) else getattr(s, attr, None)

    last7 = past_sessions_list[:7]
    idh_flags = []
    for s in last7:
        pre_s  = _get(s, "bp_pre_sys")
        nad_s  = _get(s, "bp_nadir_sys")
        idh_ep = _get(s, "idh_episode")
        if pre_s is not None and nad_s is not None:
            idh_flags.append(int((pre_s - nad_s) >= 20 or nad_s < 90))
        else:
            idh_flags.append(int(bool(idh_ep)))

    prior_idh_count = float(sum(idh_flags))
    prior_idh_rate  = prior_idh_count / len(last7) if last7 else 0.0

    nadir_sbps = [_get(s, "bp_nadir_sys") for s in last7 if _get(s, "bp_nadir_sys") is not None]
    nadir_mean = float(np.mean(nadir_sbps)) if nadir_sbps else None

    pre_sbps_hist = [_get(s, "bp_pre_sys") for s in last7 if _get(s, "bp_pre_sys") is not None]
    sbp_slope = _slope(list(reversed(pre_sbps_hist)))

    alb_slope = 0.0
    if mr3 and len(mr3) >= 2:
        points = []
        for r in mr3:
            m_val = _month_to_int(_get(r, "record_month"))
            a_val = _get(r, "albumin")
            if m_val is not None and a_val is not None:
                points.append((m_val, float(a_val)))
        alb_slope = _slope_with_x(points)

    # ── 15 New Clinical Features (Inference / Dict) ───────────────────────────
    hd_frequency = pi.get("hd_frequency")
    if hd_frequency is not None:
        hd_frequency = float(hd_frequency)

    dialysis_vintage = None
    session_date = sp.get("session_date")
    hd_wef_date = pi.get("hd_wef_date")
    if session_date and hd_wef_date:
        from datetime import date, datetime
        def _to_date(d):
            if not d:
                return None
            if isinstance(d, date):
                return d
            if isinstance(d, datetime):
                return d.date()
            if isinstance(d, str):
                try:
                    return datetime.strptime(d[:10], "%Y-%m-%d").date()
                except ValueError:
                    return None
            return None
        
        sd_date = _to_date(session_date)
        wef_date = _to_date(hd_wef_date)
        if sd_date and wef_date:
            dialysis_vintage = float((sd_date - wef_date).days)

    hb = md.get("hb")
    if hb is not None:
        hb = float(hb)

    calcium = md.get("calcium")
    if calcium is not None:
        calcium = float(calcium)

    phosphorus = md.get("phosphorus")
    if phosphorus is not None:
        phosphorus = float(phosphorus)

    prev_muscle_cramps = None
    prev_nausea_vomiting = None
    prev_giddiness = None
    prev_recovery_time = None
    prev_blood_flow_rate = None
    prev_arterial_pressure = None
    prev_venous_pressure = None

    if past_sessions_list:
        prev = past_sessions_list[0]
        cramps_val = _get(prev, "muscle_cramps")
        prev_muscle_cramps = 1.0 if cramps_val else (0.0 if cramps_val is not None else None)
        
        nv_val = _get(prev, "nausea_vomiting")
        prev_nausea_vomiting = 1.0 if nv_val else (0.0 if nv_val is not None else None)

        # Handle symptom report
        symptoms_val = None
        recovery_time_val = None
        if isinstance(prev, dict):
            sr = prev.get("symptom_report")
            if isinstance(sr, dict):
                symptoms_val = sr.get("symptoms")
                recovery_time_val = _get_drt_mins(sr)
            else:
                symptoms_val = prev.get("symptoms")
                recovery_time_val = _get_drt_mins(prev)
        else:
            sr = getattr(prev, "symptom_report", None)
            if sr:
                symptoms_val = getattr(sr, "symptoms", None)
                recovery_time_val = _get_drt_mins(sr)

        if symptoms_val is not None:
            prev_giddiness = 1.0 if "dizziness" in str(symptoms_val).lower() else 0.0
        if recovery_time_val is not None:
            prev_recovery_time = float(recovery_time_val)

        prev_bfr = None
        for s in past_sessions_list:
            bfr_val = _get(s, "actual_blood_flow_rate")
            if bfr_val is None:
                bfr_val = _get(s, "blood_flow_rate")
            if bfr_val is not None:
                prev_bfr = float(bfr_val)
                break
        if prev_bfr is not None:
            prev_blood_flow_rate = prev_bfr

        prev_ap = None
        for s in past_sessions_list:
            ap_val = _get(s, "arterial_line_pressure")
            if ap_val is not None:
                prev_ap = float(ap_val)
                break
        if prev_ap is not None:
            prev_arterial_pressure = prev_ap

        prev_vp = None
        for s in past_sessions_list:
            vp_val = _get(s, "venous_line_pressure")
            if vp_val is not None:
                prev_vp = float(vp_val)
                break
        if prev_vp is not None:
            prev_venous_pressure = prev_vp

    heart_rate_variation = None

    def _get_temp(s):
        val = _get(s, "dialysate_temperature")
        if val is None:
            val = _get(s, "dialysate_temp")
        return val

    temps = [_get_temp(s) for s in last7 if _get_temp(s) is not None]
    prior_dialysate_temp_mean = float(np.mean(temps)) if temps else None

    sods = [_get(s, "dialysate_sodium") for s in last7 if _get(s, "dialysate_sodium") is not None]
    prior_dialysate_sodium_mean = float(np.mean(sods)) if sods else None

    return _build_idh_feature_vector(
        age=age, dm=dm, chf=chf, cad=cad, pvd=pvd, af=af,
        liver_disease=liver, lvef=lvef, diastolic_dysfunction_grade=dd,
        albumin=albumin, antihypertensive_count=antihyp_count,
        pre_hd_sbp=pre_sbp, idwg_kg=idwg_kg, uf_volume_ml=uf_vol,
        uf_rate_ml_kg_h=uf_rate, dialysate_temp=dt, dialysate_sodium=ds,
        uf_achievement_ratio=uf_achiev,
        antihypertensive_prehd=antihyp_prehd,
        intradialytic_meals=meals,
        prior_idh_count_7sess=prior_idh_count,
        prior_idh_rate_7sess=prior_idh_rate,
        prior_nadir_sbp_mean=nadir_mean,
        pre_hd_sbp_slope_7sess=sbp_slope,
        albumin_slope_3mo=alb_slope,
        uf_rate_albumin_ratio=0.0,  # recomputed inside _build_idh_feature_vector
        hd_frequency=hd_frequency,
        dialysis_vintage=dialysis_vintage,
        hb=hb,
        calcium=calcium,
        phosphorus=phosphorus,
        prev_muscle_cramps=prev_muscle_cramps,
        prev_nausea_vomiting=prev_nausea_vomiting,
        prev_giddiness=prev_giddiness,
        prev_recovery_time=prev_recovery_time,
        prev_blood_flow_rate=prev_blood_flow_rate,
        prev_arterial_pressure=prev_arterial_pressure,
        prev_venous_pressure=prev_venous_pressure,
        heart_rate_variation=heart_rate_variation,
        prior_dialysate_temp_mean=prior_dialysate_temp_mean,
        prior_dialysate_sodium_mean=prior_dialysate_sodium_mean,
        is_training=False,
    )


# ── Model cache ───────────────────────────────────────────────────────────────

_IDH_MODEL       = None
_IDH_MODEL_MTIME = 0
_IDH_MAPIE_MODEL = None
_IDH_MAPIE_MTIME = 0


def _load_idh_mapie():
    global _IDH_MAPIE_MODEL, _IDH_MAPIE_MTIME
    if not (_MAPIE_AVAILABLE and _JOBLIB_AVAILABLE) or not os.path.exists(_IDH_MAPIE_PATH):
        return None
    try:
        mtime = os.path.getmtime(_IDH_MAPIE_PATH)
        if _IDH_MAPIE_MODEL is not None and mtime <= _IDH_MAPIE_MTIME:
            return _IDH_MAPIE_MODEL
        _IDH_MAPIE_MODEL = joblib.load(_IDH_MAPIE_PATH)
        _IDH_MAPIE_MTIME = mtime
        return _IDH_MAPIE_MODEL
    except Exception as exc:
        logger.debug("MAPIE model load skipped: %s", exc)
        return None


def _restore_model_from_db() -> bool:
    """Write the latest IDH model binary and metadata from the DB to local disk.

    Called when the local .joblib or json file is missing (e.g. after a container
    redeploy wipes the ephemeral filesystem).  Returns True if restored.
    """
    if not _JOBLIB_AVAILABLE:
        return False
    try:
        from database import SessionLocal as _SL, ModelArtifact as _MA
        _db = _SL()
        try:
            art = (
                _db.query(_MA)
                .filter(_MA.model_name == "idh_v1", _MA.model_binary.isnot(None))
                .order_by(_MA.trained_at.desc())
                .first()
            )
            if art is None or not art.model_binary:
                return False
            with open(_IDH_MODEL_PATH, "wb") as f:
                f.write(art.model_binary)
            logger.info("IDH model restored from DB (version=%s)", art.version)

            # Recreate the idh_model_meta.json file from DB metrics
            try:
                metrics = json.loads(art.metrics_json) if art.metrics_json else {}
                meta = {
                    "trained_at": art.version,
                    "algorithm": metrics.get("algorithm", "XGBoost (calibrated)" if _XGB_AVAILABLE else "LogisticRegression (calibrated)"),
                    "n_samples": metrics.get("n_samples"),
                    "n_events": metrics.get("n_events"),
                    "event_rate": round(metrics.get("n_events") / metrics.get("n_samples"), 4) if metrics.get("n_samples") and metrics.get("n_events") is not None else 0.0,
                    "events_per_feature": metrics.get("epf"),
                    "overfitting_risk": metrics.get("epf", 10.0) < _EPF_WARN if metrics.get("epf") is not None else False,
                    "cv_auc": metrics.get("cv_auc"),
                    "cv_auc_uncalibrated": metrics.get("cv_auc_uncalibrated"),
                    "auc_warning": metrics.get("cv_auc", 1.0) < 0.65 if metrics.get("cv_auc") is not None else False,
                    "feature_names": IDH_FEATURE_NAMES,
                }
                with open(_IDH_META_PATH, "w") as f:
                    json.dump(meta, f, indent=2)
                logger.info("IDH model metadata restored from DB")
            except Exception as meta_exc:
                logger.warning("Failed to restore IDH model metadata from DB: %s", meta_exc)

            return True
        finally:
            _db.close()
    except Exception as exc:
        logger.warning("IDH model DB restore failed: %s", exc)
        return False


def _load_idh_model():
    global _IDH_MODEL, _IDH_MODEL_MTIME
    if not _JOBLIB_AVAILABLE:
        return None
    # If the local file or meta file is missing, attempt to restore it from the database.
    if not os.path.exists(_IDH_MODEL_PATH) or not os.path.exists(_IDH_META_PATH):
        if not _restore_model_from_db():
            return None
    try:
        mtime = os.path.getmtime(_IDH_MODEL_PATH)
        if _IDH_MODEL is not None and mtime <= _IDH_MODEL_MTIME:
            return _IDH_MODEL
        _IDH_MODEL       = joblib.load(_IDH_MODEL_PATH)
        _IDH_MODEL_MTIME = mtime
        return _IDH_MODEL
    except Exception as exc:
        logger.warning("Failed to load IDH model: %s", exc)
        return None


# ── Model status ──────────────────────────────────────────────────────────────

def get_idh_model_status() -> dict:
    """Return metadata dict for the trained IDH model (or 'not trained' sentinel)."""
    if not os.path.exists(_IDH_MODEL_PATH):
        return {
            "trained": False,
            "sklearn_available": _SKLEARN_AVAILABLE,
            "xgboost_available": _XGB_AVAILABLE,
            "message": "No IDH model trained yet. POST /admin/train-idh-model to train.",
        }
    meta: dict = {}
    if os.path.exists(_IDH_META_PATH):
        try:
            with open(_IDH_META_PATH) as f:
                meta = json.load(f)
        except Exception:
            pass
    return {"trained": True, "sklearn_available": _SKLEARN_AVAILABLE,
            "xgboost_available": _XGB_AVAILABLE, **meta}


# ── Training ──────────────────────────────────────────────────────────────────

def train_idh_model(db) -> dict:
    """
    Train the IDH prediction model on all SessionRecord data.

    Uses XGBoost if available, else Calibrated LogisticRegression.
    Requires ≥ _MIN_EVENTS (130) IDH events for a trained model;
    returns an informative error otherwise.
    """
    from sqlalchemy.orm import Session as _Session, joinedload
    from database import Patient, SessionRecord, MonthlyRecord

    if not (_SKLEARN_AVAILABLE and _JOBLIB_AVAILABLE):
        return {"success": False, "error": "scikit-learn or joblib not installed."}

    # ── 1. Bulk-load all data in 3 queries (replaces N+1 per-patient queries) ──
    patients = (
        db.query(Patient)
        .options(
            joinedload(Patient.comorbidity_profile),
            joinedload(Patient.cardiac),
        )
        .filter(Patient.is_active == True)
        .all()
    )
    if not patients:
        return {"success": False, "error": "No active patients found."}

    patient_ids = [p.id for p in patients]
    patient_map = {p.id: p for p in patients}

    all_sessions = (
        db.query(SessionRecord)
        .options(joinedload(SessionRecord.symptom_report))
        .filter(SessionRecord.patient_id.in_(patient_ids))
        .order_by(SessionRecord.patient_id, SessionRecord.session_date.asc())
        .all()
    )
    all_monthly = (
        db.query(MonthlyRecord)
        .filter(MonthlyRecord.patient_id.in_(patient_ids))
        .order_by(MonthlyRecord.patient_id, MonthlyRecord.record_month.desc())
        .all()
    )

    # Group into per-patient dicts for O(1) lookup during feature extraction.
    from collections import defaultdict
    sessions_by_patient: dict = defaultdict(list)
    for s in all_sessions:
        sessions_by_patient[s.patient_id].append(s)

    monthly_by_patient: dict = defaultdict(list)
    for r in all_monthly:
        monthly_by_patient[r.patient_id].append(r)

    X, y = [], []
    skipped_patients = 0

    for pid, patient in patient_map.items():
        sessions    = sessions_by_patient[pid]   # already sorted asc by session_date
        monthly_recs = monthly_by_patient[pid]   # already sorted desc by record_month

        if len(sessions) < 2:
            skipped_patients += 1
            continue

        monthly_by_month = {r.record_month: r for r in monthly_recs}

        for i, sess in enumerate(sessions):
            if i == 0:
                continue
            past = list(reversed(sessions[:i]))   # sorted desc (newest-past first)

            mr  = monthly_by_month.get(sess.record_month)
            mr3 = monthly_recs[:3]

            try:
                feats = _extract_idh_features_for_training(
                    session=sess, patient=patient,
                    past_sessions=past, monthly_record=mr,
                    monthly_records_3mo=mr3,
                )
                label = _compute_idh_label(sess)
                X.append(feats)
                y.append(label)
            except Exception as exc:
                logger.debug("IDH training extraction failed for session %s: %s", sess.id, exc)
                continue

    n_samples = len(y)
    n_events  = sum(y)
    event_rate = round(n_events / n_samples, 4) if n_samples > 0 else 0.0

    if n_samples < max(_MIN_EVENTS * 2, 40):
        return {
            "success": False,
            "n_samples": n_samples,
            "n_events": n_events,
            "error": (
                f"Insufficient session records: {n_samples} usable sessions "
                f"(need ≥{max(_MIN_EVENTS * 2, 40)}). Keep entering session data."
            ),
        }

    if n_events < _MIN_EVENTS:
        return {
            "success": False,
            "n_samples": n_samples,
            "n_events": n_events,
            "events_needed": _MIN_EVENTS,
            "epf_current": round(n_events / _N_FEATURES, 1),
            "epf_minimum": _EPF_MIN,
            "error": (
                f"Insufficient IDH events: {n_events} recorded, need ≥{_MIN_EVENTS} "
                f"({_EPF_MIN} per feature × {_N_FEATURES} features). "
                f"Currently at {round(n_events / _N_FEATURES, 1)} events/feature. "
                "Model will use heuristic fallback until more outcome data is collected."
            ),
        }

    X_arr = np.array(X, dtype=float)
    y_arr = np.array(y, dtype=int)

    epf = round(n_events / _N_FEATURES, 1)
    overfitting_risk = epf < _EPF_WARN
    n_folds = min(5, n_events)

    # ── 2. Choose algorithm ────────────────────────────────────────────────────
    cv = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)

    if _XGB_AVAILABLE:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            base_xgb = xgb.XGBClassifier(
                n_estimators=200,
                max_depth=4,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                scale_pos_weight=(n_samples - n_events) / max(n_events, 1),
                eval_metric="logloss",
                random_state=42,
                verbosity=0,
            )
            pipe = Pipeline([
                ("imputer", SimpleImputer(strategy="median")),
                ("xgb", base_xgb),
            ])
            # cv_auc_uncalibrated: discrimination of the raw XGBoost pipeline.
            cv_probs_raw      = cross_val_predict(pipe, X_arr, y_arr, cv=cv, method="predict_proba")
            cv_auc_uncalib    = round(float(roc_auc_score(y_arr, cv_probs_raw[:, 1])), 3)

            # cv_auc: AUC of the calibrated model via manual cross-validation split (no leakage, no 2x CV speed issue)
            cv_probs = np.zeros(len(y_arr))
            for train_idx, val_idx in cv.split(X_arr, y_arr):
                X_train, y_train = X_arr[train_idx], y_arr[train_idx]
                X_val, y_val = X_arr[val_idx], y_arr[val_idx]
                
                from sklearn.base import clone
                fold_pipe = clone(pipe)
                
                n_events_train = int(sum(y_train))
                inner_cv = min(3, n_events_train) if n_events_train >= 3 else 2
                
                fold_cal = CalibratedClassifierCV(
                    fold_pipe,
                    cv=inner_cv,
                    method="isotonic" if len(y_train) >= 50 else "sigmoid"
                )
                fold_cal.fit(X_train, y_train)
                cv_probs[val_idx] = fold_cal.predict_proba(X_val)[:, 1]
                
            cv_auc = round(float(roc_auc_score(y_arr, cv_probs)), 3)

            # cal_model: full fit on all data (used for inference).
            cal_model = CalibratedClassifierCV(pipe, cv=n_folds, method="isotonic" if n_samples >= 50 else "sigmoid")
            cal_model.fit(X_arr, y_arr)

        algorithm = "XGBoost (calibrated)"

    else:
        # Fallback: Calibrated Logistic Regression
        c_reg = 0.3 if overfitting_risk else 0.5
        base_lr = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler",  StandardScaler()),
            ("lr",      LogisticRegression(
                class_weight="balanced", C=c_reg,
                solver="lbfgs", max_iter=1000,
            )),
        ])
        cv_probs_raw   = cross_val_predict(base_lr, X_arr, y_arr, cv=cv, method="predict_proba")
        cv_auc_uncalib = round(float(roc_auc_score(y_arr, cv_probs_raw[:, 1])), 3)

        # cv_auc: AUC of the calibrated model via manual cross-validation split
        cv_probs = np.zeros(len(y_arr))
        for train_idx, val_idx in cv.split(X_arr, y_arr):
            X_train, y_train = X_arr[train_idx], y_arr[train_idx]
            X_val, y_val = X_arr[val_idx], y_arr[val_idx]
            
            from sklearn.base import clone
            fold_lr = clone(base_lr)
            
            n_events_train = int(sum(y_train))
            inner_cv = min(3, n_events_train) if n_events_train >= 3 else 2
            
            fold_cal = CalibratedClassifierCV(fold_lr, cv=inner_cv, method="sigmoid")
            fold_cal.fit(X_train, y_train)
            cv_probs[val_idx] = fold_cal.predict_proba(X_val)[:, 1]
            
        cv_auc = round(float(roc_auc_score(y_arr, cv_probs)), 3)

        cal_model = CalibratedClassifierCV(base_lr, cv=n_folds, method="sigmoid")
        cal_model.fit(X_arr, y_arr)
        
        algorithm = "LogisticRegression (calibrated, XGBoost unavailable)"

    auc_warning = cv_auc < 0.65 or overfitting_risk

    # ── 3. Persist model ───────────────────────────────────────────────────────
    import hashlib as _hl, json as _js, io as _io
    global _IDH_MODEL
    joblib.dump(cal_model, _IDH_MODEL_PATH, compress=3)
    _IDH_MODEL = None   # invalidate in-process cache

    # Capture the compressed bytes for DB storage so the model survives
    # container redeployments on ephemeral filesystems.
    _model_buf = _io.BytesIO()
    joblib.dump(cal_model, _model_buf, compress=3)
    _model_bytes = _model_buf.getvalue()

    from datetime import datetime as _dt
    trained_at_str = _dt.now().isoformat(timespec="seconds")
    training_data_hash = _hl.sha256(
        _js.dumps(X, sort_keys=True).encode()
    ).hexdigest()

    meta = {
        "trained_at":              trained_at_str,
        "algorithm":               algorithm,
        "n_samples":               n_samples,
        "n_events":                n_events,
        "event_rate":              event_rate,
        "events_per_feature":      epf,
        "overfitting_risk":        overfitting_risk,
        "n_folds":                 n_folds,
        # cv_auc: cross-validated AUC of the *calibrated* model — this is what
        # is deployed and what the reported metric should reflect.
        "cv_auc":                  cv_auc,
        # cv_auc_uncalibrated: AUC of the base pipeline before calibration,
        # kept for diagnostic comparison only.
        "cv_auc_uncalibrated":     cv_auc_uncalib,
        "auc_warning":             auc_warning,
        "feature_names":           IDH_FEATURE_NAMES,
        "skipped_patients":        skipped_patients,
        "training_data_hash":      training_data_hash,
        "data_quality_note":  (
            f"EPF={epf:.1f} (need ≥{_EPF_WARN} for reliable estimates). "
            + ("⚠ Overfitting risk." if overfitting_risk else "EPF adequate.")
        ),
    }
    with open(_IDH_META_PATH, "w") as f:
        json.dump(meta, f, indent=2)

    # ── 4. Register ModelArtifact (with binary blob) ───────────────────────────
    try:
        from database import SessionLocal as _SL, ModelArtifact as _MA
        from datetime import datetime as _dt2
        _art_db = _SL()
        try:
            art = _MA(
                model_name          = "idh_v1",
                version             = trained_at_str,
                trained_at          = _dt2.fromisoformat(trained_at_str),
                training_data_hash  = training_data_hash,
                metrics_json        = json.dumps({
                    "cv_auc": cv_auc,
                    "cv_auc_uncalibrated": cv_auc_uncalib,
                    "n_samples": n_samples,
                    "n_events": n_events,
                    "epf": epf,
                    "algorithm": algorithm,
                }),
                feature_schema_json = json.dumps(IDH_FEATURE_NAMES),
                artifact_path       = os.path.relpath(_IDH_MODEL_PATH),
                model_binary        = _model_bytes,
            )
            _art_db.add(art)
            _art_db.commit()
        finally:
            _art_db.close()
    except Exception as _art_exc:
        logger.warning("Failed to register IDH ModelArtifact: %s", _art_exc)

    # ── 5. MAPIE conformal classifier (80% prediction sets, Bangsgaard-style PI) ─
    if _MAPIE_AVAILABLE and _JOBLIB_AVAILABLE:
        try:
            mapie_clf = MapieClassifier(
                estimator=pipe if _XGB_AVAILABLE else base_lr,
                cv=n_folds,
                method="lac",
            )
            mapie_clf.fit(X_arr, y_arr)
            joblib.dump(mapie_clf, _IDH_MAPIE_PATH, compress=3)
            meta["mapie_trained"] = True
            logger.info("IDH MAPIE conformal classifier trained and saved.")
        except Exception as mapie_exc:
            logger.warning("IDH MAPIE training failed (non-fatal): %s", mapie_exc)
            meta["mapie_trained"] = False
    else:
        meta["mapie_trained"] = False

    logger.info(
        "IDH model trained: algo=%s n=%d events=%d epf=%.1f cv_auc=%.3f drift_risk=%s",
        algorithm, n_samples, n_events, epf, cv_auc, overfitting_risk,
    )
    return {"success": True, **meta}


# ── SHAP feature attribution ──────────────────────────────────────────────────

def _compute_idh_shap(model, feats: list) -> Optional[list]:
    """Return top-10 SHAP contributors sorted by |shap_value| desc."""
    if not _SHAP_AVAILABLE:
        return None
    try:
        x = np.array([feats], dtype=float)

        # Try TreeExplainer for XGBoost; fall back to LinearExplainer for LR
        base_estimator = getattr(model, "estimators_", [model])[0]

        # Walk the pipeline to find the final estimator
        if hasattr(base_estimator, "named_steps"):
            final_step = list(base_estimator.named_steps.values())[-1]
            # Preprocess
            for name, step in base_estimator.named_steps.items():
                if name == list(base_estimator.named_steps)[-1]:
                    break
                x = step.transform(x)
        else:
            final_step = base_estimator

        if _XGB_AVAILABLE and isinstance(final_step, xgb.XGBClassifier):
            explainer = _shap.TreeExplainer(final_step)
        else:
            explainer = _shap.LinearExplainer(final_step, np.zeros_like(x))

        sv = explainer.shap_values(x)
        raw = sv[0] if hasattr(sv, "__len__") and not isinstance(sv, np.ndarray) else sv
        if isinstance(raw, list):
            raw = raw[1]  # positive class for binary classification
        if raw.ndim == 2:
            raw = raw[0]

        result = [
            {
                "feature":    IDH_FEATURE_NAMES[i],
                "value":      round(float(feats[i]), 4) if feats[i] is not None else None,
                "shap_value": round(float(raw[i]), 4),
            }
            for i in range(len(IDH_FEATURE_NAMES))
        ]
        result.sort(key=lambda r: abs(r["shap_value"]), reverse=True)
        return result[:10]
    except Exception as exc:
        logger.debug("IDH SHAP skipped: %s", exc)
        return None


# ── MLOps prediction logger ───────────────────────────────────────────────────

def _log_idh_prediction(feats: list, prob: float, patient_id: Optional[int],
                         session_date: Optional[str], model_version: Optional[str]) -> None:
    """Fire-and-forget: log one IDH inference call to ml_predictions."""
    if patient_id is None:
        return
    try:
        from database import SessionLocal as _SL, MLPrediction as _MP, compute_patient_id_hash as _cph
        from datetime import datetime as _dt
        feat_dict = {name: feats[i] for i, name in enumerate(IDH_FEATURE_NAMES)}
        feat_json = json.dumps(feat_dict, sort_keys=True)
        feat_hash = hashlib.sha256(feat_json.encode()).hexdigest()
        month_str = (session_date or _dt.utcnow().strftime("%Y-%m-%d"))[:7]
        _db = _SL()
        try:
            row = _MP(
                patient_id          = patient_id,
                patient_id_hash     = _cph(patient_id),
                model_name          = "idh_v1",
                model_version       = model_version or "unknown",
                input_feature_hash  = feat_hash,
                features_json       = feat_json,
                prediction_score    = round(prob, 6),
                predicted_class     = int(prob >= _THRESHOLD_MODERATE),
                prediction_month    = month_str,
            )
            _db.add(row)
            _db.commit()
        finally:
            _db.close()
    except Exception as exc:
        logger.debug("IDH MLPrediction log skipped: %s", exc)


# ── Risk level utilities ──────────────────────────────────────────────────────

def _prob_to_risk_level(prob: float) -> str:
    if prob >= _THRESHOLD_HIGH:
        return "Very High"
    if prob >= _THRESHOLD_MODERATE:
        return "High"
    if prob >= _THRESHOLD_LOW:
        return "Moderate"
    return "Low"


def _risk_level_actions(risk_level: str) -> list:
    actions = {
        "Very High": [
            "Extended pre-session haemodynamic evaluation",
            "Consider UF profiling (step-down or sodium profiling)",
            "Cool dialysate temperature (35–36 °C)",
            "Withhold morning antihypertensives if SBP < 140 mmHg",
            "Alert treating physician before starting session",
            "BP monitoring every 15 minutes minimum",
        ],
        "High": [
            "Cool dialysate temperature (35.5–36.5 °C)",
            "Consider reducing UF rate by 10–20%",
            "Withhold morning antihypertensives if SBP < 150 mmHg",
            "BP monitoring every 15–20 minutes",
            "Avoid intradialytic meals",
        ],
        "Moderate": [
            "Monitor BP every 20–30 minutes",
            "Avoid intradialytic meals",
            "Ensure patient is in supine/Trendelenburg-ready position",
        ],
        "Low": [
            "Standard session protocol",
        ],
    }
    return actions.get(risk_level, [])


# ── Heuristic fallback ────────────────────────────────────────────────────────

def _heuristic_idh_score(feats: list, session_plan: dict, patient_info: dict) -> dict:
    """
    Rule-based fallback when no trained model is available.
    Uses the highest-evidence predictors from literature.
    """
    score = 0
    factors = []

    # Prior IDH history (strongest predictor)
    prior_idh_rate = feats[21] if len(feats) > 21 else 0
    if prior_idh_rate >= 0.6:
        score += 35; factors.append("High prior IDH frequency (≥3/5 recent sessions)")
    elif prior_idh_rate >= 0.3:
        score += 20; factors.append("Moderate prior IDH frequency (≥1–2/5 recent sessions)")

    # UF rate
    uf_rate = feats[14] if len(feats) > 14 else 0
    if uf_rate and uf_rate > 13:
        score += 25; factors.append(f"Very high UF rate ({uf_rate:.1f} mL/kg/h)")
    elif uf_rate and uf_rate > 10:
        score += 15; factors.append(f"High UF rate ({uf_rate:.1f} mL/kg/h > 10 mL/kg/h threshold)")

    # Pre-HD SBP < 110 mmHg
    pre_sbp = feats[11] if len(feats) > 11 else None
    if pre_sbp is not None and pre_sbp < 110:
        score += 20; factors.append(f"Low pre-HD SBP ({pre_sbp:.0f} mmHg)")

    # Albumin
    albumin = feats[9] if len(feats) > 9 else None
    if albumin is not None and albumin < 3.0:
        score += 15; factors.append(f"Severe hypoalbuminaemia ({albumin:.1f} g/dL) — impaired vascular refilling")
    elif albumin is not None and albumin < 3.5:
        score += 8;  factors.append(f"Hypoalbuminaemia ({albumin:.1f} g/dL)")

    # Cardiac
    if feats[2]:   score += 8;  factors.append("Congestive heart failure")
    lvef = feats[7] if len(feats) > 7 else 60
    if lvef < 40:  score += 10; factors.append(f"Reduced EF ({lvef:.0f}%)")

    # Antihypertensives taken pre-HD
    if feats[18]:  score += 10; factors.append("Antihypertensives taken morning of session")

    # Previous session symptoms (from the new clinical features)
    if len(feats) > 31 and feats[31]:
        score += 5; factors.append("Muscle cramps in the previous session")
    if len(feats) > 32 and feats[32]:
        score += 5; factors.append("Nausea/vomiting in the previous session")
    if len(feats) > 33 and feats[33]:
        score += 5; factors.append("Dizziness/giddiness in the previous session")
    if len(feats) > 34 and feats[34] is not None and feats[34] > 240:
        score += 5; factors.append("Prolonged post-dialysis recovery time in the previous session")

    score = min(score, 100)
    prob  = score / 100.0
    risk_level = _prob_to_risk_level(prob)

    return {
        "available":    True,
        "method":       "Heuristic (no trained model — POST /admin/train-idh-model)",
        "risk_score":   score,
        "risk_probability": prob,
        "risk_level":   risk_level,
        "risk_factors": factors,
        "actions":      _risk_level_actions(risk_level),
        "shap_values":  None,
        "model_cv_auc": None,
        "model_trained_at": None,
        "auc_warning":  False,
        "inputs_missing": [],
        "model_is_heuristic": True,
    }


# ── Main inference function ───────────────────────────────────────────────────

def compute_idh_risk(
    session_plan:        dict,
    patient_info:        dict,
    past_sessions_list:  list,
    monthly_data:        dict = None,
    monthly_records_3mo: list = None,
    log_prediction:      bool = True,
) -> dict:
    """
    Compute pre-session IDH risk probability.

    Returns a standardised dict:
    {
        available: bool,
        data: {
            risk_score:      0–100 (int),
            risk_probability: 0.0–1.0,
            risk_level:      'Low' | 'Moderate' | 'High' | 'Very High',
            risk_factors:    [str],
            actions:         [str],
            shap_values:     [...] | None,
            method:          str,
            model_cv_auc:    float | None,
            model_trained_at: str | None,
            auc_warning:     bool,
            inputs_missing:  [str],
        }
    }
    """
    feats = _extract_idh_features_for_inference(
        session_plan, patient_info, past_sessions_list,
        monthly_data, monthly_records_3mo,
    )

    # ── Compute missing-input report ──────────────────────────────────────────
    sp = session_plan or {}
    pi = patient_info or {}
    md = monthly_data or {}
    missing = []
    if sp.get("pre_hd_sbp") is None:       missing.append("Pre-HD SBP")
    if sp.get("uf_volume") is None:         missing.append("UF Volume (Prescription)")
    if md.get("albumin") is None:           missing.append("Albumin (latest monthly)")
    if pi.get("age") is None:              missing.append("Patient Age")
    if pi.get("ejection_fraction") is None: missing.append("LVEF (echo)")
    if sp.get("dialysate_temp") is None:    missing.append("Dialysate Temperature")

    model = _load_idh_model()

    # Refuse inference if model file exists but no registered artifact
    if model is not None:
        try:
            from database import SessionLocal as _SL, ModelArtifact as _MA
            _gate_db = _SL()
            try:
                _reg = _gate_db.query(_MA).filter(_MA.model_name == "idh_v1").first()
            finally:
                _gate_db.close()
            if _reg is None:
                logger.warning("IDH model file exists but no ModelArtifact row — refusing inference.")
                model = None
        except Exception:
            pass

    if model is not None:
        try:
            prob       = float(model.predict_proba(np.array([feats], dtype=float))[0][1])
            risk_pct   = round(prob * 100, 1)
            risk_level = _prob_to_risk_level(prob)

            meta: dict = {}
            if os.path.exists(_IDH_META_PATH):
                try:
                    with open(_IDH_META_PATH) as _f:
                        meta = json.load(_f)
                except Exception:
                    pass

            # ── Clinically interpretable risk factors ─────────────────────────
            factors = []
            if feats[21] >= 0.6:   factors.append("High prior IDH rate (≥3 of last 7 sessions)")
            elif feats[21] >= 0.3: factors.append("Moderate prior IDH frequency")
            if feats[14] > 13:     factors.append(f"Very high UF rate ({feats[14]:.1f} mL/kg/h)")
            elif feats[14] > 10:   factors.append(f"High UF rate ({feats[14]:.1f} mL/kg/h)")
            if feats[9] < 3.0:     factors.append(f"Severe hypoalbuminaemia ({feats[9]:.1f} g/dL)")
            elif feats[9] < 3.5:   factors.append(f"Hypoalbuminaemia ({feats[9]:.1f} g/dL)")
            if feats[11] and feats[11] < 110:
                factors.append(f"Low pre-HD SBP ({feats[11]:.0f} mmHg)")
            if feats[7] < 40:      factors.append(f"Reduced LVEF ({feats[7]:.0f}%)")
            if feats[8] >= 2:      factors.append("Moderate–severe diastolic dysfunction")
            if feats[1]:           factors.append("Diabetes mellitus")
            if feats[2]:           factors.append("Congestive heart failure")
            if feats[5]:           factors.append("Atrial fibrillation")
            if feats[18]:          factors.append("Antihypertensives taken pre-session")
            if feats[23] < -3:     factors.append("Declining pre-HD SBP trend (last 7 sessions)")
            if feats[24] < -0.2:   factors.append("Declining albumin trend (last 3 months)")

            # Incorporate new features into interpretations
            if len(feats) > 28 and feats[28] is not None and feats[28] < 10.0:
                factors.append(f"Anaemia (Hb {feats[28]:.1f} g/dL)")
            if len(feats) > 31 and feats[31]:
                factors.append("Muscle cramps in the previous session")
            if len(feats) > 32 and feats[32]:
                factors.append("Nausea/vomiting in the previous session")
            if len(feats) > 33 and feats[33]:
                factors.append("Dizziness/giddiness in the previous session")
            if len(feats) > 34 and feats[34] is not None and feats[34] > 240:
                factors.append(f"Prolonged recovery time ({feats[34]:.0f} mins) in the previous session")
            if len(feats) > 39 and feats[39] is not None and feats[39] > 37.0:
                factors.append(f"Warm dialysate temperature mean ({feats[39]:.1f} °C)")

            shap_values = _compute_idh_shap(model, feats)

            # ── MAPIE 80% conformal prediction interval ───────────────────────
            pi_lower: Optional[float] = None
            pi_upper: Optional[float] = None
            mapie_model = _load_idh_mapie()
            if mapie_model is not None:
                try:
                    x_arr = np.array([feats], dtype=float)
                    _, y_ps = mapie_model.predict(x_arr, alpha=0.20)
                    # y_ps shape: (n_samples, n_classes, n_alpha)
                    in_set = y_ps[0, :, 0]   # boolean mask for each class at 80% coverage
                    # If only class-1 is in set: lower bound = prob; upper = prob
                    # If both classes in set: full uncertainty → widen to [0, 1]
                    # If only class-0: near-zero risk
                    if in_set[1] and not in_set[0]:
                        pi_lower = round(max(prob - 0.05, 0.0), 3)
                        pi_upper = round(min(prob + 0.05, 1.0), 3)
                    elif in_set[0] and in_set[1]:
                        pi_lower = 0.0
                        pi_upper = 1.0
                    else:
                        pi_lower = 0.0
                        pi_upper = round(min(prob + 0.10, 1.0), 3)
                except Exception as pi_exc:
                    logger.debug("MAPIE PI skipped: %s", pi_exc)

            if log_prediction:
                session_date = sp.get("session_date")
                _log_idh_prediction(
                    feats=feats, prob=prob,
                    patient_id=pi.get("id"),
                    session_date=str(session_date) if session_date else None,
                    model_version=meta.get("trained_at"),
                )

            return {
                "available": True,
                "error": None,
                "data": {
                    "available":         True,
                    "method":            meta.get("algorithm", "ML model"),
                    "risk_score":        risk_pct,
                    "risk_probability":  prob,
                    "risk_level":        risk_level,
                    "risk_factors":      factors,
                    "actions":           _risk_level_actions(risk_level),
                    "shap_values":       shap_values,
                    "model_cv_auc":      meta.get("cv_auc"),
                    "model_n_samples":   meta.get("n_samples"),
                    "model_n_events":    meta.get("n_events"),
                    "model_trained_at":  meta.get("trained_at"),
                    "auc_warning":       meta.get("auc_warning", False),
                    "inputs_missing":    missing,
                    "model_is_heuristic": False,
                    "pi_lower":          pi_lower,
                    "pi_upper":          pi_upper,
                },
            }
        except Exception as exc:
            logger.warning("IDH model predict_proba failed: %s — using heuristic", exc)

    # ── Heuristic fallback ────────────────────────────────────────────────────
    heuristic = _heuristic_idh_score(feats, sp, pi)
    heuristic["inputs_missing"] = missing
    return {"available": True, "error": None, "data": heuristic}
