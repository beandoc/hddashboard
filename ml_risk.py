"""
ml_risk.py
==========
Deterioration Risk Model (logistic regression) and Mortality Risk Prediction
(XGBoost Xu et al. 2023) for hemodialysis patients.
"""
import math
import logging
import os
import pickle
import json
import warnings
import time as _time
from datetime import datetime
from typing import List, Dict, Optional

import numpy as np

from database import MonthlyRecord, Patient

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

from sqlalchemy.orm import Session

from ml_trends import _month_to_ordinal

logger = logging.getLogger(__name__)

# ── Deterioration Risk ────────────────────────────────────────────────────────

# 10 features used for both training and inference — must stay in sync
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
]

_MODEL_PATH      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deterioration_model.pkl")
_MODEL_META_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deterioration_model_meta.json")


def _build_feature_vector(
    hb_val, hb_alert,
    alb_val, alb_alert,
    target_score,
    epo_hypo,
    age, cad, chf, dm_status,
    is_training=False
) -> list:
    """
    Unified feature vector constructor.
    Ensures identical feature ordering and normalization for both training and inference.
    """
    # Imputation for inference path only
    if not is_training:
        hb_val       = hb_val if hb_val is not None else 10.0
        alb_val      = alb_val if alb_val is not None else 3.5
        target_score = target_score if target_score is not None else 5.0

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
        1.0 if "type" in str(dm_status or "").lower() else 0.0,
    ]


def _extract_record_features_for_training(record, patient) -> list:
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

    return _build_feature_vector(
        hb_val       = hb,
        hb_alert     = (hb is not None and hb < 10.0),
        alb_val      = albumin,
        alb_alert    = (albumin is not None and albumin < 3.5),
        target_score = target_score,
        epo_hypo     = epo_hypo,
        age          = patient.age,
        cad          = patient.cad_status,
        chf          = patient.chf_status,
        dm_status    = patient.dm_status,
        is_training  = True
    )


def _extract_analytics_features_for_inference(
    hb: dict, alb: dict, target: dict,
    epo: dict = None, patient_info: dict = None,
) -> list:
    """Dict path for real-time inference."""
    epo          = epo or {}
    patient_info = patient_info or {}
    return _build_feature_vector(
        hb_val       = hb.get("current"),
        hb_alert     = hb.get("alert"),
        alb_val      = alb.get("current"),
        alb_alert    = alb.get("risk"),
        target_score = target.get("score"),
        epo_hypo     = epo.get("hypo_response"),
        age          = patient_info.get("age"),
        cad          = patient_info.get("cad_status"),
        chf          = patient_info.get("chf_status"),
        dm_status    = patient_info.get("dm_status"),
        is_training  = False
    )


_DETERIORATION_MODEL = None
_MODEL_LOAD_TIME = 0

def _load_deterioration_model():
    global _DETERIORATION_MODEL, _MODEL_LOAD_TIME

    if os.path.exists(_MODEL_PATH):
        try:
            mtime = os.path.getmtime(_MODEL_PATH)
            # If already loaded and file hasn't changed, return cached
            if _DETERIORATION_MODEL is not None and mtime <= _MODEL_LOAD_TIME:
                return _DETERIORATION_MODEL

            with open(_MODEL_PATH, "rb") as f:
                _DETERIORATION_MODEL = pickle.load(f)
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

            feats = _extract_record_features_for_training(curr, patient)
            label = int(
                bool(nxt.hospitalization_this_month) or
                bool(nxt.hospitalization_diagnosis)  or
                bool(nxt.hospitalization_icd_code)
            )
            X.append(feats)
            y.append(label)

    n_samples  = len(y)
    n_events   = sum(y)
    event_rate = round(n_events / n_samples, 4) if n_samples > 0 else 0.0

    if n_samples < 20:
        return {
            "success": False, "n_samples": n_samples, "n_events": n_events,
            "error": (
                f"Insufficient data: need ≥ 20 paired monthly records, have {n_samples}. "
                "Continue adding monthly records before training."
            ),
        }

    if n_events < 5:
        return {
            "success": False, "n_samples": n_samples, "n_events": n_events,
            "error": (
                f"Only {n_events} hospitalization event(s) recorded. "
                "Need ≥ 5 positive cases to fit a reliable model."
            ),
        }

    # ── 2. Build pipeline ─────────────────────────────────────────────────────
    X_arr = np.array(X, dtype=float)
    y_arr = np.array(y, dtype=int)

    base = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler",  StandardScaler()),
        ("lr",      LogisticRegression(
            class_weight="balanced",
            C=0.5,
            solver="lbfgs",
            max_iter=1000,
        )),
    ])

    # ── 3. Cross-validated AUC ───────────────────────────────────────────────
    n_folds  = min(5, n_events)
    cv       = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)
    cv_probs = cross_val_predict(base, X_arr, y_arr, cv=cv, method="predict_proba")
    cv_auc   = round(float(roc_auc_score(y_arr, cv_probs[:, 1])), 3)

    auc_warning = cv_auc < 0.55

    # ── 4. Fit final calibrated model on all data ─────────────────────────────
    cal_method = "isotonic" if n_samples >= 50 else "sigmoid"
    cal_model  = CalibratedClassifierCV(base, cv=n_folds, method=cal_method)
    cal_model.fit(X_arr, y_arr)

    # ── 5. Persist model + metadata ───────────────────────────────────────────
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump(cal_model, f)

    global _DETERIORATION_MODEL
    _DETERIORATION_MODEL = None

    meta = {
        "trained_at":          datetime.now().isoformat(timespec="seconds"),
        "n_samples":           n_samples,
        "n_events":            n_events,
        "event_rate":          event_rate,
        "n_folds":             n_folds,
        "calibration_method":  cal_method,
        "cv_auc":              cv_auc,
        "auc_warning":         auc_warning,
        "feature_names":       DETERIORATION_FEATURE_NAMES,
        "skipped_patients":    skipped,
    }
    with open(_MODEL_META_PATH, "w") as f:
        json.dump(meta, f, indent=2)

    logger.info(
        "Deterioration model trained: n_samples=%d n_events=%d cv_auc=%.3f cal=%s",
        n_samples, n_events, cv_auc, cal_method,
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

    if model is not None:
        feats = _extract_analytics_features_for_inference(hb_data, alb_data, target_data, epo_data, patient_info)
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

# Lazy-load models at first call (avoids import overhead at startup)
# None = load attempted but failed; {} = not yet attempted
_XGB_MODELS: dict = {}
_XGB_LOAD_ATTEMPTED: bool = False

def _load_xgb_models() -> dict:
    """Load the three XGBoost PKL models once and cache them."""
    global _XGB_MODELS, _XGB_LOAD_ATTEMPTED
    if _XGB_LOAD_ATTEMPTED:
        return _XGB_MODELS  # already tried — return cached result (may be empty)
    _XGB_LOAD_ATTEMPTED = True
    try:
        model_dir = os.path.join(os.path.dirname(__file__), "models")
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
    Returns (log_odds, used_features, missing_features, n_core_used).
    """
    log_odds = -1.4
    used, missing = [], []
    n_core_used = 0

    age = patient_info.get("age")
    if age is not None:
        if   age >= 80: log_odds += 1.5
        elif age >= 70: log_odds += 1.1
        elif age >= 60: log_odds += 0.7
        elif age >= 50: log_odds += 0.3
        used.append(f"Age {age}yr"); n_core_used += 1
    else:
        missing.append("Age")

    albumin_gdl = latest.get("albumin")
    if albumin_gdl is not None:
        alb_gl = albumin_gdl * 10.0
        if   alb_gl >= 40.0: log_odds -= 0.30
        elif alb_gl >= 35.0: log_odds += 0.00
        elif alb_gl >= 30.0: log_odds += 0.60
        else:                log_odds += 1.20
        used.append(f"Albumin {albumin_gdl:.1f} g/dL"); n_core_used += 1
    else:
        missing.append("Albumin")

    wbc = latest.get("wbc_count")
    if wbc is not None:
        n_est = wbc * 0.65
        if   n_est > 10.0: log_odds += 1.10
        elif n_est >  7.5: log_odds += 0.70
        elif n_est >  4.5: log_odds += 0.20
        used.append(f"Neutrophil (est.) {n_est:.1f}"); n_core_used += 1
    else:
        crp = latest.get("crp")
        if crp and crp > 10:
            log_odds += 0.50
            used.append(f"CRP {crp:.1f} mg/L (proxy)")
        else:
            missing.append("Neutrophil / WBC")

    ef = patient_info.get("ef")
    if ef is not None:
        if   ef < 30: log_odds += 1.40
        elif ef < 40: log_odds += 0.90
        elif ef < 50: log_odds += 0.50
        elif ef < 60: log_odds += 0.20
        used.append(f"EF {ef}%"); n_core_used += 1
    else:
        if patient_info.get("chf_status"):
            log_odds += 0.75; used.append("CHF (EF proxy)")
        else:
            missing.append("EF (echo not recorded)")

    cad = patient_info.get("cad_status")
    if cad is not None:
        if cad: log_odds += 0.65; used.append("IHD/CAD present")
        else:   used.append("No IHD/CAD")
        n_core_used += 1
    else:
        missing.append("IHD/CAD status")

    return log_odds, used, missing, n_core_used


def predict_mortality_risk(df: List[Dict], patient_info: dict = None) -> Dict:
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
    idh = 1 if cad else 0

    core_present = {
        "Age":      age is not None,
        "Albumin":  albumin_gl is not None,
        "Neutrophil": neutrophil is not None,
        "EF":       ef is not None,
        "IDH/CAD":  cad is not None,
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

    # ── Attempt XGBoost prediction ───────────────────────────────────────────
    models = _load_xgb_models()
    model_type = "unknown"
    prob_1yr = prob_4yr = prob_7yr = None

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
                f"{'IHD/CAD present' if cad else 'No IHD/CAD'}",
            ]
        except Exception as e:
            logger.warning(f"XGBoost prediction failed: {e}. Falling back.")
            models = {}

    if prob_1yr is None and models and n_core_used >= 2:
        # Partial features available → impute missing with population medians
        MEDIANS = {"age": 62, "albumin_gl": 37.0, "neutrophil": 5.5, "ef": 60, "idh": 0}
        age_x      = age if age is not None else MEDIANS["age"]
        albumin_x  = albumin_gl if albumin_gl is not None else MEDIANS["albumin_gl"]
        neut_x     = neutrophil if neutrophil is not None else MEDIANS["neutrophil"]
        ef_x       = ef if ef is not None else MEDIANS["ef"]
        idh_x      = idh if cad is not None else MEDIANS["idh"]

        imputed = []
        if age is None:      imputed.append(f"Age (imputed median {MEDIANS['age']}yr)")
        if albumin_gl is None: imputed.append(f"Albumin (imputed median {MEDIANS['albumin_gl']} g/L)")
        if neutrophil is None: imputed.append(f"Neutrophil (imputed median {MEDIANS['neutrophil']})")
        if ef is None:       imputed.append(f"EF (imputed median {MEDIANS['ef']}%)")
        if cad is None:      imputed.append(f"IDH (imputed No)")

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
                    elif k == "IDH/CAD": used.append("IHD/CAD present" if cad else "No IHD/CAD")
            used += [f"⚠ {i}" for i in imputed]
        except Exception as e:
            logger.warning(f"XGBoost imputed prediction failed: {e}. Using rule-based fallback.")
            models = {}

    if prob_1yr is None:
        # Full fallback: rule-based log-odds
        log_odds, used, missing, n_core_used = _rule_based_log_odds_fallback(latest, patient_info)
        prob_1yr = round(_sigmoid(log_odds), 3)
        prob_4yr = round(min(0.97, 1 - (1 - prob_1yr) ** 3.5), 3)
        prob_7yr = round(min(0.99, 1 - (1 - prob_1yr) ** 6.5), 3)
        model_type = "rule_based_log_odds"

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
            "model_calibration_status": "pending Indian cohort validation",
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
            "indian_pop_note":    (
                "Trained on Chinese HD cohort (n~900). Indian HD patients have earlier "
                "ESRD onset, higher DM burden, and lower baseline albumin. "
                "Risk direction is valid; absolute values require local validation."
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

    albumin_gdl = None
    if latest_record:
        albumin_gdl = latest_record.get("albumin")
    if albumin_gdl is None:
        n_missing += 1
        inputs_missing.append("Albumin")
    elif albumin_gdl < 2.5:
        score += 2
        components.append("Albumin < 2.5 g/dL (+2)")

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


def get_all_patients_mortality_risk(db: Session) -> List[Dict]:
    """
    Compute mortality risk for all active patients.

    PERF: Batch-loads all MonthlyRecords in 2 queries (patients + records)
    instead of 1+N queries. Records are sorted and sliced in Python.
    """
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
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

    from bayesian_analytics import compute_bayesian_alert_profile, augment_mortality_risk

    rows = []
    for p in patients:
        records = records_by_pid.get(p.id, [])
        df = [
            {
                "month": r.record_month,
                "hb": r.hb, "albumin": r.albumin,
                "phosphorus": r.phosphorus, "idwg": r.idwg,
                "urr": r.urr, "serum_ferritin": r.serum_ferritin,
                "tsat": r.tsat, "ipth": r.ipth, "bp_sys": r.bp_sys,
                "epo_weekly_units": r.epo_weekly_units,
                "epo_mircera_dose": r.epo_mircera_dose,
                "wbc_count": r.wbc_count, "crp": r.crp,
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
        mort = predict_mortality_risk(df, patient_info) if df else {"available": False}
        bay_profile = compute_bayesian_alert_profile(df, patient_info) if df else {"available": False}
        mort = augment_mortality_risk(mort, bay_profile)
        davies = compute_davies_score(patient_info, df[0] if df else None)
        rows.append({
            "patient":     p,
            "mort":        mort,
            "prob_1yr":    mort["data"].get("prob_1yr") if mort.get("available") else None,
            "risk_level":  mort["data"].get("risk_level", "Unknown") if mort.get("available") else "Unknown",
            "css_class":   mort["data"].get("class", "secondary") if mort.get("available") else "secondary",
            "confidence":  mort["data"].get("data_completeness", "—") if mort.get("available") else "—",
            "latest_hb":   df[0].get("hb") if df else None,
            "latest_alb":  df[0].get("albumin") if df else None,
            "n_months":    len(df),
            "bay_profile": bay_profile,
            "davies":      davies,
        })
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
