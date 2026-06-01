"""
services/access_failure_model.py
=================================
Vascular Access Time-to-Failure prediction model.

Reference:
    Hsieh et al. 2023. "IoMT-Based XGBoost Model for Vascular Access Failure
    Prediction in Haemodialysis Patients." (90.7% precision for 90-day failure.)

Features (12 total, derived from longitudinal access surveillance records):
    Trend features (require ≥ 2 Doppler records):
        qa_latest          — most recent access flow (mL/min)
        qa_slope           — mL/min per record (declining = negative)
        qa_min             — minimum Qa across last 6 records
        delta_qa_pct       — % change from first to last record

    Cross-sectional features (single-record):
        recirculation_pct  — latest recirculation %
        psi_psv            — peak systolic velocity (cm/s)
        ri                 — resistance index
        stenosis_pct       — stenosis %

    Clinical features:
        access_age_days    — days since access creation
        access_type_avf    — 1 if AVF, 0 if AVG / CVC
        thrombosis_count   — number of prior thrombosis events
        cannulation_fail_rate — % of sessions with cannulation difficulty

Outcome label:
    access_failure_90d — 1 if access failed within 90 days of record date.
    Sourced from clinical_events where event_type = 'av_fistula_failure' or
    'av_fistula_thrombosis' or 'catheter_related_infection'.

Model: XGBoost → Calibrated LogisticRegression fallback → threshold heuristic.
Training trigger: POST /access/train-failure-model (admin only).
Celery: weekly task_compute_access_failure_risk for patients with ≥ 3 records.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

try:
    import joblib
    _JOBLIB = True
except ImportError:
    _JOBLIB = False

try:
    import xgboost as xgb
    _XGB = True
except ImportError:
    _XGB = False

try:
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import StratifiedKFold
    from sklearn.metrics import roc_auc_score
    _SK = True
except ImportError:
    _SK = False

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MODEL_PATH = os.path.join(_BASE, "access_failure_model.joblib")
_META_PATH  = os.path.join(_BASE, "access_failure_meta.json")

# KDOQI absolute Qa thresholds (mL/min)
_QA_AVF_FAIL = 500.0
_QA_AVG_FAIL = 400.0

_ACCESS_MODEL       = None
_ACCESS_MODEL_MTIME = 0


def _load_model():
    global _ACCESS_MODEL, _ACCESS_MODEL_MTIME
    if not (_JOBLIB and os.path.exists(_MODEL_PATH)):
        return None
    try:
        mtime = os.path.getmtime(_MODEL_PATH)
        if _ACCESS_MODEL is not None and mtime <= _ACCESS_MODEL_MTIME:
            return _ACCESS_MODEL
        _ACCESS_MODEL = joblib.load(_MODEL_PATH)
        _ACCESS_MODEL_MTIME = mtime
        return _ACCESS_MODEL
    except Exception as exc:
        logger.debug("Access failure model load failed: %s", exc)
        return None


def _slope(values: List[float]) -> float:
    clean = [v for v in values if v is not None and not np.isnan(v)]
    if len(clean) < 2:
        return 0.0
    n = len(clean)
    xm = (n - 1) / 2
    ym = sum(clean) / n
    num = sum((i - xm) * (y - ym) for i, y in enumerate(clean))
    den = sum((i - xm) ** 2 for i in range(n))
    return num / den if den else 0.0


def build_feature_vector(
    surveillance_records: List[dict],
    access_info:          dict,
    session_stats:        dict,
) -> List[float]:
    """
    Build a 12-element feature vector from raw access surveillance data.

    surveillance_records : list of dicts with keys qa_ml_min, recirculation_pct,
                           psv_cm_s, ri, stenosis_pct, record_date — newest first.
    access_info          : dict with keys access_type, creation_date, thrombosis_count.
    session_stats        : dict with keys total_sessions, cannulation_difficulty_count.
    """
    recs = surveillance_records[:6]  # up to 6 most recent
    qa_vals = [r.get("qa_ml_min") for r in recs if r.get("qa_ml_min") is not None]

    qa_latest     = float(qa_vals[0]) if qa_vals else float("nan")
    qa_min        = float(min(qa_vals)) if qa_vals else float("nan")
    qa_slope      = _slope(list(reversed(qa_vals)))   # oldest first for slope
    delta_qa_pct  = float((qa_vals[0] - qa_vals[-1]) / max(qa_vals[-1], 1) * 100) if len(qa_vals) >= 2 else 0.0

    latest = recs[0] if recs else {}
    recirc     = float(latest.get("recirculation_pct") or 0.0)
    psv        = float(latest.get("psv_cm_s") or latest.get("peak_systolic_velocity") or float("nan"))
    ri         = float(latest.get("ri") or latest.get("resistance_index") or float("nan"))
    stenosis   = float(latest.get("stenosis_pct") or 0.0)

    access_type   = str(access_info.get("access_type") or "").lower()
    is_avf        = 1.0 if "avf" in access_type or "fistula" in access_type else 0.0
    creation_date = access_info.get("creation_date")
    if creation_date and isinstance(creation_date, date):
        access_age = float((date.today() - creation_date).days)
    elif creation_date:
        try:
            access_age = float((date.today() - date.fromisoformat(str(creation_date)[:10])).days)
        except Exception:
            access_age = float("nan")
    else:
        access_age = float("nan")

    thrombosis_count = float(access_info.get("thrombosis_count") or 0)

    total_sess   = session_stats.get("total_sessions") or 1
    diff_count   = session_stats.get("cannulation_difficulty_count") or 0
    cannulation_fail_rate = float(diff_count) / float(total_sess) * 100.0

    return [
        qa_latest,
        qa_slope,
        qa_min,
        delta_qa_pct,
        recirc,
        psv,
        ri,
        stenosis,
        access_age,
        is_avf,
        thrombosis_count,
        cannulation_fail_rate,
    ]


_FEATURE_NAMES = [
    "qa_latest", "qa_slope", "qa_min", "delta_qa_pct",
    "recirculation_pct", "psv_cm_s", "ri", "stenosis_pct",
    "access_age_days", "is_avf", "thrombosis_count", "cannulation_fail_rate",
]


def compute_access_failure_risk(
    surveillance_records: List[dict],
    access_info:          dict,
    session_stats:        dict,
) -> Dict:
    """
    Predict 90-day vascular access failure probability.

    Returns dict with:
        probability_90d   — float 0–1
        risk_level        — 'Low' | 'Moderate' | 'High'
        risk_factors      — list of strings
        method            — 'XGBoost' | 'LogisticRegression' | 'Heuristic'
        model_trained     — bool
    """
    if len(surveillance_records) < 2:
        return {
            "available":      False,
            "error":          "Minimum 2 Doppler surveillance records required.",
            "model_trained":  False,
        }

    feats = build_feature_vector(surveillance_records, access_info, session_stats)
    x = np.array([feats], dtype=float)

    model = _load_model()
    if model is not None:
        try:
            prob = float(model.predict_proba(x)[0][1])
            risk_level = "High" if prob >= 0.50 else ("Moderate" if prob >= 0.25 else "Low")
            return {
                "available":      True,
                "probability_90d": round(prob, 3),
                "risk_level":     risk_level,
                "risk_factors":   _interpret(feats, access_info),
                "method":         "ML model",
                "model_trained":  True,
            }
        except Exception as exc:
            logger.warning("Access failure model inference failed: %s", exc)

    # ── Heuristic fallback (KDOQI thresholds) ─────────────────────────────────
    return _heuristic(feats, access_info)


def _interpret(feats: List[float], access_info: dict) -> List[str]:
    factors = []
    is_avf = feats[9] > 0.5
    qa_threshold = _QA_AVF_FAIL if is_avf else _QA_AVG_FAIL

    if not np.isnan(feats[0]) and feats[0] < qa_threshold:
        factors.append(f"Access flow {feats[0]:.0f} mL/min below {'AVF' if is_avf else 'AVG'} threshold ({qa_threshold:.0f})")
    if feats[1] < -30:
        factors.append(f"Declining flow trend ({feats[1]:.0f} mL/min per record)")
    if feats[4] > 10:
        factors.append(f"High recirculation {feats[4]:.1f}% (threshold 10%)")
    if not np.isnan(feats[7]) and feats[7] > 50:
        factors.append(f"Significant stenosis {feats[7]:.0f}%")
    if feats[10] > 0:
        factors.append(f"Prior thrombosis events ({int(feats[10])})")
    if feats[11] > 5:
        factors.append(f"Frequent cannulation difficulties ({feats[11]:.1f}% of sessions)")
    return factors


def _heuristic(feats: List[float], access_info: dict) -> Dict:
    is_avf = feats[9] > 0.5
    qa_threshold = _QA_AVF_FAIL if is_avf else _QA_AVG_FAIL
    score = 0

    if not np.isnan(feats[0]):
        if feats[0] < qa_threshold * 0.8:
            score += 40
        elif feats[0] < qa_threshold:
            score += 20

    if feats[1] < -30:
        score += 25
    elif feats[1] < -10:
        score += 10

    if feats[4] > 10:
        score += 20
    if not np.isnan(feats[7]) and feats[7] > 50:
        score += 15
    if feats[10] > 0:
        score += 10 * min(int(feats[10]), 3)

    score = min(score, 100)
    prob = score / 100.0
    risk_level = "High" if prob >= 0.50 else ("Moderate" if prob >= 0.25 else "Low")

    return {
        "available":       True,
        "probability_90d": round(prob, 3),
        "risk_level":      risk_level,
        "risk_factors":    _interpret(feats, access_info),
        "method":          "Heuristic (KDOQI thresholds — train model for ML prediction)",
        "model_trained":   False,
    }


def train_access_failure_model(db) -> Dict:
    """
    Train the access failure XGBoost model on all AccessSurveillanceRecord data.

    Requires ≥ 50 access failure events for a trained model.
    Each patient's surveillance records are labelled by whether an access failure
    event (av_fistula_failure / av_fistula_thrombosis) occurred within 90 days.
    """
    if not (_SK and _JOBLIB):
        return {"success": False, "error": "scikit-learn or joblib not installed."}

    try:
        from database import (
            SessionLocal, Patient, AccessSurveillanceRecord,
            PatientVascularAccess, SessionRecord, ClinicalEvent,
        )
    except ImportError as exc:
        return {"success": False, "error": f"DB import failed: {exc}"}

    _db = db
    patients = _db.query(Patient).filter(Patient.is_active == True).all()

    _FAILURE_EVENTS = {
        "av_fistula_failure", "av_fistula_thrombosis",
        "thrombosis", "av_fistula_revision",
    }

    X, y = [], []
    for p in patients:
        surveillance = (
            _db.query(AccessSurveillanceRecord)
            .filter(AccessSurveillanceRecord.patient_id == p.id)
            .order_by(AccessSurveillanceRecord.record_date.desc())
            .all()
        )
        if len(surveillance) < 2:
            continue

        # Access static info
        va = (
            _db.query(PatientVascularAccess)
            .filter(PatientVascularAccess.patient_id == p.id)
            .order_by(PatientVascularAccess.id.desc())
            .first()
        )
        thrombosis_count = (
            _db.query(ClinicalEvent)
            .filter(
                ClinicalEvent.patient_id == p.id,
                ClinicalEvent.event_type.in_(["thrombosis", "av_fistula_thrombosis"]),
            )
            .count()
        )
        access_info = {
            "access_type":      va.access_type if va else "avf",
            "creation_date":    va.creation_date if va else None,
            "thrombosis_count": thrombosis_count,
        }

        # Session stats
        total_sess   = _db.query(SessionRecord).filter(SessionRecord.patient_id == p.id).count()
        diff_count   = (
            _db.query(SessionRecord)
            .filter(SessionRecord.patient_id == p.id, SessionRecord.cannulation_difficulty == True)
            .count()
        )
        session_stats = {"total_sessions": total_sess, "cannulation_difficulty_count": diff_count}

        # For each surveillance record, label whether access failed within 90 days
        failure_dates = [
            e.event_date for e in
            _db.query(ClinicalEvent)
            .filter(
                ClinicalEvent.patient_id == p.id,
                ClinicalEvent.event_type.in_(list(_FAILURE_EVENTS)),
            )
            .all()
            if e.event_date is not None
        ]

        recs_dicts = [
            {
                "qa_ml_min":          r.qa_ml_min,
                "recirculation_pct":  r.recirculation_pct,
                "psv_cm_s":           getattr(r, "psv_cm_s", None),
                "ri":                 getattr(r, "ri", None),
                "stenosis_pct":       getattr(r, "stenosis_pct", None),
                "record_date":        r.record_date,
            }
            for r in surveillance
        ]

        for i, rec_dict in enumerate(recs_dicts):
            recs_window = recs_dicts[i:]   # this record + all older ones
            feats = build_feature_vector(recs_window, access_info, session_stats)
            rec_date = rec_dict.get("record_date")
            label = 0
            if rec_date and failure_dates:
                label = int(any(
                    0 <= (fd - rec_date).days <= 90
                    for fd in failure_dates
                    if isinstance(fd, date)
                ))
            X.append(feats)
            y.append(label)

    n_samples = len(y)
    n_events  = sum(y)
    if n_samples < 40 or n_events < 10:
        return {
            "success": False,
            "n_samples": n_samples,
            "n_events": n_events,
            "error": f"Insufficient data: {n_events} access failure events (need ≥ 10).",
        }

    X_arr = np.array(X, dtype=float)
    y_arr = np.array(y, dtype=int)
    n_folds = min(5, n_events)
    cv = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)

    if _XGB:
        base = Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("xgb", xgb.XGBClassifier(
                n_estimators=150, max_depth=4, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8,
                scale_pos_weight=(n_samples - n_events) / max(n_events, 1),
                eval_metric="logloss", random_state=42, verbosity=0,
            )),
        ])
    else:
        base = Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("sc",  StandardScaler()),
            ("lr",  LogisticRegression(class_weight="balanced", C=0.5, max_iter=1000)),
        ])

    model = CalibratedClassifierCV(base, cv=n_folds, method="isotonic" if n_samples >= 50 else "sigmoid")
    model.fit(X_arr, y_arr)

    from sklearn.model_selection import cross_val_predict
    cv_probs = cross_val_predict(model, X_arr, y_arr, cv=cv, method="predict_proba")
    cv_auc = round(float(roc_auc_score(y_arr, cv_probs[:, 1])), 3) if n_events >= 5 else None

    joblib.dump(model, _MODEL_PATH, compress=3)
    global _ACCESS_MODEL
    _ACCESS_MODEL = None

    meta = {
        "n_samples": n_samples, "n_events": n_events,
        "cv_auc": cv_auc, "feature_names": _FEATURE_NAMES,
        "algorithm": "XGBoost (calibrated)" if _XGB else "LogisticRegression (calibrated)",
    }
    with open(_META_PATH, "w") as f:
        json.dump(meta, f, indent=2)

    logger.info("Access failure model trained: n=%d events=%d cv_auc=%s", n_samples, n_events, cv_auc)
    return {"success": True, **meta}
