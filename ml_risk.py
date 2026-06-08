"""
ml_risk.py
==========
Deterioration Risk Model (logistic regression) and Mortality Risk Prediction
(XGBoost Xu et al. 2023) for hemodialysis patients.
"""
import hashlib
import math
import logging
import os
import json
import warnings
import time as _time
from datetime import datetime
from typing import List, Dict, Optional

import numpy as np

from database import MonthlyRecord, Patient, PatientFeatureSnapshot

try:
    import statsmodels.api as sm
    _STATSMODELS_AVAILABLE = True
except ImportError:
    _STATSMODELS_AVAILABLE = False

try:
    import pandas as pd
    _PANDAS_AVAILABLE = True
except ImportError:
    _PANDAS_AVAILABLE = False

try:
    import joblib
    _JOBLIB_AVAILABLE = True
except ImportError:
    _JOBLIB_AVAILABLE = False

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

from sqlalchemy.orm import Session, joinedload

from ml_trends import _month_to_ordinal

logger = logging.getLogger(__name__)

# ── Deterioration Risk ────────────────────────────────────────────────────────

# 12 features used for both training and inference — must stay in sync
DETERIORATION_FEATURE_NAMES = [
    "hb_alert",       # Binary: Hb < 10.0 g/dL
    "hb_value",       # Continuous: Hb g/dL (median-imputed when missing)
    "alb_alert",      # Binary: Albumin < 3.5 g/dL
    "alb_value",      # Continuous: Albumin g/dL (median-imputed when missing)
    "target_score",   # 0–10 KDOQI achievement score
    "epo_hypo_proxy", # Binary: sub-target Hb despite active ESA prescription
    "age",            # Integer: patient age in years
    "cad",            # Binary: coronary artery disease / IHD
    "chf",            # Binary: congestive heart failure
    "dm",             # Binary: any diabetes mellitus (type 1 or 2)
    "hosp_severity_score_90d", # Continuous: severity-weighted admission score (last 90d)
                               #   Life Threatening=3, Critical=2, Moderate=1, Routine=0
    "recent_infection_events", # Continuous: infection event count in last 90d
]

# Severity weights for hospitalization_severity field
_HOSP_SEVERITY_WEIGHTS: dict = {
    "Life Threatening": 3.0,
    "Critical":         2.0,
    "Moderate":         1.0,
    "Routine":          0.0,
}


def _admission_severity_score(adm: dict) -> float:
    """
    Compute a clinical acuity score for a single admission dict stored in
    hospitalization_details JSON.

    Base score comes from the severity dropdown:
      Life Threatening = 3.0 | Critical = 2.0 | Moderate = 1.0 | Routine = 0.0

    Bonuses from objective illness-severity indicators (capped to prevent one
    feature dominating the total):
      PCT ≥ 10 ng/mL  → +1.5  (severe sepsis / septic shock)
      PCT 2–10        → +0.75 (sepsis)
      PCT 0.5–2       → +0.25 (bacterial infection)
      Shock on admission      → +1.0
      Inotropes (per day)     → +0.5/day, max +1.5
      Mechanical ventilation  → +1.0/day, max +3.0
      Blood transfusion       → +0.3/unit, max +1.5

    Routine admissions always score 0.0 regardless of bonus fields — they
    should never contribute to the deterioration risk signal.
    """
    sev = adm.get("severity", "")
    base = _HOSP_SEVERITY_WEIGHTS.get(sev, 1.0) if sev else 1.0
    if base == 0.0:
        return 0.0  # Routine — ignore all other signals

    bonus = 0.0

    # Procalcitonin — sepsis severity proxy
    try:
        pct = float(adm.get("pct") or 0)
        if pct >= 10:
            bonus += 1.5
        elif pct >= 2:
            bonus += 0.75
        elif pct >= 0.5:
            bonus += 0.25
    except (TypeError, ValueError):
        pass

    # Shock on admission
    try:
        if int(adm.get("shock_on_admission") or 0):
            bonus += 1.0
    except (TypeError, ValueError):
        pass

    # Inotrope duration (days)
    try:
        inotrope_days = float(adm.get("inotrope_days") or 0)
        bonus += min(1.5, inotrope_days * 0.5)
    except (TypeError, ValueError):
        pass

    # Mechanical ventilation (days)
    try:
        vent_days = float(adm.get("ventilation_days") or 0)
        bonus += min(3.0, vent_days * 1.0)
    except (TypeError, ValueError):
        pass

    # Blood transfusion (units during admission)
    try:
        t_units = float(adm.get("transfusion_units") or 0)
        bonus += min(1.5, t_units * 0.3)
    except (TypeError, ValueError):
        pass

    return base + bonus


_MODEL_PATH      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deterioration_model.joblib")
_MODEL_META_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deterioration_model_meta.json")


def get_snapshot_feature_vector(db, patient_id: int, month_str: str) -> Optional[list]:
    """Return the cached feature vector from patient_feature_snapshot, or None if absent/stale.

    Calling code should fall back to live feature extraction when this returns None.
    The vector ordering matches _build_feature_vector:
      [hb_alert, hb, alb_alert, albumin, target_score, epo_hypo, age, cad, chf, dm_type,
       hosp_severity_score_90d, recent_infection_events]
    """
    snap = (
        db.query(PatientFeatureSnapshot)
        .filter(
            PatientFeatureSnapshot.patient_id == patient_id,
            PatientFeatureSnapshot.as_of_month == month_str,
            PatientFeatureSnapshot.stale == False,
        )
        .first()
    )
    if snap is None or not snap.feature_vector:
        return None
    fv = snap.feature_vector
    return [
        fv.get("hb_alert", 0),
        fv.get("hb", 10.0),
        fv.get("alb_alert", 0),
        fv.get("albumin", 3.5),
        fv.get("target_score", 5.0),
        fv.get("epo_hypo", 0),
        fv.get("age", 60),
        fv.get("cad", 0),
        fv.get("chf", 0),
        fv.get("dm_type", 0),
        fv.get("hosp_severity_score_90d", fv.get("num_recent_hospitalizations_90d", 0.0)),
        fv.get("recent_infection_events", 0.0),
    ]


def _build_feature_vector(
    hb_val, hb_alert,
    alb_val, alb_alert,
    target_score,
    epo_hypo,
    age, cad, chf, dm_status,
    hosp_severity_score_90d=0.0,
    recent_infection_events=0.0,
    is_training=False
) -> list:
    """
    Unified feature vector constructor.
    Ensures identical feature ordering and normalization for both training and inference.
    """
    # Imputation for inference path only
    if not is_training:
        hb_val                  = hb_val if hb_val is not None else 10.0
        alb_val                 = alb_val if alb_val is not None else 3.5
        target_score            = target_score if target_score is not None else 5.0
        hosp_severity_score_90d = hosp_severity_score_90d if hosp_severity_score_90d is not None else 0.0
        recent_infection_events = recent_infection_events if recent_infection_events is not None else 0.0

    return [
        float(hb_alert or 0),
        hb_val,
        float(alb_alert or 0),
        alb_val,
        float(target_score),
        float(epo_hypo or 0),
        float(age or 60),
        float(cad or 0),
        float(chf or 0),
        0.0 if str(dm_status or "").strip().lower() in ("", "none", "no", "0", "false", "n") else 1.0,
        float(hosp_severity_score_90d),
        float(recent_infection_events),
    ]


def _extract_record_features_for_training(record, patient, db: Session) -> list:
    """ORM path for training."""
    hb      = record.hb
    albumin = record.albumin

    # Standard KDOQI target score computation
    points, available = 0, 0
    for val, met in [
        (hb,               hb        is not None and hb        >= 10.0),
        (albumin,          albumin   is not None and albumin   >= 3.5),
        (record.phosphorus, record.phosphorus is not None and record.phosphorus <= 5.5),
        (record.idwg,       record.idwg       is not None and record.idwg       <= 2.5),
        (record.urr,        record.urr        is not None and record.urr        >= 65.0),
        (record.single_pool_ktv, record.single_pool_ktv is not None and record.single_pool_ktv >= 1.2),
    ]:
        if val is not None:
            available += 1
            if met: points += 1
    target_score = float(round(points / available * 10)) if available > 0 else 5.0

    epo_hypo = (hb is not None and hb < 10.0 and (record.epo_weekly_units is not None or bool(record.epo_mircera_dose)))

    # Compute timeline event features for training month (up to 90 days lookback)
    import calendar
    from datetime import date, timedelta
    
    month_str = record.record_month
    year = int(month_str[:4])
    month = int(month_str[5:7])
    last_day = calendar.monthrange(year, month)[1]
    end_date = date(year, month, last_day)
    start_date = end_date - timedelta(days=90)
    
    from database import MonthlyRecord as _MR, ClinicalEvent
    import json as _json

    # Severity-weighted hospitalization score from past MonthlyRecord rows (≤90d lookback).
    # Reads hospitalization_details JSON per admission; falls back to flat severity column
    # for older records that pre-date per-admission JSON, and to weight=1.0 for records
    # entered before the severity field existed (backward compatible).
    past_hosp_recs = (
        db.query(_MR)
        .filter(
            _MR.patient_id == patient.id,
            _MR.record_month < record.record_month,
            _MR.hospitalization_this_month == True,
        )
        .order_by(_MR.record_month.desc())
        .limit(3)
        .all()
    )
    hosp_severity_score_90d = 0.0
    for pr in past_hosp_recs:
        admissions = []
        if pr.hospitalization_details:
            try:
                admissions = _json.loads(pr.hospitalization_details)
            except Exception:
                pass
        if admissions:
            for adm in admissions:
                hosp_severity_score_90d += _admission_severity_score(adm)
        elif pr.hospitalization_severity:
            # Older record: flat column only, no per-admission JSON
            hosp_severity_score_90d += _HOSP_SEVERITY_WEIGHTS.get(pr.hospitalization_severity, 1.0)
        else:
            hosp_severity_score_90d += 1.0  # pre-severity data: treat as moderate weight

    inf_count = db.query(ClinicalEvent).filter(
        ClinicalEvent.patient_id == patient.id,
        (ClinicalEvent.event_type.like("%Infection%") | ClinicalEvent.event_type.in_(["Infection", "Sepsis / Bacteremia", "Catheter / Exit-Site Infection"])),
        ClinicalEvent.event_date >= start_date,
        ClinicalEvent.event_date <= end_date
    ).count()
    recent_infection_events = float(inf_count)

    return _build_feature_vector(
        hb_val                  = hb,
        hb_alert                = (hb is not None and hb < 10.0),
        alb_val                 = albumin,
        alb_alert               = (albumin is not None and albumin < 3.5),
        target_score            = target_score,
        epo_hypo                = epo_hypo,
        age                     = patient.age,
        cad                     = patient.cad_status,
        chf                     = patient.chf_status,
        dm_status               = patient.dm_status,
        hosp_severity_score_90d = hosp_severity_score_90d,
        recent_infection_events = recent_infection_events,
        is_training             = True
    )


def _extract_analytics_features_for_inference(
    hb: dict, alb: dict, target: dict,
    epo: dict = None, patient_info: dict = None,
    hosp_severity_score_90d=0.0,
    recent_infection_events=0.0,
) -> list:
    """Dict path for real-time inference."""
    epo          = epo or {}
    patient_info = patient_info or {}
    return _build_feature_vector(
        hb_val                  = hb.get("current"),
        hb_alert                = hb.get("alert"),
        alb_val                 = alb.get("current"),
        alb_alert               = alb.get("risk"),
        target_score            = target.get("score"),
        epo_hypo                = epo.get("hypo_response"),
        age                     = patient_info.get("age"),
        cad                     = patient_info.get("cad_status"),
        chf                     = patient_info.get("chf_status"),
        dm_status               = patient_info.get("dm_status"),
        hosp_severity_score_90d = hosp_severity_score_90d,
        recent_infection_events = recent_infection_events,
        is_training             = False
    )


_DETERIORATION_MODEL = None
_MODEL_LOAD_TIME = 0

def _restore_model_from_db() -> bool:
    """
    Restore deterioration_v1 model from ModelArtifact database binary if it exists.
    Writes the binary to _MODEL_PATH and metadata JSON to _MODEL_META_PATH.
    Returns True if successfully restored, False otherwise.
    """
    try:
        from database import SessionLocal, ModelArtifact
        db = SessionLocal()
        try:
            art = (
                db.query(ModelArtifact)
                .filter(ModelArtifact.model_name == "deterioration_v1")
                .filter(ModelArtifact.model_binary != None)
                .order_by(ModelArtifact.trained_at.desc())
                .first()
            )
            if art:
                # Ensure target directory exists
                os.makedirs(os.path.dirname(_MODEL_PATH), exist_ok=True)
                
                # Write model binary
                with open(_MODEL_PATH, "wb") as f:
                    f.write(art.model_binary)
                
                # Write model metadata JSON
                meta = {
                    "trained_at":          art.version,
                    "feature_names":       DETERIORATION_FEATURE_NAMES,
                    "training_data_hash":  art.training_data_hash,
                }
                # If metrics_json is present, parse and update
                if art.metrics_json:
                    try:
                        metrics = json.loads(art.metrics_json)
                        meta.update(metrics)
                    except:
                        pass
                
                with open(_MODEL_META_PATH, "w") as f:
                    json.dump(meta, f, indent=2)
                
                logger.info("Successfully restored deterioration_v1 model from DB.")
                return True
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Failed to restore deterioration_v1 model from DB: %s", exc)
    return False


def _load_deterioration_model():
    global _DETERIORATION_MODEL, _MODEL_LOAD_TIME

    if not os.path.exists(_MODEL_PATH):
        _restore_model_from_db()

    if os.path.exists(_MODEL_PATH):
        try:
            mtime = os.path.getmtime(_MODEL_PATH)
            # If already loaded and file hasn't changed, return cached
            if _DETERIORATION_MODEL is not None and mtime <= _MODEL_LOAD_TIME:
                return _DETERIORATION_MODEL

            _DETERIORATION_MODEL = joblib.load(_MODEL_PATH)
            _MODEL_LOAD_TIME = mtime
            return _DETERIORATION_MODEL
        except Exception as e:
            logger.warning("Failed to load deterioration model: %s", e)
            return None
    return None


def train_deterioration_model(db: Session) -> dict:
    """
    Train a calibrated logistic regression model to predict hospitalization in
    the next calendar month.
    """
    if not _SKLEARN_AVAILABLE:
        return {
            "success": False,
            "error": "scikit-learn is not installed. Run: pip install scikit-learn",
        }

    # ── 1. Build paired (features, label) dataset ─────────────────────────────
    patients = db.query(Patient).filter(Patient.is_active == True).all()
    X, y, skipped = [], [], 0

    for patient in patients:
        records = (
            db.query(MonthlyRecord)
            .filter(MonthlyRecord.patient_id == patient.id)
            .order_by(MonthlyRecord.record_month.asc())
            .all()
        )
        if len(records) < 2:
            skipped += 1
            continue

        for i in range(len(records) - 1):
            curr = records[i]
            nxt  = records[i + 1]

            # Skip pairs separated by > 2 months (data gap)
            try:
                gap = _month_to_ordinal(nxt.record_month) - _month_to_ordinal(curr.record_month)
                if gap > 2:
                    continue
            except Exception:
                continue

            feats = _extract_record_features_for_training(curr, patient, db)
            # A hospitalisation counts as a deterioration event only when it is
            # not a planned/routine admission (access procedures, day cases, etc.).
            # "Routine" severity is explicitly excluded so that 4 fistula
            # interventions do not outscore an ICU admission in the training label.
            nxt_hosp = (
                bool(nxt.hospitalization_this_month) or
                bool(nxt.hospitalization_diagnosis)  or
                bool(nxt.hospitalization_icd_code)
            )
            if nxt_hosp and nxt.hospitalization_severity == "Routine":
                nxt_hosp = False
            label = int(nxt_hosp)
            X.append(feats)
            y.append(label)

    n_samples  = len(y)
    n_events   = sum(y)
    event_rate = round(n_events / n_samples, 4) if n_samples > 0 else 0.0

    # ── Events-per-feature (EPF) guard ───────────────────────────────────────
    # Statistical rule: need ≥ 10 EPF for reliable logistic regression.
    # We relax to EPF_MIN=5 for small single-centre HD registries, but flag
    # anything below EPF=10 as having overfitting risk.
    N_FEATURES   = len(DETERIORATION_FEATURE_NAMES)   # 10
    EPF_MIN      = 5                                    # absolute minimum
    EPF_WARN     = 10                                   # below this → overfitting warning
    MIN_EVENTS   = N_FEATURES * EPF_MIN                 # 50
    MIN_SAMPLES  = max(MIN_EVENTS * 2, 40)              # need samples > 2× events

    if n_samples < MIN_SAMPLES:
        return {
            "success": False, "n_samples": n_samples, "n_events": n_events,
            "error": (
                f"Insufficient paired records: need ≥{MIN_SAMPLES} (have {n_samples}). "
                "Continue adding monthly records before training."
            ),
        }

    if n_events < MIN_EVENTS:
        return {
            "success": False, "n_samples": n_samples, "n_events": n_events,
            "events_needed": MIN_EVENTS,
            "epf_current": round(n_events / N_FEATURES, 1),
            "epf_minimum": EPF_MIN,
            "error": (
                f"Insufficient hospitalization events: {n_events} recorded, "
                f"need ≥{MIN_EVENTS} ({EPF_MIN} per feature × {N_FEATURES} features). "
                f"Currently at {round(n_events/N_FEATURES, 1)} events/feature. "
                f"Model will be heuristic fallback until more outcome data is collected."
            ),
        }

    # ── 2. Build pipeline ─────────────────────────────────────────────────────
    X_arr = np.array(X, dtype=float)
    y_arr = np.array(y, dtype=int)

    epf           = round(n_events / N_FEATURES, 1)
    overfitting_risk = epf < EPF_WARN   # below 10 EPF → flag

    # Use stronger regularization (lower C) when EPF is below warning threshold
    # to reduce overfitting on small event counts.
    c_reg = 0.3 if overfitting_risk else 0.5

    base = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler",  StandardScaler()),
        ("lr",      LogisticRegression(
            class_weight="balanced",
            C=c_reg,          # tighter regularization for small N
            solver="lbfgs",
            max_iter=1000,
        )),
    ])

    # ── 3. Cross-validated AUC ───────────────────────────────────────────────
    n_folds  = min(5, n_events)
    cv       = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)
    cv_probs = cross_val_predict(base, X_arr, y_arr, cv=cv, method="predict_proba")
    cv_auc   = round(float(roc_auc_score(y_arr, cv_probs[:, 1])), 3)

    # Raise AUC warning threshold to 0.60 (was 0.55) — below 0.60 is near-random
    auc_warning = cv_auc < 0.60 or overfitting_risk

    # ── 4. Fit final calibrated model on all data ─────────────────────────────
    cal_method = "isotonic" if n_samples >= 50 else "sigmoid"
    cal_model  = CalibratedClassifierCV(base, cv=n_folds, method=cal_method)
    cal_model.fit(X_arr, y_arr)

    # ── 5. Persist model + metadata ───────────────────────────────────────────
    joblib.dump(cal_model, _MODEL_PATH, compress=3)

    global _DETERIORATION_MODEL
    _DETERIORATION_MODEL = None

    trained_at_str = datetime.now().isoformat(timespec="seconds")

    # SHA-256 of the training matrix for reproducibility / audit
    training_data_hash = hashlib.sha256(
        json.dumps(X, sort_keys=True).encode()
    ).hexdigest()

    meta = {
        "trained_at":          trained_at_str,
        "n_samples":           n_samples,
        "n_events":            n_events,
        "event_rate":          event_rate,
        "events_per_feature":  epf,
        "overfitting_risk":    overfitting_risk,
        "regularization_C":    c_reg,
        "n_folds":             n_folds,
        "calibration_method":  cal_method,
        "cv_auc":              cv_auc,
        "auc_warning":         auc_warning,
        "feature_names":       DETERIORATION_FEATURE_NAMES,
        "skipped_patients":    skipped,
        "epf_minimum_used":    EPF_MIN,
        "epf_warning_level":   EPF_WARN,
        "training_data_hash":  training_data_hash,
        "data_quality_note": (
            f"EPF={epf:.1f} (need ≥{EPF_WARN} for reliable estimates). "
            + ("⚠ Overfitting risk — use for risk ranking only, not absolute probabilities." if overfitting_risk else "EPF adequate.")
        ),
    }
    with open(_MODEL_META_PATH, "w") as f:
        json.dump(meta, f, indent=2)

    # ── Register artifact in DB — inference is refused without this row ────────
    try:
        from database import SessionLocal, ModelArtifact
        _art_db = SessionLocal()
        try:
            model_bin_data = None
            if os.path.exists(_MODEL_PATH):
                with open(_MODEL_PATH, "rb") as f_bin:
                    model_bin_data = f_bin.read()
            art = ModelArtifact(
                model_name          = "deterioration_v1",
                version             = trained_at_str,
                trained_at          = datetime.fromisoformat(trained_at_str),
                training_data_hash  = training_data_hash,
                metrics_json        = json.dumps({
                    "cv_auc": cv_auc, "n_samples": n_samples,
                    "n_events": n_events, "epf": epf,
                    "calibration_method": cal_method,
                }),
                feature_schema_json = json.dumps(DETERIORATION_FEATURE_NAMES),
                artifact_path       = os.path.relpath(_MODEL_PATH),
                model_binary        = model_bin_data,
            )
            _art_db.add(art)
            _art_db.commit()
        finally:
            _art_db.close()
    except Exception as _art_exc:
        logger.warning("Failed to register ModelArtifact: %s", _art_exc)

    logger.info(
        "Deterioration model trained: n_samples=%d n_events=%d epf=%.1f cv_auc=%.3f cal=%s overfitting_risk=%s C=%.1f",
        n_samples, n_events, epf, cv_auc, cal_method, overfitting_risk, c_reg,
    )
    return {"success": True, **meta}


def get_deterioration_model_status() -> dict:
    """
    Return metadata about the trained deterioration model.
    Returns a 'not trained' sentinel when no model file exists.
    """
    # BUG 8 FIX: removed local `import json` — already imported at module level
    if not os.path.exists(_MODEL_PATH):
        return {
            "trained": False,
            "sklearn_available": _SKLEARN_AVAILABLE,
            "message": "No model trained yet. POST to /admin/train-deterioration-model to train.",
        }
    meta: dict = {}
    if os.path.exists(_MODEL_META_PATH):
        try:
            with open(_MODEL_META_PATH) as f:
                meta = json.load(f)
        except Exception:
            pass
    return {"trained": True, "sklearn_available": _SKLEARN_AVAILABLE, **meta}


# ── SHAP helper ───────────────────────────────────────────────────────────────

try:
    import shap as _shap
    _SHAP_AVAILABLE = True
except ImportError:
    _SHAP_AVAILABLE = False


def _compute_deterioration_shap(model, feats: list) -> Optional[list]:
    """Return a list of {feature, value, shap_value} dicts, sorted by |shap| desc.

    Uses LinearExplainer on the final estimator inside the calibration wrapper.
    Returns None when shap is unavailable or the pipeline shape doesn't match.
    """
    if not _SHAP_AVAILABLE:
        return None
    try:
        # CalibratedClassifierCV wraps a Pipeline; extract the underlying pipeline
        base_estimator = getattr(model, "estimators_", [model])[0]
        if hasattr(base_estimator, "named_steps"):
            preprocessor_steps = [s for name, s in base_estimator.named_steps.items()
                                   if name != "clf"]
            import numpy as _np
            x = _np.array([feats], dtype=float)
            for step in preprocessor_steps:
                x = step.transform(x)
            clf = base_estimator.named_steps.get("clf") or list(base_estimator.named_steps.values())[-1]
        else:
            import numpy as _np
            x = _np.array([feats], dtype=float)
            clf = base_estimator

        explainer = _shap.LinearExplainer(clf, _np.zeros_like(x))
        sv = explainer.shap_values(x)
        # sv shape: (1, n_features) for binary class positive label
        raw = sv[0] if sv.ndim == 2 else sv
        result = [
            {
                "feature": DETERIORATION_FEATURE_NAMES[i],
                "value": round(float(feats[i]), 4) if feats[i] is not None else None,
                "shap_value": round(float(raw[i]), 4),
            }
            for i in range(len(DETERIORATION_FEATURE_NAMES))
        ]
        result.sort(key=lambda r: abs(r["shap_value"]), reverse=True)
        return result[:10]
    except Exception as exc:
        logger.debug("SHAP computation skipped: %s", exc)
        return None


# ── MLOps prediction logger ───────────────────────────────────────────────────

def _log_deterioration_prediction(
    feats: list,
    prob: float,
    patient_id: Optional[int],
    model_version: Optional[str],
) -> None:
    """Fire-and-forget: write one MLPrediction row.  Never raises."""
    if patient_id is None:
        return
    try:
        from database import SessionLocal, MLPrediction
        feat_dict = {name: (feats[i] if feats[i] is not None else None)
                     for i, name in enumerate(DETERIORATION_FEATURE_NAMES)}
        feat_json = json.dumps(feat_dict, sort_keys=True)
        feat_hash = hashlib.sha256(feat_json.encode()).hexdigest()

        from datetime import datetime as _dt
        month_str = _dt.utcnow().strftime("%Y-%m")

        db = SessionLocal()
        try:
            from database import compute_patient_id_hash
            row = MLPrediction(
                patient_id=patient_id,
                patient_id_hash=compute_patient_id_hash(patient_id),
                model_name="deterioration_v1",
                model_version=model_version or "unknown",
                input_feature_hash=feat_hash,
                features_json=feat_json,
                prediction_score=round(prob, 6),
                predicted_class=int(prob >= 0.40),
                prediction_month=month_str,
            )
            db.add(row)
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.debug("MLPrediction log skipped: %s", exc)


def compute_deterioration_risk(
    hb: Dict, alb: Dict, target: Dict,
    epo: Dict = None, patient_info: Dict = None,
) -> Dict:
    """
    Estimate the probability of hospitalization in the next calendar month.
    """
    # ── Unpack standardized inputs ───────────────────────────────────────────
    hb_data     = hb.get("data", hb)
    alb_data    = alb.get("data", alb)
    target_data = target.get("data", target)
    epo_data    = (epo or {}).get("data", epo or {})

    # ── Derive human-readable risk factors (shared by both paths) ─────────────
    factors = []
    if hb_data.get("alert"):                         factors.append("Hb below 10 g/dL")
    if hb_data.get("alert_predicted_low"):           factors.append("Hb predicted to fall below 10 g/dL")
    if alb_data.get("risk"):                         factors.append("Albumin below 3.5 g/dL")
    if (epo_data or {}).get("hypo_response"):        factors.append("ESA hypo-response (high ERI)")
    if target_data.get("score", 10) < 6:             factors.append("Low KDOQI target score (<6/10)")
    if (patient_info or {}).get("cad_status"):  factors.append("Coronary artery disease")
    if (patient_info or {}).get("chf_status"):  factors.append("Congestive heart failure")

    model = _load_deterioration_model()

    # Refuse inference when no registered artifact exists — prevents an
    # unversioned or manually-dropped pkl from silently producing predictions.
    if model is not None:
        try:
            from database import SessionLocal as _SL, ModelArtifact as _MA
            _gate_db = _SL()
            try:
                _registered = _gate_db.query(_MA).filter(
                    _MA.model_name == "deterioration_v1"
                ).first()
            finally:
                _gate_db.close()
            if _registered is None:
                logger.warning(
                    "Deterioration model file exists but has no ModelArtifact registry row — "
                    "refusing inference. Re-train via POST /admin/train-deterioration-model."
                )
                model = None
        except Exception as _gate_exc:
            logger.debug("ModelArtifact gate check failed: %s", _gate_exc)

    if model is not None:
        patient_id = (patient_info or {}).get("id")
        hosp_severity_score_90d = 0.0
        recent_infection_events = 0.0

        if patient_id:
            from database import SessionLocal as _SL, MonthlyRecord as _MR2, ClinicalEvent as _CE
            from datetime import date, timedelta
            import json as _json2

            _ev_db = _SL()
            try:
                today = date.today()
                start_date = today - timedelta(days=90)
                # Current month string for upper bound (exclude present record)
                cur_month = today.strftime("%Y-%m")

                # Severity-weighted score from recent MonthlyRecord rows
                past_hosp = (
                    _ev_db.query(_MR2)
                    .filter(
                        _MR2.patient_id == patient_id,
                        _MR2.record_month < cur_month,
                        _MR2.hospitalization_this_month == True,
                    )
                    .order_by(_MR2.record_month.desc())
                    .limit(3)
                    .all()
                )
                for pr in past_hosp:
                    admissions = []
                    if pr.hospitalization_details:
                        try:
                            admissions = _json2.loads(pr.hospitalization_details)
                        except Exception:
                            pass
                    if admissions:
                        for adm in admissions:
                            hosp_severity_score_90d += _admission_severity_score(adm)
                    elif pr.hospitalization_severity:
                        hosp_severity_score_90d += _HOSP_SEVERITY_WEIGHTS.get(pr.hospitalization_severity, 1.0)
                    else:
                        hosp_severity_score_90d += 1.0

                inf_count = _ev_db.query(_CE).filter(
                    _CE.patient_id == patient_id,
                    (_CE.event_type.like("%Infection%") | _CE.event_type.in_(["Infection", "Sepsis / Bacteremia", "Catheter / Exit-Site Infection"])),
                    _CE.event_date >= start_date,
                    _CE.event_date <= today
                ).count()
                recent_infection_events = float(inf_count)
            except Exception as _q_exc:
                logger.debug("Failed to query event data for patient %s: %s", patient_id, _q_exc)
            finally:
                _ev_db.close()

        feats = _extract_analytics_features_for_inference(
            hb_data, alb_data, target_data, epo_data, patient_info,
            hosp_severity_score_90d=hosp_severity_score_90d,
            recent_infection_events=recent_infection_events
        )
        try:
            prob      = float(model.predict_proba(np.array([feats]))[0][1])
            risk_pct  = round(prob * 100, 1)
            risk_level = "High" if prob >= 0.40 else "Moderate" if prob >= 0.15 else "Low"

            # BUG 8 FIX: removed local `import json` — already at module level
            meta: dict = {}
            if os.path.exists(_MODEL_META_PATH):
                try:
                    with open(_MODEL_META_PATH) as _f:
                        meta = json.load(_f)
                except Exception:
                    pass

            missing = []
            if hb_data.get("current") is None: missing.append("Hemoglobin")
            if alb_data.get("current") is None: missing.append("Albumin")
            if target_data.get("score") is None: missing.append("Target Score (labs)")
            if (epo_data or {}).get("hypo_response") is None: missing.append("ESA Response")
            if (patient_info or {}).get("age") is None: missing.append("Age")
            if (patient_info or {}).get("cad_status") is None: missing.append("CAD Status")
            if (patient_info or {}).get("chf_status") is None: missing.append("CHF Status")
            if (patient_info or {}).get("dm_status") is None: missing.append("DM Status")

            # ── MLOps: log prediction ────────────────────────────────────────
            _log_deterioration_prediction(
                feats=feats,
                prob=prob,
                patient_id=(patient_info or {}).get("id"),
                model_version=meta.get("trained_at"),
            )

            # ── SHAP: compute per-prediction feature contributions ────────────
            shap_values = _compute_deterioration_shap(model, feats)

            return {
                "available": True,
                "error":     None,
                "data": {
                    "available":       True,
                    "method":          "LogisticRegression (calibrated)",
                    "risk_score":      risk_pct,
                    "score":           risk_pct,
                    "risk_probability": prob,
                    "risk_level":      risk_level,
                    "level":           risk_level,
                    "risk_factors":    factors,
                    "factors":         factors,
                    "inputs_missing":  missing,
                    "model_cv_auc":    meta.get("cv_auc"),
                    "model_n_samples": meta.get("n_samples"),
                    "model_trained_at": meta.get("trained_at"),
                    "auc_warning":     meta.get("auc_warning", False),
                    "shap_values":     shap_values,
                }
            }
        except Exception as e:
            logger.warning("Deterioration model predict_proba failed: %s — using heuristic", e)

    # ── Heuristic fallback (no trained model or prediction failed) ────────────
    risk_score = 0
    if hb_data.get("alert"):             risk_score += 40
    if alb_data.get("risk"):             risk_score += 30
    if target_data.get("score", 0) < 6:  risk_score += 30
    risk_level = "High" if risk_score >= 60 else "Moderate" if risk_score >= 30 else "Low"
    missing = []
    if hb_data.get("current") is None: missing.append("Hemoglobin")
    if alb_data.get("current") is None: missing.append("Albumin")
    if target_data.get("score") is None: missing.append("Target Score (labs)")

    return {
        "available": True,
        "error":     None,
        "data": {
            "available":   True,
            "method":      "Heuristic (no trained model — POST /admin/train-deterioration-model)",
            "risk_score":  risk_score,
            "score":       risk_score,
            "risk_level":  risk_level,
            "level":       risk_level,
            "risk_factors": factors,
            "factors":     factors,
            "inputs_missing": missing,
            "model_cv_auc":    None,
            "model_n_samples": None,
            "model_trained_at": None,
            "auc_warning":     False,
        }
    }


# ── Mortality Risk Prediction ─────────────────────────────────────────────────

# BUG 7 FIX: removed duplicate `import os as _os` and `import warnings as _warnings`

# ── Indian Population Re-calibration (Fix 3) ─────────────────────────────────

# Platt scaling parameters derived from literature comparison:
#   Xu et al. 2023 Chinese cohort: 1-yr mortality ~22-28%
#   DOPPS India Phase 5 (Pisoni et al. 2019): 1-yr HD mortality ~13-18%
#   Indian HD Registry (ISN data 2020): median 1-yr mortality 14.2%
#
# Logit-space linear recalibration: logit(p_cal) = SLOPE * logit(p_raw) + INTERCEPT
# These parameters shift the raw Chinese-cohort probabilities toward Indian baselines.
# MUST be replaced with cohort-fitted values once ≥50 outcome events are collected.
_INDIAN_CAL_SLOPE     = 0.72   # risk compression (Indian cohort lower baseline mortality)
_INDIAN_CAL_INTERCEPT = -0.40  # intercept shift (lower baseline log-odds)
_INDIAN_CAL_VALIDATED = False   # set True once local outcomes have fitted these params


def _indian_recalibrate(prob_raw: float, apply: bool = True) -> tuple:
    """
    Apply Indian HD population re-calibration to Xu et al. XGBoost output.

    Method: Platt scaling (logit-space linear transform)
      logit(p_cal) = SLOPE * logit(p_raw) + INTERCEPT

    Parameters are literature-approximated from DOPPS India Phase 5 and
    Indian HD Registry data. They should be replaced with locally fitted
    values once ≥50 mortality events are available in this cohort.

    Returns:
        (prob_calibrated, calibration_note)
    """
    if not apply:
        return prob_raw, "Indian recalibration not applied (rule-based fallback path)."

    try:
        logit_raw = math.log(max(0.001, prob_raw) / max(0.001, 1.0 - prob_raw))
        logit_cal = _INDIAN_CAL_SLOPE * logit_raw + _INDIAN_CAL_INTERCEPT
        prob_cal  = 1.0 / (1.0 + math.exp(-logit_cal))
        prob_cal  = round(max(0.001, min(0.999, prob_cal)), 3)

        note = (
            f"Ad-hoc literature-approximated Platt scaling (DOPPS India Phase 5 baseline ~14-18% 1-yr mortality). "
            f"Raw Xu et al. probability: {prob_raw*100:.1f}% → Indian-adjusted: {prob_cal*100:.1f}%. "
            f"⚠ This recalibration is manually approximated — replace with locally fitted parameters once ≥50 outcome events are collected."
        )
        return prob_cal, note
    except Exception:
        return prob_raw, "Indian recalibration failed — using raw XGBoost probability."


# Lazy-load models at first call (avoids import overhead at startup)
# None = load attempted but failed; {} = not yet attempted
_XGB_MODELS: dict = {}
_XGB_LOAD_ATTEMPTED: bool = False

_MANIFEST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "manifest.json")

# Drift thresholds keyed by the feature name used at inference time.
# Sourced from models/manifest.json — duplicated here so checks survive a
# missing manifest file.
_XGB_DRIFT_BOUNDS: dict = {
    "Age":       (18,   95),
    "Albumin":   (15.0, 55.0),   # g/L
    "N109L":     (0.5,  15.0),   # ×10⁹/L
    "EF":        (10,   80),
}


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_xgb_manifests(model_dir: str) -> None:
    """Log a warning for any pkl whose SHA-256 does not match manifest.json."""
    try:
        with open(_MANIFEST_PATH) as f:
            manifest = json.load(f)
    except Exception as e:
        logger.warning("models/manifest.json missing or unreadable — skipping integrity check: %s", e)
        return

    for key, entry in manifest.get("models", {}).items():
        path = os.path.join(model_dir, entry["file"])
        if not os.path.exists(path):
            logger.warning("Model file missing: %s", entry["file"])
            continue
        actual = _sha256_file(path)
        if actual != entry["sha256"]:
            logger.error(
                "INTEGRITY MISMATCH for %s: manifest=%s actual=%s — "
                "model may have been replaced or corrupted.",
                entry["file"], entry["sha256"][:12], actual[:12],
            )
        else:
            logger.debug("Integrity OK: %s", entry["file"])


def _check_xgb_feature_drift(age, albumin_gl, neutrophil, ef) -> list:
    """
    Return a list of human-readable drift warnings for features outside the
    Xu et al. 2023 training distribution.  Empty list = no drift detected.
    """
    warnings_out = []
    checks = [
        ("Age",     age,        "yr"),
        ("Albumin", albumin_gl, "g/L"),
        ("N109L",   neutrophil, "×10⁹/L"),
        ("EF",      ef,         "%"),
    ]
    for name, value, unit in checks:
        if value is None:
            continue
        lo, hi = _XGB_DRIFT_BOUNDS[name]
        if not (lo <= value <= hi):
            warnings_out.append(
                f"{name} {value} {unit} is outside Xu et al. training range "
                f"[{lo}–{hi} {unit}]; prediction may extrapolate."
            )
    return warnings_out


def _load_xgb_models() -> dict:
    """Load the three XGBoost PKL models once, verifying SHA-256 against manifest."""
    global _XGB_MODELS, _XGB_LOAD_ATTEMPTED
    if _XGB_LOAD_ATTEMPTED:
        return _XGB_MODELS  # already tried — return cached result (may be empty)
    _XGB_LOAD_ATTEMPTED = True
    try:
        model_dir = os.path.join(os.path.dirname(__file__), "models")
        _verify_xgb_manifests(model_dir)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _XGB_MODELS = {
                "1yr": joblib.load(os.path.join(model_dir, "Xgbc_clf_final_round_oneyearAI.pkl")),
                "4yr": joblib.load(os.path.join(model_dir, "Xgbc_clf_final_round.pkl")),
                "7yr": joblib.load(os.path.join(model_dir, "Xgbc_clf_final_round_sevenyearAI.pkl")),
            }
        logger.info("XGBoost mortality models loaded successfully.")
    except Exception as e:
        _XGB_MODELS = {}
        logger.warning(f"XGBoost models not loaded (rule-based fallback active): {e}")
    return _XGB_MODELS



def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-50.0, min(50.0, x))))


def _mortality_uncertainty_band(prob: float, n_core_features: int, model_type: str) -> dict:
    """
    Approximate uncertainty band around the XGBoost probability.
    NOT a statistically validated confidence interval.
    """
    if model_type in ("xgboost_full", "xgboost_imputed"):
        base_se = 0.05
        feature_gap = (5 - n_core_features) * 0.08
    else:
        log_odds = math.log(max(0.001, prob) / max(0.001, 1 - prob))
        base_se = 0.25
        feature_gap = (5 - n_core_features) * 0.30
        total_se = math.sqrt(base_se**2 + feature_gap**2)
        return {
            "uncertainty_lower": round(_sigmoid(log_odds - 1.96 * total_se), 3),
            "uncertainty_upper": round(_sigmoid(log_odds + 1.96 * total_se), 3),
            "ci_valid": False,
            "uncertainty_note": "Approximate range (rule-based fallback); not a validated confidence interval.",
        }

    total_se = math.sqrt(base_se**2 + feature_gap**2)
    p_lower = max(0.001, round(prob - 1.96 * total_se, 3))
    p_upper = min(0.999, round(prob + 1.96 * total_se, 3))
    return {
        "uncertainty_lower": p_lower,
        "uncertainty_upper": p_upper,
        "ci_valid": False,
        "uncertainty_note": (
            "Approximate range based on feature completeness. "
            "Model trained on Chinese HD cohort — absolute calibration not yet validated for Indian population. "
            "Use for risk ranking, not absolute prognosis."
        ),
    }


def _rule_based_log_odds_fallback(latest: dict, patient_info: dict) -> tuple:
    """
    Minimal rule-based fallback when XGBoost models are unavailable.
    Returns (log_odds, used_features, missing_features, n_core_used, contributions).
    contributions: list of {feature, value, delta, direction} for the explainer panel.
    """
    log_odds = -1.4
    used, missing, contributions = [], [], []
    n_core_used = 0

    def _contrib(feature: str, value: str, delta: float) -> None:
        contributions.append({
            "feature": feature,
            "value": value,
            "delta": round(delta, 2),
            "direction": "raises" if delta > 0 else ("lowers" if delta < 0 else "neutral"),
        })

    age = patient_info.get("age")
    if age is not None:
        if   age >= 80: d = 1.5
        elif age >= 70: d = 1.1
        elif age >= 60: d = 0.7
        elif age >= 50: d = 0.3
        else:           d = 0.0
        log_odds += d
        used.append(f"Age {age}yr"); n_core_used += 1
        _contrib("Age", f"{age} yr", d)
    else:
        missing.append("Age")

    albumin_gdl = latest.get("albumin")
    if albumin_gdl is not None:
        alb_gl = albumin_gdl * 10.0
        if   alb_gl >= 40.0: d = -0.30
        elif alb_gl >= 35.0: d =  0.00
        elif alb_gl >= 30.0: d =  0.60
        else:                d =  1.20
        log_odds += d
        used.append(f"Albumin {albumin_gdl:.1f} g/dL"); n_core_used += 1
        _contrib("Albumin", f"{albumin_gdl:.1f} g/dL", d)
    else:
        missing.append("Albumin")

    wbc = latest.get("wbc_count")
    if wbc is not None:
        n_est = wbc * 0.65
        if   n_est > 10.0: d = 1.10
        elif n_est >  7.5: d = 0.70
        elif n_est >  4.5: d = 0.20
        else:              d = 0.0
        log_odds += d
        used.append(f"Neutrophil (est.) {n_est:.1f}"); n_core_used += 1
        _contrib("Neutrophil (est.)", f"{n_est:.1f} ×10⁹/L", d)
    else:
        crp = latest.get("crp")
        if crp and crp > 10:
            log_odds += 0.50
            used.append(f"CRP {crp:.1f} mg/L (proxy)")
            _contrib("CRP (inflammation proxy)", f"{crp:.1f} mg/L", 0.50)
        else:
            missing.append("Neutrophil / WBC")

    ef = patient_info.get("ef")
    if ef is not None:
        if   ef < 30: d = 1.40
        elif ef < 40: d = 0.90
        elif ef < 50: d = 0.50
        elif ef < 60: d = 0.20
        else:         d = 0.0
        log_odds += d
        used.append(f"EF {ef}%"); n_core_used += 1
        _contrib("Ejection Fraction", f"{ef}%", d)
    else:
        if patient_info.get("chf_status"):
            log_odds += 0.75
            used.append("CHF (EF proxy)")
            _contrib("CHF (EF proxy — no echo)", "CHF present", 0.75)
        else:
            missing.append("EF (echo not recorded)")

    cad = patient_info.get("cad_status")
    if cad is not None:
        d = 0.65 if cad else 0.0
        log_odds += d
        if cad: used.append("IHD/CAD present")
        else:   used.append("No IHD/CAD")
        n_core_used += 1
        _contrib("IHD / CAD", "Present" if cad else "Absent", d)
    else:
        missing.append("IHD/CAD status")

    return log_odds, used, missing, n_core_used, contributions


def predict_mortality_risk_batch(batch_inputs: List[Dict]) -> Dict[any, Dict]:
    """
    Compute XGBoost predictions in batches to avoid loop-based inference overhead.
    Each item in batch_inputs is a dict:
        {
            "id": patient_id,
            "age": int,
            "albumin_gl": float,
            "neutrophil": float,
            "ef": float,
            "cad": bool,
            "n_core_used": int
        }
    """
    if not _PANDAS_AVAILABLE:
        return {}

    models = _load_xgb_models()
    if not models or not batch_inputs:
        return {}

    rows_data = []
    patient_ids = []
    model_types = []

    MEDIANS = {"age": 62, "albumin_gl": 37.0, "neutrophil": 5.5, "ef": 60, "idh": 0}

    for item in batch_inputs:
        pid = item["id"]
        age = item["age"]
        albumin_gl = item["albumin_gl"]
        neutrophil = item["neutrophil"]
        ef = item["ef"]
        cad = item["cad"]
        n_core_used = item["n_core_used"]

        age_x = age if age is not None else MEDIANS["age"]
        albumin_x = albumin_gl if albumin_gl is not None else MEDIANS["albumin_gl"]
        neut_x = neutrophil if neutrophil is not None else MEDIANS["neutrophil"]
        ef_x = ef if ef is not None else MEDIANS["ef"]
        idh_x = (1 if cad else 0) if cad is not None else MEDIANS["idh"]

        rows_data.append([idh_x, age_x, albumin_x, neut_x, ef_x])
        patient_ids.append(pid)
        model_types.append("xgboost_full" if n_core_used == 5 else "xgboost_imputed")

    try:
        x = pd.DataFrame(
            rows_data,
            columns=["IDH", "Age", "Albumin", "N109L", "EF"]
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            prob_1yr_all = models["1yr"].predict_proba(x)[:, 1]
            prob_4yr_all = models["4yr"].predict_proba(x)[:, 1]
            prob_7yr_all = models["7yr"].predict_proba(x)[:, 1]
    except Exception as e:
        logger.warning(f"Batch XGBoost prediction failed: {e}")
        return {}

    results = {}
    for idx, pid in enumerate(patient_ids):
        results[pid] = {
            "prob_1yr": round(float(prob_1yr_all[idx]), 3),
            "prob_4yr": round(float(prob_4yr_all[idx]), 3),
            "prob_7yr": round(float(prob_7yr_all[idx]), 3),
            "model_type": model_types[idx]
        }
    return results


def predict_mortality_risk(df: List[Dict], patient_info: dict = None, _precomputed: dict = None) -> Dict:
    """
    Estimate 1-year, 4-year, and 7-year mortality probability for a HD patient.

    Primary engine: Xu et al. 2023 XGBoost model (AUC 0.979 on Chinese cohort).
    Fallback engine: Rule-based log-odds (used when XGBoost unavailable or
    when fewer than 2 core features are present).
    """
    if patient_info is None:
        patient_info = {}

    latest = df[0] if df else {}

    # ── Extract the 5 XGBoost features ──────────────────────────────────────
    age          = patient_info.get("age")
    albumin_gdl  = latest.get("albumin")
    wbc          = latest.get("wbc_count")
    ef_raw       = patient_info.get("ef")
    cad          = patient_info.get("cad_status")

    # Albumin: convert g/dL → g/L (model trained in g/L)
    albumin_gl = round(albumin_gdl * 10.0, 1) if albumin_gdl is not None else None

    # Neutrophil: direct count preferred; estimate from WBC if not available
    neutrophil = latest.get("neutrophil_count")
    if neutrophil is None and wbc is not None:
        neutrophil = round(wbc * 0.65, 2)
    neut_source = "direct" if latest.get("neutrophil_count") else "estimated from WBC"

    ef = ef_raw
    # IHD in Xu et al. 2023 = Ischemic Heart Disease = CAD binary flag
    idh = 1 if cad else 0

    core_present = {
        "Age":        age is not None,
        "Albumin":    albumin_gl is not None,
        "Neutrophil": neutrophil is not None,
        "EF":         ef is not None,
        "IDH/CAD":    cad is not None,
    }
    n_core_used = sum(core_present.values())
    missing = [k for k, v in core_present.items() if not v]
    used = []

    # ── Insufficient data guard ──────────────────────────────────────────────
    if n_core_used < 2:
        return {
            "available": False,
            "error":     "Insufficient core features (need ≥2).",
            "data": {
                "available": False,
                "reason": (
                    "Insufficient core features (need ≥2 of: Age, Albumin, "
                    "Neutrophil/WBC, EF, CAD status)"
                ),
            }
        }

    if age is None:
        return {
            "available": False,
            "error":     "Patient age missing.",
            "data": {
                "available": False,
                "reason": "Patient age not entered. Age is the most influential feature in this model — imputing it can swing the result by 90+ percentage points. Enter the patient's age in the profile to enable mortality prediction.",
            }
        }

    if not (1 <= age <= 115):
        logger.warning("Implausible age %s stored for patient — mortality prediction suppressed.", age)
        return {
            "available": False,
            "error":     f"Patient age {age} is outside the valid range [1–115].",
            "data": {
                "available": False,
                "reason": (
                    f"Age {age} is biologically implausible and was likely entered in error. "
                    "Correct the patient's age in the profile to enable mortality prediction."
                ),
            }
        }

    # ── Attempt XGBoost prediction ───────────────────────────────────────────
    models = _load_xgb_models()
    model_type = "unknown"
    prob_1yr = prob_4yr = prob_7yr = None

    if _precomputed is not None and "prob_1yr" in _precomputed:
        prob_1yr = _precomputed["prob_1yr"]
        prob_4yr = _precomputed["prob_4yr"]
        prob_7yr = _precomputed["prob_7yr"]
        model_type = _precomputed["model_type"]
        if model_type == "xgboost_full":
            used = [
                f"Age {age}yr",
                f"Albumin {albumin_gdl:.1f} g/dL ({albumin_gl} g/L)" if albumin_gdl is not None else f"Albumin {albumin_gl} g/L",
                f"Neutrophil {neutrophil:.2f} ×10⁹/L ({neut_source})" if neutrophil is not None else "",
                f"EF {ef}%" if ef is not None else "",
                f"IHD/CAD {'yes' if cad else 'no'}",
            ]
            used = [u for u in used if u]
        elif model_type == "xgboost_imputed":
            MEDIANS = {"age": 62, "albumin_gl": 37.0, "neutrophil": 5.5, "ef": 60, "idh": 0}
            imputed = []
            if age is None:        imputed.append(f"Age (imputed median {MEDIANS['age']}yr)")
            if albumin_gl is None: imputed.append(f"Albumin (imputed median {MEDIANS['albumin_gl']} g/L)")
            if neutrophil is None: imputed.append(f"Neutrophil (imputed median {MEDIANS['neutrophil']})")
            if ef is None:         imputed.append(f"EF (imputed median {MEDIANS['ef']}%)")
            if cad is None:        imputed.append("IHD/CAD (imputed 0 — comorbidity not recorded)")
            
            for k, v in core_present.items():
                if v:
                    if k == "Age": used.append(f"Age {age}yr")
                    elif k == "Albumin": used.append(f"Albumin {albumin_gdl:.1f} g/dL" if albumin_gdl is not None else f"Albumin {albumin_gl} g/L")
                    elif k == "Neutrophil": used.append(f"Neutrophil {neutrophil:.2f} ×10⁹/L ({neut_source})")
                    elif k == "EF": used.append(f"EF {ef}%")
                    elif k == "IDH/CAD": used.append(f"IHD/CAD {'yes' if cad else 'no'}")
            used += [f"⚠ {i}" for i in imputed]
    else:
        if models and all(f is not None for f in [age, albumin_gl, neutrophil, ef, cad]):
            try:
                x = pd.DataFrame(
                    [[idh, age, albumin_gl, neutrophil, ef]],
                    columns=["IDH", "Age", "Albumin", "N109L", "EF"]
                )
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    prob_1yr = round(float(models["1yr"].predict_proba(x)[0, 1]), 3)
                    prob_4yr = round(float(models["4yr"].predict_proba(x)[0, 1]), 3)
                    prob_7yr = round(float(models["7yr"].predict_proba(x)[0, 1]), 3)
                model_type = "xgboost_full"
                used = [
                    f"Age {age}yr",
                    f"Albumin {albumin_gdl:.1f} g/dL ({albumin_gl} g/L)",
                    f"Neutrophil {neutrophil:.2f} ×10⁹/L ({neut_source})",
                    f"EF {ef}%",
                    f"IHD/CAD {'yes' if cad else 'no'}",
                ]
            except Exception as e:
                logger.warning(f"XGBoost prediction failed: {e}. Falling back.")
                models = {}

        if prob_1yr is None and models and n_core_used >= 2:
            # Partial features available → impute missing with population medians
            # IDH median = 0.0 (most patients have no/rare hypotension episodes)
            MEDIANS = {"age": 62, "albumin_gl": 37.0, "neutrophil": 5.5, "ef": 60, "idh": 0}
            age_x      = age if age is not None else MEDIANS["age"]
            albumin_x  = albumin_gl if albumin_gl is not None else MEDIANS["albumin_gl"]
            neut_x     = neutrophil if neutrophil is not None else MEDIANS["neutrophil"]
            ef_x       = ef if ef is not None else MEDIANS["ef"]
            idh_x      = idh if cad is not None else MEDIANS["idh"]

            imputed = []
            if age is None:        imputed.append(f"Age (imputed median {MEDIANS['age']}yr)")
            if albumin_gl is None: imputed.append(f"Albumin (imputed median {MEDIANS['albumin_gl']} g/L)")
            if neutrophil is None: imputed.append(f"Neutrophil (imputed median {MEDIANS['neutrophil']})")
            if ef is None:         imputed.append(f"EF (imputed median {MEDIANS['ef']}%)")
            if cad is None:        imputed.append("IHD/CAD (imputed 0 — comorbidity not recorded)")

            try:
                x = pd.DataFrame(
                    [[idh_x, age_x, albumin_x, neut_x, ef_x]],
                    columns=["IDH", "Age", "Albumin", "N109L", "EF"]
                )
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    prob_1yr = round(float(models["1yr"].predict_proba(x)[0, 1]), 3)
                    prob_4yr = round(float(models["4yr"].predict_proba(x)[0, 1]), 3)
                    prob_7yr = round(float(models["7yr"].predict_proba(x)[0, 1]), 3)
                model_type = "xgboost_imputed"
                for k, v in core_present.items():
                    if v:
                        if k == "Age": used.append(f"Age {age}yr")
                        elif k == "Albumin": used.append(f"Albumin {albumin_gdl:.1f} g/dL")
                        elif k == "Neutrophil": used.append(f"Neutrophil {neutrophil:.2f} ×10⁹/L ({neut_source})")
                        elif k == "EF": used.append(f"EF {ef}%")
                        elif k == "IDH/CAD": used.append(f"IHD/CAD {'yes' if cad else 'no'}")
                used += [f"⚠ {i}" for i in imputed]
            except Exception as e:
                logger.warning(f"XGBoost imputed prediction failed: {e}. Using rule-based fallback.")
                models = {}

    rule_based_contributions: list = []
    if prob_1yr is None:
        # Full fallback: rule-based log-odds
        log_odds, used, missing, n_core_used, rule_based_contributions = _rule_based_log_odds_fallback(latest, patient_info)
        prob_1yr = round(_sigmoid(log_odds), 3)
        prob_4yr = round(min(0.97, 1 - (1 - prob_1yr) ** 3.5), 3)
        prob_7yr = round(min(0.99, 1 - (1 - prob_1yr) ** 6.5), 3)
        model_type = "rule_based_log_odds"

    # ── Indian Population Re-calibration (Fix 3) ─────────────────────────────
    # Apply only for XGBoost paths (model was trained on Chinese cohort).
    # Rule-based fallback already uses Indian-appropriate log-odds priors.
    _apply_recal = model_type in ("xgboost_full", "xgboost_imputed")
    prob_1yr_raw = prob_1yr   # preserve raw Chinese-cohort estimate for reference
    prob_1yr, _indian_cal_note = _indian_recalibrate(prob_1yr, apply=_apply_recal)
    # Scale 4yr/7yr proportionally (maintain relative risk ordering)
    if _apply_recal and prob_1yr_raw > 0:
        _scale = prob_1yr / prob_1yr_raw
        prob_4yr = round(min(0.999, prob_4yr * _scale), 3)
        prob_7yr = round(min(0.999, prob_7yr * _scale), 3)

    # ── Risk level classification ────────────────────────────────────────────
    if prob_1yr >= 0.65:
        risk_level, css_class = "Very High", "danger"
    elif prob_1yr >= 0.439:
        risk_level, css_class = "High", "danger"
    elif prob_1yr >= 0.20:
        risk_level, css_class = "Moderate", "warning"
    else:
        risk_level, css_class = "Low", "success"

    # ── Confidence tier ──────────────────────────────────────────────────────
    if model_type == "xgboost_full":
        data_completeness = "high" if n_core_used == 5 else "moderate"
    elif model_type == "xgboost_imputed":
        data_completeness = "moderate" if n_core_used >= 3 else "low"
    else:
        data_completeness = "low"

    # ── Uncertainty band ─────────────────────────────────────────────────────
    ub = _mortality_uncertainty_band(prob_1yr, n_core_used, model_type)

    # ── Human-readable message ───────────────────────────────────────────────
    model_label = {
        "xgboost_full":    "XGBoost model (all 5 features)",
        "xgboost_imputed": f"XGBoost model ({n_core_used}/5 features; {5-n_core_used} imputed from population median)",
        "rule_based_log_odds": "Rule-based log-odds (XGBoost unavailable or insufficient data)",
    }.get(model_type, model_type)

    if risk_level == "Very High":
        message = (
            f"Very High 1-year mortality risk ({prob_1yr*100:.0f}%). "
            "Urgent multidisciplinary review — consider palliative care discussion."
        )
    elif risk_level == "High":
        message = (
            f"High 1-year mortality risk ({prob_1yr*100:.0f}%). "
            "Optimise modifiable factors: anaemia, nutrition, cardiac status."
        )
    elif risk_level == "Moderate":
        message = (
            f"Moderate 1-year mortality risk ({prob_1yr*100:.0f}%). "
            "Monitor trends; address any deteriorating parameters promptly."
        )
    else:
        message = (
            f"Low 1-year mortality risk ({prob_1yr*100:.0f}%). "
            "Continue standard HD monitoring and KDOQI targets."
        )

    if missing:
        message += f" ({len(missing)} feature(s) missing — {data_completeness} data completeness.)"
    if "imputed" in model_type:
        message += " ⚠ Some features imputed from population median."

    # Acute Hb override
    _current_hb = latest.get("hb")
    if _current_hb is not None and _current_hb < 7.0:
        acute_hb_warning = (
            f"ACUTE RISK OVERLAY: Current Hb {_current_hb} g/dL is life-threatening. "
            f"This chronic-disease model does not include Hb as a feature — "
            f"near-term mortality risk is likely significantly higher than the figure above. "
            f"Urgent clinical review and likely transfusion required."
        )
        acute_hb_severity = "critical"
    elif _current_hb is not None and _current_hb < 9.0:
        acute_hb_warning = (
            f"Hb {_current_hb} g/dL is below target. The chronic-disease model does not "
            f"include Hb as a feature — anaemia management should be optimised alongside "
            f"mortality risk monitoring."
        )
        acute_hb_severity = "low"
    else:
        acute_hb_warning = None
        acute_hb_severity = None

    # ── Feature drift check ──────────────────────────────────────────────────
    drift_warnings = _check_xgb_feature_drift(age, albumin_gl, neutrophil, ef)
    if drift_warnings:
        logger.warning("XGBoost input drift detected: %s", "; ".join(drift_warnings))

    return {
        "available":          True,
        "error":              None,
        "data": {
            "available":          True,
            "prob_1yr":           prob_1yr,
            "prob_4yr":           prob_4yr,
            "prob_7yr":           prob_7yr,
            "prob_4yr_note":      "Xu et al. 4-year XGBoost model (AUC 0.933). Indian population calibration pending.",
            "prob_7yr_note":      "Xu et al. 7-year XGBoost model (AUC 0.935). Indian population calibration pending.",
            "uncertainty_lower":  ub["uncertainty_lower"],
            "uncertainty_upper":  ub["uncertainty_upper"],
            "ci_valid":           False,
            "uncertainty_note":   ub["uncertainty_note"],
            "model_type":         model_type,
            "model_label":        model_label,
            "risk_level":         risk_level,
            "class":              css_class,
            "data_completeness":  data_completeness,
            "model_calibration_status": "ad-hoc literature-approximated (non-validated)",
            "n_core_used":        n_core_used,
            "features_used":      used,
            "features_missing":   missing,
            "inputs_missing":     missing,
            "message":            message,
            "high_risk_threshold": 0.439,
            "above_threshold":    prob_1yr >= 0.439,
            "threshold_validation": "Chinese cohort only",
            "acute_hb_warning":   acute_hb_warning,
            "acute_hb_severity":  acute_hb_severity,
            "rule_based_contributions": rule_based_contributions,
            # ── Drift detection ───────────────────────────────────────────────
            "drift_warnings":     drift_warnings,
            "drift_detected":     bool(drift_warnings),
            # ── Indian population calibration fields ──────────────────────────
            "prob_1yr_raw_chinese": prob_1yr_raw if _apply_recal else None,
            "indian_recalibrated":  _apply_recal,
            "indian_cal_note":      _indian_cal_note,
            "indian_cal_validated": _INDIAN_CAL_VALIDATED,
            "indian_pop_note":    (
                "Xu et al. 2023 model trained on Chinese HD cohort (n~900). "
                "Re-calibrated for Indian HD population using DOPPS India Phase 5 "
                "baseline mortality (14-18%/yr). Risk direction is valid; "
                "replace calibration with local cohort data once ≥50 outcome events collected."
            ),
        }
    }


def compute_davies_score(patient_info: dict, latest_record: dict = None) -> dict:
    """
    Compute the Davies comorbidity score for a hemodialysis patient.
    """
    score = 0
    components = []
    inputs_missing = []
    n_missing = 0

    age = patient_info.get("age")
    if age is None:
        n_missing += 1
        inputs_missing.append("Age")
    elif age > 75:
        score += 2
        components.append("Age > 75 (+2)")

    cad = patient_info.get("cad_status")
    if cad is None:
        n_missing += 1
        inputs_missing.append("CAD Status")
    elif cad:
        score += 2
        components.append("IHD/CAD (+2)")

    pvd = patient_info.get("history_of_pvd")
    if pvd is None:
        n_missing += 1
        inputs_missing.append("PVD Status")
    elif pvd:
        score += 1
        components.append("PVD (+1)")

    dm_eo = patient_info.get("dm_end_organ_damage")
    if dm_eo is None:
        n_missing += 1
        inputs_missing.append("DM End-Organ Damage")
    elif dm_eo:
        score += 2
        components.append("DM + end-organ damage (+2)")

    neoplasia = False
    solid = patient_info.get("solid_tumor")
    leuk  = patient_info.get("leukemia")
    lymph = patient_info.get("lymphoma")
    if solid and solid.lower() not in ("none", "no", ""):
        neoplasia = True
    if leuk:
        neoplasia = True
    if lymph:
        neoplasia = True
    if neoplasia:
        score += 3
        components.append("Active neoplasia (+3)")


    if score <= 1:
        risk_group = "Low"
        approx_1yr = 0.05
        css_class = "success"
    elif score <= 3:
        risk_group = "Medium"
        approx_1yr = 0.18
        css_class = "warning"
    else:
        risk_group = "High"
        approx_1yr = 0.47
        css_class = "danger"

    return {
        "available":          True,
        "score":              score,
        "risk_group":         risk_group,
        "approx_1yr":         approx_1yr,
        "css_class":          css_class,
        "components":         components,
        "n_missing":          n_missing,
        "inputs_missing":     inputs_missing,
        "note":               "Davies comorbidity score (Wright & Jones 1999). Mortality estimates from UK Renal Registry validation.",
    }


_ML_PER_PATIENT_CACHE: dict = {}  # patient_id -> (result_dict_without_patient, expiry_ts)
_ML_CACHE_TTL = 600  # 10 minutes — monthly data changes infrequently; reduces cold-start frequency

# Whole-function result cache (patient_id -> risk_dict, no ORM objects).
# On cache hit, only the Patient objects are re-fetched (1 fast query).
_ML_FULL_CACHE: dict = {"ts": 0.0, "rows": None}


def get_all_patients_mortality_risk(db: Session) -> List[Dict]:
    """
    Compute mortality risk for all active patients.

    PERF: Batch-loads all MonthlyRecords in 2 queries (patients + records)
    instead of 1+N queries. Records are sorted and sliced in Python.
    Per-patient ML results (Bayesian + SHAP) cached for 2 min to avoid
    recomputing expensive inference on every request.
    On whole-function cache hit: only 1 DB query (patients) instead of 3+N.
    """
    # Whole-function cache hit: skip all batch queries and ML computation
    if _time.time() - _ML_FULL_CACHE["ts"] < _ML_CACHE_TTL and _ML_FULL_CACHE["rows"] is not None:
        patients = (
            db.query(Patient)
            .options(
                joinedload(Patient.comorbidity_profile),
                joinedload(Patient.cardiac),
            )
            .filter(
                Patient.is_active == True,
            )
            .order_by(Patient.name).all()
        )
        pid_to_patient = {p.id: p for p in patients}
        return [
            {"patient": pid_to_patient[pid], **risk_dict}
            for pid, risk_dict in _ML_FULL_CACHE["rows"]
            if pid in pid_to_patient
        ]

    patients = (
        db.query(Patient)
        .options(
            joinedload(Patient.comorbidity_profile),
            joinedload(Patient.cardiac),
        )
        .filter(
            Patient.is_active == True,
        )
        .order_by(Patient.name).all()
    )
    if not patients:
        return []

    pid_list = [p.id for p in patients]

    # ── Batch load last 6 months of records for all patients in one query ─────
    all_records = (
        db.query(MonthlyRecord)
        .filter(MonthlyRecord.patient_id.in_(pid_list))
        .order_by(MonthlyRecord.patient_id, MonthlyRecord.record_month.desc())
        .all()
    )

    # Group by patient_id, keeping only the 6 most-recent per patient
    from collections import defaultdict
    records_by_pid: dict = defaultdict(list)
    for rec in all_records:
        if len(records_by_pid[rec.patient_id]) < 6:
            records_by_pid[rec.patient_id].append(rec)

    patient_map = {p.id: p for p in patients}

    # Batch-load current-month feature snapshots so we can (a) skip re-extraction
    # for the deterioration model when a fresh snapshot is available, and (b) expose
    # feature_hash on every row for the clinician audit view.
    from dashboard_logic import get_current_month_str as _cur_month
    _snap_month = _cur_month()
    _snapshots = (
        db.query(PatientFeatureSnapshot)
        .filter(
            PatientFeatureSnapshot.patient_id.in_(pid_list),
            PatientFeatureSnapshot.as_of_month == _snap_month,
            PatientFeatureSnapshot.stale == False,
        )
        .all()
    )
    _snap_by_pid: dict = {s.patient_id: s for s in _snapshots}

    from bayesian_analytics import compute_bayesian_alert_profile, attach_bayesian_signal

    # Hoist outside the loop — each call does os.path.exists + os.path.getmtime syscalls
    det_model = _load_deterioration_model()

    now_ts = _time.time()

    # Batch extraction and prediction for active XGBoost patients whose cache has expired or is missing
    patients_to_predict = []
    for p in patients:
        _cached_entry = _ML_PER_PATIENT_CACHE.get(p.id)
        if _cached_entry and now_ts < _cached_entry[1]:
            continue
        records = records_by_pid.get(p.id, [])
        if not records:
            continue
        latest = records[0]
        age = p.age
        albumin_gdl = latest.albumin
        wbc = latest.wbc_count
        ef = p.ejection_fraction
        cad = p.cad_status

        albumin_gl = round(albumin_gdl * 10.0, 1) if albumin_gdl is not None else None

        neutrophil = latest.neutrophil_count
        if neutrophil is None and wbc is not None:
            neutrophil = round(wbc * 0.65, 2)

        core_present = {
            "Age":        age is not None,
            "Albumin":    albumin_gl is not None,
            "Neutrophil": neutrophil is not None,
            "EF":         ef is not None,
            "IDH/CAD":    cad is not None,
        }
        n_core_used = sum(core_present.values())

        if age is not None and (1 <= age <= 115) and n_core_used >= 2:
            patients_to_predict.append({
                "id": p.id,
                "age": age,
                "albumin_gl": albumin_gl,
                "neutrophil": neutrophil,
                "ef": ef,
                "cad": cad,
                "n_core_used": n_core_used,
            })

    precomputed_results = {}
    if patients_to_predict:
        precomputed_results = predict_mortality_risk_batch(patients_to_predict)

    rows = []
    for p in patients:
        records = records_by_pid.get(p.id, [])

        # Fast path: return cached ML result — only Patient ORM obj is refreshed
        _cached_entry = _ML_PER_PATIENT_CACHE.get(p.id)
        if _cached_entry and now_ts < _cached_entry[1]:
            rows.append({"patient": p, **_cached_entry[0]})
            continue

        df = [
            {
                "month": r.record_month,
                "hb": r.hb, "albumin": r.albumin,
                "phosphorus": r.phosphorus, "idwg": r.idwg,
                "urr": r.urr, "serum_ferritin": r.serum_ferritin,
                "tsat": r.tsat, "ipth": r.ipth, "bp_sys": r.bp_sys,
                "epo_weekly_units": r.epo_weekly_units,
                "epo_mircera_dose": r.epo_mircera_dose,
                "wbc_count": r.wbc_count, "neutrophil_count": r.neutrophil_count, "crp": r.crp,
                "hospitalization_this_month": r.hospitalization_this_month,
                "weight": r.target_dry_weight or p.dry_weight,
                "iv_iron_dose":          r.iv_iron_dose,
                "phosphate_binder_type": r.phosphate_binder_type,
            }
            for r in records
        ]
        patient_info = {
            "age":                 p.age,
            "cad_status":         p.cad_status,
            "chf_status":         p.chf_status,
            "dm_status":          p.dm_status,
            "ef":                 p.ejection_fraction,
            "history_of_pvd":     getattr(p, "history_of_pvd",     None),
            "dm_end_organ_damage": getattr(p, "dm_end_organ_damage", None),
            "solid_tumor":        getattr(p, "solid_tumor",        None),
            "leukemia":           getattr(p, "leukemia",           None),
            "lymphoma":           getattr(p, "lymphoma",           None),
        }
        _precomputed = precomputed_results.get(p.id) if precomputed_results else None
        mort = predict_mortality_risk(df, patient_info, _precomputed=_precomputed) if df else {"available": False}
        bay_profile = compute_bayesian_alert_profile(df, patient_info) if df else {"available": False}
        mort = attach_bayesian_signal(mort, bay_profile)
        davies = compute_davies_score(patient_info, df[0] if df else None)
        # ── Deterioration SHAP (fast — LogisticRegression, O(n_features)) ─────
        # Use the materialized feature snapshot when available — O(1) dict lookup
        # instead of re-deriving all features from the monthly record.  Falls back
        # to live extraction for patients whose snapshot hasn't been computed yet.
        det_shap = None
        snap = _snap_by_pid.get(p.id)
        if det_model is not None and df:
            if snap is not None and snap.feature_vector:
                fv = snap.feature_vector
                feats = [
                    fv.get("hb_alert", 0), fv.get("hb", 10.0),
                    fv.get("alb_alert", 0), fv.get("albumin", 3.5),
                    fv.get("target_score", 5.0), fv.get("epo_hypo", 0),
                    fv.get("age", 60), fv.get("cad", 0),
                    fv.get("chf", 0), fv.get("dm_type", 0),
                ]
            else:
                latest = df[0]
                hb_v    = latest.get("hb")
                alb_v   = latest.get("albumin")
                epo_hyp = (hb_v is not None and hb_v < 10.0 and
                           (latest.get("epo_weekly_units") or latest.get("epo_mircera_dose")))
                feats = _build_feature_vector(
                    hb_val=hb_v,
                    hb_alert=(hb_v is not None and hb_v < 10.0),
                    alb_val=alb_v,
                    alb_alert=(alb_v is not None and alb_v < 3.5),
                    target_score=None,
                    epo_hypo=epo_hyp,
                    age=p.age,
                    cad=p.cad_status,
                    chf=p.chf_status,
                    dm_status=p.dm_status,
                    is_training=False,
                )
            det_shap = _compute_deterioration_shap(det_model, feats)

        _ml_result = {
            "mort":         mort,
            "prob_1yr":     mort["data"].get("prob_1yr") if mort.get("available") else None,
            "risk_level":   mort["data"].get("risk_level", "Unknown") if mort.get("available") else "Unknown",
            "css_class":    mort["data"].get("class", "secondary") if mort.get("available") else "secondary",
            "confidence":   mort["data"].get("data_completeness", "—") if mort.get("available") else "—",
            "latest_hb":    df[0].get("hb") if df else None,
            "latest_alb":   df[0].get("albumin") if df else None,
            "n_months":     len(df),
            "bay_profile":  bay_profile,
            "davies":       davies,
            "det_shap":     det_shap,
            "feature_hash": snap.feature_hash if snap else None,
        }
        _ML_PER_PATIENT_CACHE[p.id] = (_ml_result, now_ts + _ML_CACHE_TTL)
        rows.append({"patient": p, **_ml_result})

    # Populate whole-function cache with non-ORM data only
    _ML_FULL_CACHE["rows"] = [(p.id, {k: v for k, v in r.items() if k != "patient"}) for p, r in zip(patients, rows)]
    _ML_FULL_CACHE["ts"] = now_ts
    return rows


# PERF FIX 2: module-level mortality cache to avoid recomputing on every call
_MORTALITY_CACHE: dict = {"ts": 0.0, "count": 0}


def get_high_risk_mortality_count(db: Session) -> int:
    """
    Returns the count of patients with 1-year mortality risk > 0.40.
    Cached for 5 minutes to avoid recomputing on every dashboard load.
    """
    if _time.time() - _MORTALITY_CACHE["ts"] < 300:
        return _MORTALITY_CACHE["count"]
    count = sum(1 for r in get_all_patients_mortality_risk(db) if r.get("risk_level") == "High")
    _MORTALITY_CACHE.update({"ts": _time.time(), "count": count})
    return count
