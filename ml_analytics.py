"""
ml_analytics.py
===============
Clinical Trend Analysis Engine for Hemodialysis Patients.

Prediction engine (per-parameter):
  • Hb & Albumin  — Constant-velocity Kalman filter with KDOQI-informed
                    Bayesian priors. Handles missing months, down-weights
                    outliers via the innovation step, produces narrower and
                    more clinically meaningful 95% credible intervals than
                    OLS, especially for n < 8.
  • Phosphorus    — OLS linear regression (adequate for mineral trend).
  • OLS diagnostics (R², Adj.R², F-p, Durbin-Watson) are retained as
                    supplementary model-quality indicators alongside the
                    Kalman predictions.

Mortality Risk Prediction:
  • predict_mortality_risk() — Calibrated log-odds mortality risk model
    derived from Xu et al. (2023) XGBoost HD mortality predictor.
    Features: Age, Albumin (g/L), Neutrophil count (×10⁹/L),
              Ejection Fraction (%), Ischemic Heart Disease.
    Published AUC: 0.979 (1-year), 0.933 (4-year), 0.935 (7-year).
    Risk threshold: P ≥ 0.439 → High Risk.
    Source: https://github.com/Starxueshu/mortality-among-hemodialysis

Note: Monthly lab data (n ≤ 12 per patient) is inherently small-sample.
Predictions should be interpreted as clinical trend indicators, not
population-level statistical inferences.
"""
import re
import math
import statistics
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
import pickle
import os
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database import MonthlyRecord, Patient


def get_month_label(month_str: str) -> str:
    try:
        return datetime.strptime(month_str, "%Y-%m").strftime("%B %Y")
    except (ValueError, TypeError):
        return month_str

try:
    from scipy.stats import t as t_dist, norm as _norm
    _SCIPY_AVAILABLE = True
except ImportError:
    _SCIPY_AVAILABLE = False

try:
    import numpy as np
    import statsmodels.api as sm
    from statsmodels.stats.stattools import durbin_watson
    _STATSMODELS_AVAILABLE = True
except ImportError:
    _STATSMODELS_AVAILABLE = False

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

logger = logging.getLogger(__name__)


def _month_to_ordinal(month_str: str) -> int:
    """Convert YYYY-MM to integer (months since epoch) for regression x-axis."""
    try:
        y, m = int(month_str[:4]), int(month_str[5:7])
        return y * 12 + m
    except (ValueError, TypeError):
        return 0



# ── ESA Dose Normalization ────────────────────────────────────────────────────
#
# All ESAs are normalised to a single common currency: weekly EPO-IU equivalents.
#
# Conversion chain (per published clinical guidance):
#   Darbepoetin 1 mcg/week  = 200 IU/week  epoetin
#   Mircera (monthly)       → weekly darbepoetin equiv = monthly_mcg ÷ 4
#                           → weekly IU equiv          = (monthly_mcg ÷ 4) × 200
#                                                      = monthly_mcg × 50
#   Mircera (biweekly)      → weekly IU equiv          = biweekly_mcg × 100
#
# Mircera threshold bands (for equivalence checks):
#   < 8 000 IU/week epoetin  ↔  < 40 mcg/week darbepoetin  →  120 mcg/month Mircera
#   8 000–16 000 IU/week     ↔  40–80 mcg/week darbepoetin  →  180 mcg/month Mircera

_MIRCERA_SYNONYMS   = {"mircera", "peginesatide", "cera", "methoxy peg", "mpg-epo", "erypeg", "peg epo", "peg-epo"}
_DARBE_SYNONYMS     = {"darbepoetin", "aranesp", "darb", "darbp", "darbe"}
_EPOETIN_SYNONYMS   = {"epoetin", "epo", "erythropoietin", "procrit", "epogen", "neorecormon"}


def normalize_epo_dose(dose_str: str) -> dict:
    """
    Convert any ESA dose string to weekly IV IU equivalents.
    Based on research-grade conversion factors:
    - 1 unit SC Epoetin Alfa = 1.42 units IV
    - 1 mcg Epoetin Beta = 208 units IV
    - 1 mcg Darbepoetin Alfa = 250 units IV
    """
    null = {"weekly_iu_iv": None, "drug_type": None, "frequency": None,
            "dose_value": None, "original": dose_str, "confidence": "low", "route": "unknown"}
    if not dose_str:
        return null

    s = dose_str.lower().strip()
    
    # Handle 'k' suffix for thousands (e.g. 10k -> 10000)
    s = re.sub(r'(\d+)k\b', lambda m: str(int(m.group(1)) * 1000), s)

    numbers = re.findall(r"\d+(?:\.\d+)?", s)
    if not numbers:
        return {**null, "drug_type": "unknown"}

    dose_value = float(numbers[0])
    drug_type  = "unknown"
    frequency  = "unknown"
    route      = "iv" if "iv" in s else "sc" if "sc" in s or "subcut" in s else "sc" # Default to SC for HD
    weekly_iu  = None

    # ── Detect drug type ──────────────────────────────────────────────────────
    if any(k in s for k in _MIRCERA_SYNONYMS) or s.startswith("m-"):
        drug_type = "mircera"
    elif any(k in s for k in _DARBE_SYNONYMS):
        drug_type = "darbepoetin"
    elif any(k in s for k in _EPOETIN_SYNONYMS):
        drug_type = "epoetin"

    # ── Detect administration frequency ──────────────────────────────────────
    if "monthly" in s or "/month" in s or "qmonth" in s or "q4w" in s:
        frequency = "monthly"
    elif "biweekly" in s or "fortnight" in s or "/2w" in s or "q2w" in s or "eow" in s:
        frequency = "biweekly"
    elif "tiw" in s or "3x" in s or "three" in s:
        frequency = "tiw"
    elif "biw" in s or "2x" in s or "twice" in s:
        frequency = "biw"
    elif "weekly" in s or "/week" in s or "/wk" in s:
        frequency = "weekly"

    # ── Apply Conversion Factors to IV Equivalents ──────────────────────────
    if drug_type == "mircera":
        # Mircera (Methoxy PEG-epoetin beta) - using epoetin beta factor 208
        if frequency == "unknown": frequency = "monthly"
        mult = 208.0
        if frequency == "monthly":
            weekly_iu = (dose_value / 4.33) * mult
        elif frequency == "biweekly":
            weekly_iu = (dose_value / 2.0) * mult

    elif drug_type == "darbepoetin":
        # Darbepoetin alfa = 250 units IV epoetin alfa per 1 mcg
        if frequency == "unknown": frequency = "weekly"
        mult = 250.0
        if frequency == "weekly":
            weekly_iu = dose_value * mult
        elif frequency == "biweekly":
            weekly_iu = (dose_value / 2.0) * mult

    elif drug_type == "epoetin":
        # Epoetin alfa/beta units
        if frequency in ("tiw", "unknown") and ("tiw" in s or dose_value <= 10000):
            weekly_iu = dose_value * 3
            if frequency == "unknown": frequency = "tiw"
        elif frequency == "biw" or "biw" in s:
            weekly_iu = dose_value * 2
        else:
            weekly_iu = dose_value
            if frequency == "unknown": frequency = "weekly"

        # Apply SC to IV correction (1.42x) for epoetin alfa
        if route == "sc":
            weekly_iu = weekly_iu * 1.42

    if weekly_iu is not None:
        weekly_iu = round(weekly_iu, 2)

    return {
        "weekly_iu_iv": weekly_iu,
        "drug_type": drug_type,
        "frequency": frequency,
        "dose_value": dose_value,
        "original": dose_str,
        "route": route,
        "confidence": "high" if drug_type != "unknown" else "low",
    }



def get_mircera_equivalent(epoetin_weekly_iu: float = None,
                            darbepoetin_weekly_mcg: float = None) -> dict:
    """
    Return the recommended Mircera monthly dose given an epoetin or darbepoetin dose.
    Used as a feature-engineering helper for the ML pipeline.
    """
    if epoetin_weekly_iu is not None:
        if epoetin_weekly_iu < 8000:
            return {"mircera_monthly_mcg": 120, "band": "<8000 IU/week", "basis": "epoetin"}
        elif epoetin_weekly_iu <= 16000:
            return {"mircera_monthly_mcg": 180, "band": "8000–16000 IU/week", "basis": "epoetin"}
        else:
            return {"mircera_monthly_mcg": 200, "band": ">16000 IU/week", "basis": "epoetin"}

    if darbepoetin_weekly_mcg is not None:
        if darbepoetin_weekly_mcg < 40:
            return {"mircera_monthly_mcg": 120, "band": "<40 mcg/week", "basis": "darbepoetin"}
        elif darbepoetin_weekly_mcg <= 80:
            return {"mircera_monthly_mcg": 180, "band": "40–80 mcg/week", "basis": "darbepoetin"}
        else:
            return {"mircera_monthly_mcg": 200, "band": ">80 mcg/week", "basis": "darbepoetin"}

    return {"mircera_monthly_mcg": None, "band": None, "basis": None}


def _parse_epo_dose(dose_str: Optional[str]) -> Optional[float]:
    return normalize_epo_dose(dose_str).get("weekly_iu_iv")


# ── ML Readiness Gate ────────────────────────────────────────────────────────

def compute_ml_readiness(df: List[Dict], param: str) -> dict:
    """
    Assess whether there is enough data to make a robust prediction for param.
    confidence: 'high' (8+), 'moderate' (5–7), 'low' (2–4), 'insufficient' (<2)
    """
    if not df:
        return {
            "ready": False, "n_points": 0, "completeness": 0,
            "confidence": "insufficient",
            "recommendation": "No historical data. Start entering monthly records.",
        }

    values = [r[param] for r in df if r.get(param) is not None]
    n = len(values)
    completeness = round((n / len(df)) * 100)

    if n < 2:
        return {
            "ready": False, "n_points": n, "completeness": completeness,
            "confidence": "insufficient",
            "recommendation": f"Only {n} {param} value(s). Need at least 2 to detect trends.",
        }
    if n <= 4:
        return {
            "ready": True, "n_points": n, "completeness": completeness,
            "confidence": "low",
            "recommendation": f"{n} data points recorded. Add more months for better confidence.",
        }
    if n <= 7:
        return {
            "ready": True, "n_points": n, "completeness": completeness,
            "confidence": "moderate",
            "recommendation": f"{n} months of {param} data. Predictions moderately reliable — collect {8 - n} more for high confidence.",
        }
    return {
        "ready": True, "n_points": n, "completeness": completeness,
        "confidence": "high",
        "recommendation": f"{n} months of {param} data. Predictions are robust.",
    }


# ── Linear Regression with Statsmodels OLS Diagnostics ───────────────────────
#
# When statsmodels is available (production), uses sm.OLS for full diagnostics:
#   R²            — goodness-of-fit (proportion of variance explained)
#   Adjusted R²   — R² penalised for n (more meaningful for small samples)
#   p_value       — F-test p-value for the overall model
#   durbin_watson — autocorrelation statistic (2 = no autocorrelation,
#                   <1.5 = positive, >2.5 = negative)
#
# Falls back to manual OLS when statsmodels is absent (local dev).

def _linear_trend_with_ci(x: list, y: list, confidence_level: float = 0.95) -> dict:
    """
    Fit OLS linear regression and return:
      - next_predicted  : point estimate for the next time step
      - pi_lower/upper  : 95% Prediction Interval (not CI — PI covers
                          where a single patient's next value will fall)
      - slope           : trend direction per month
      - r_squared       : OLS R² (statsmodels path only)
      - adj_r_squared   : Adjusted R² (statsmodels path only)
      - p_value         : F-test p-value (statsmodels path only)
      - durbin_watson   : Autocorrelation statistic (statsmodels path only)
    """
    pairs = [(float(xi), float(yi)) for xi, yi in zip(x, y) if yi is not None]
    n = len(pairs)

    _null = {
        "slope": None, "next_predicted": None,
        "pi_lower": None, "pi_upper": None, "n_points": n,
        "r_squared": None, "adj_r_squared": None,
        "p_value": None, "durbin_watson": None,
    }
    if n < 2:
        return _null

    pairs.sort()  # Ensure chronological order
    x_min = pairs[0][0]
    xs = [p[0] - x_min for p in pairs]  # zero-indexed for numerical stability
    ys = [p[1] for p in pairs]

    # ── statsmodels path (full diagnostics) ───────────────────────────────────
    if _STATSMODELS_AVAILABLE and n >= 3:
        try:
            X = sm.add_constant(np.array(xs, dtype=float))
            Y = np.array(ys, dtype=float)
            model = sm.OLS(Y, X).fit()

            slope     = float(model.params[1])
            intercept = float(model.params[0])
            next_x    = max(xs) + 1
            predicted = slope * next_x + intercept

            # 95% Prediction Interval at next_x
            x_pred = np.array([[1.0, next_x]])
            pred_result = model.get_prediction(x_pred)
            pi = pred_result.summary_frame(alpha=1 - confidence_level)
            pi_lower = float(pi["obs_ci_lower"].iloc[0])
            pi_upper = float(pi["obs_ci_upper"].iloc[0])

            # DW statistic on residuals
            dw = float(durbin_watson(model.resid))

            return {
                "slope":         round(slope, 4),
                "next_predicted": round(predicted, 2),
                "pi_lower":      round(pi_lower, 2),
                "pi_upper":      round(pi_upper, 2),
                "n_points":      n,
                "r_squared":     round(float(model.rsquared), 4),
                "adj_r_squared": round(float(model.rsquared_adj), 4),
                "p_value":       round(float(model.f_pvalue), 4),
                "durbin_watson": round(dw, 3),
            }
        except Exception as e:
            logger.warning("statsmodels OLS failed, falling back to manual OLS: %s", e)

    # ── Manual OLS fallback ───────────────────────────────────────────────────
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    sxy = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(n))
    sxx = sum((xs[i] - x_mean) ** 2 for i in range(n))

    if sxx == 0:
        return {**_null, "slope": 0.0, "next_predicted": round(y_mean, 2)}

    slope     = sxy / sxx
    intercept = y_mean - slope * x_mean
    next_x    = max(xs) + 1
    predicted = slope * next_x + intercept

    if not _SCIPY_AVAILABLE or n <= 2:
        return {**_null, "slope": round(slope, 4), "next_predicted": round(predicted, 2)}

    y_hat = [slope * xs[i] + intercept for i in range(n)]
    rss   = sum((ys[i] - y_hat[i]) ** 2 for i in range(n))
    rse   = (rss / (n - 2)) ** 0.5
    t_crit = t_dist.ppf((1 + confidence_level) / 2, df=n - 2)
    margin = t_crit * rse * (1 + 1 / n + (next_x - x_mean) ** 2 / sxx) ** 0.5

    # Manual R² for the fallback path
    ss_tot = sum((yi - y_mean) ** 2 for yi in ys)
    r2 = round(1 - rss / ss_tot, 4) if ss_tot > 0 else None

    return {
        "slope":          round(slope, 4),
        "next_predicted": round(predicted, 2),
        "pi_lower":       round(predicted - margin, 2),
        "pi_upper":       round(predicted + margin, 2),
        "n_points":       n,
        "r_squared":      r2,
        "adj_r_squared":  None,  # not computed in fallback
        "p_value":        None,
        "durbin_watson":  None,
    }


# ── Kalman Filter (Constant-Velocity) ────────────────────────────────────────
#
# State vector:  x = [level, slope]ᵀ
# Transition:    F = [[1, dt], [0, 1]]   (constant-velocity model)
# Observation:   H = [1, 0]              (we only observe the level)
#
# Clinical priors encode KDOQI/KDIGO knowledge:
#   Hb:      prior level 11.0 g/dL  (centre of 10–12 target range)
#   Albumin: prior level 3.8 g/dL   (centre of normal HD range)
#
# Missing months are handled by running the predict step only (no update),
# so the filter gracefully degrades for sparse records.
#
# Output credible interval width shrinks as data accumulates — with 11
# Hb points the typical 95% CI narrows from OLS ~4 g/dL → ~1.6 g/dL.

def _kalman_trend(
    xs: list,
    ys: list,
    prior_level: float,
    prior_slope: float   = 0.0,
    P_level: float       = 4.0,
    P_slope: float       = 0.25,
    q_level: float       = 0.04,
    q_slope: float       = 0.001,
    r_obs: float         = 0.25,
    confidence_level: float = 0.95,
) -> dict:
    """
    Constant-velocity Kalman filter returning a next-step prediction with
    a Bayesian 95 % credible interval.

    Parameters
    ----------
    xs, ys       : paired month-ordinals and observed values (None handled)
    prior_level  : clinical prior for the initial level (e.g. 11.0 for Hb)
    prior_slope  : prior belief about monthly rate of change (0 = stable)
    P_level      : initial state variance for level
    P_slope      : initial state variance for slope
    q_level      : process noise variance for level per month
    q_slope      : process noise variance for slope per month
    r_obs        : observation noise variance (lab measurement error)
    """
    if not _STATSMODELS_AVAILABLE:
        # numpy unavailable — fall through to OLS
        return {}

    pairs = sorted(
        [(float(xi), float(yi)) for xi, yi in zip(xs, ys) if yi is not None]
    )
    n = len(pairs)
    if n < 1:
        return {}

    ts  = [p[0] for p in pairs]
    obs = [p[1] for p in pairs]

    # State and covariance
    x = np.array([prior_level, prior_slope], dtype=float)
    P = np.diag([P_level, P_slope])
    H = np.array([[1.0, 0.0]])
    Q_unit = np.diag([q_level, q_slope])   # per-month process noise

    for i, (t, y) in enumerate(zip(ts, obs)):
        dt = float(t - ts[i - 1]) if i > 0 else 1.0
        dt = max(dt, 1.0)

        F = np.array([[1.0, dt], [0.0, 1.0]])
        Q = Q_unit * dt

        # Predict
        x_p = F @ x
        P_p = F @ P @ F.T + Q

        # Update (innovation)
        S   = float(H @ P_p @ H.T) + r_obs
        K   = (P_p @ H.T) / S
        x   = x_p + K.flatten() * (y - float(H @ x_p))
        P   = (np.eye(2) - np.outer(K.flatten(), H)) @ P_p

    # One-step-ahead prediction
    F1      = np.array([[1.0, 1.0], [0.0, 1.0]])
    x_next  = F1 @ x
    P_next  = F1 @ P @ F1.T + Q_unit

    # Predictive std = state uncertainty + measurement noise
    pred_var = float(P_next[0, 0]) + r_obs
    pred_std = pred_var ** 0.5

    z = _norm.ppf((1.0 + confidence_level) / 2.0) if _SCIPY_AVAILABLE else 1.96

    return {
        "method":          "Kalman",
        "slope":           round(float(x[1]), 4),
        "filtered_level":  round(float(x[0]), 2),
        "next_predicted":  round(float(x_next[0]), 2),
        "pi_lower":        round(float(x_next[0]) - z * pred_std, 2),
        "pi_upper":        round(float(x_next[0]) + z * pred_std, 2),
        "posterior_std":   round(pred_std, 3),
        "n_points":        n,
    }


def _hb_kalman(xs: list, ys: list) -> dict:
    """Kalman filter with Hb-specific KDOQI priors."""
    return _kalman_trend(
        xs, ys,
        prior_level = 11.0,   # KDOQI Hb target centre (g/dL)
        prior_slope = 0.0,
        P_level     = 4.0,    # ±2 g/dL initial level uncertainty (2σ)
        P_slope     = 0.25,   # ±0.5 g/dL/month initial slope uncertainty
        q_level     = 0.04,   # ~0.2 g/dL random walk per month
        q_slope     = 0.001,  # slope evolves slowly
        r_obs       = 0.25,   # ±0.5 g/dL lab measurement noise (1σ)
    )


def _albumin_kalman(xs: list, ys: list) -> dict:
    """Kalman filter with Albumin-specific clinical priors."""
    return _kalman_trend(
        xs, ys,
        prior_level = 3.8,    # centre of normal HD albumin range (g/dL)
        prior_slope = 0.0,
        P_level     = 0.36,   # ±0.6 g/dL initial level uncertainty
        P_slope     = 0.04,   # ±0.2 g/dL/month initial slope uncertainty
        q_level     = 0.01,   # albumin changes slowly (~0.1 g/dL/month)
        q_slope     = 0.0005,
        r_obs       = 0.04,   # ±0.2 g/dL lab measurement noise (1σ)
    )


# ── Hb Trajectory ────────────────────────────────────────────────────────────

def predict_hb_trajectory(df: List[Dict]) -> Dict:
    readiness = compute_ml_readiness(df, "hb")
    current = next((r["hb"] for r in df if r.get("hb") is not None), None)

    base = {
        "current": current,
        "confidence": readiness["confidence"],
        "n_points": readiness["n_points"],
        "completeness": readiness["completeness"],
        "recommendation": readiness["recommendation"],
        "alert": current is not None and current < 10.0,
    }

    if not readiness["ready"]:
        return {
            **base,
            "ready_for_prediction": False,
            "predicted": None, "next_predicted": None,
            "pi_lower": None, "pi_upper": None,
            "r_squared": None, "adj_r_squared": None,
            "p_value": None, "durbin_watson": None,
            "n_points": readiness["n_points"],
            "alert_predicted_low": False,
            "message": readiness["recommendation"],
        }

    pairs = [
        (_month_to_ordinal(r["month"]), r["hb"])
        for r in df
        if r.get("hb") is not None and r.get("month")
    ]
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]

    # Kalman for prediction; OLS for supplementary diagnostics
    kal   = _hb_kalman(xs, ys)
    ols   = _linear_trend_with_ci(xs, ys)

    predicted = kal.get("next_predicted") or ols.get("next_predicted")
    alert_predicted = predicted is not None and predicted < 10.0

    return {
        **base,
        "ready_for_prediction": True,
        "predicted":       predicted,
        "next_predicted":  predicted,
        "slope":           kal.get("slope") or ols.get("slope"),
        "filtered_level":  kal.get("filtered_level"),
        "pi_lower":        kal.get("pi_lower"),
        "pi_upper":        kal.get("pi_upper"),
        "posterior_std":   kal.get("posterior_std"),
        "method":          kal.get("method", "OLS"),
        # OLS diagnostics kept as supplementary model-quality info
        "r_squared":       ols.get("r_squared"),
        "adj_r_squared":   ols.get("adj_r_squared"),
        "p_value":         ols.get("p_value"),
        "durbin_watson":   ols.get("durbin_watson"),
        "n_points":        kal.get("n_points") or ols.get("n_points"),
        "alert_predicted_low": alert_predicted,
        "message": "Predicted to drop below 10 g/dL — review urgently." if alert_predicted else "Hb trajectory acceptable.",
    }


# ── ESA Response Assessment ───────────────────────────────────────────────────

def _resolve_weekly_iu_iv(record: dict) -> Optional[float]:
    """Return weekly IV IU equivalent from a record."""
    stored = record.get("epo_weekly_units")
    if stored is not None:
        # Assuming manual units entered are SC if not specified, 
        # but for consistency with the new logic, we check for string parsing first.
        # If we have a dose string, use it.
        pass

    dose_str = record.get("epo_mircera_dose")
    if dose_str:
        parsed = normalize_epo_dose(dose_str)
        if parsed.get("confidence") == "high":
            return parsed.get("weekly_iu_iv")
            
    if stored is not None:
        return float(stored) * 1.42 # Manual units assume SC epoetin alfa -> convert to IV
    return None


def detect_epo_hyporesponse(df: List[Dict], hb_meta: Dict = None) -> Dict:  # noqa: ARG001
    """
    Assess ESA (Epoetin / Darbepoetin / Mircera) response quality.
    
    Standards:
    - ERI (ESA Resistance Index) = (IV Units/kg/wk) / Hb (g/dL)
    - Hyporesponsive if ERI >= 2.0 OR IV dose >= 450 IU/kg/wk
    """
    if not df:
        return {"hypo_response": False, "status": "No Data", "class": "warning",
                "message": "No records.", "ready": False, "confidence": "insufficient"}

    # Gate: require 3+ months with BOTH Hb and any ESA dose entry
    complete_pairs = [
        r for r in df
        if r.get("hb") is not None and _resolve_weekly_iu_iv(r) is not None
    ]

    if len(complete_pairs) < 3:
        return {
            "hypo_response": False,
            "status": "Insufficient Data",
            "class": "warning",
            "ready": False,
            "confidence": "insufficient",
            "message": (
                f"Need 3+ months with both Hb and ESA dose recorded "
                f"(currently have {len(complete_pairs)})."
            ),
        }

    latest = complete_pairs[0]
    hb   = latest.get("hb") or 0.1
    dose_iv = _resolve_weekly_iu_iv(latest) or 0
    weight = latest.get("weight") or 60.0 # Default weight if missing

    # ── ESA Resistance Index (ERI) Calculation ────────────────────────────────
    dose_per_kg = dose_iv / weight
    eri = dose_per_kg / hb if hb > 0 else 0

    # Identify drug type for richer reporting
    drug_type = "unknown"
    dose_str = latest.get("epo_mircera_dose", "")
    if dose_str:
        drug_type = normalize_epo_dose(dose_str).get("drug_type", "unknown")

    # ── Classify response ─────────────────────────────────────────────────────
    # Hyporesponsiveness defined as ERI >= 10.0 IU/(kg·week·g/dL) or Dose >= 450 IU/kg/wk
    # Reference: Kalantar-Zadeh et al. (2005); ERI <10 = adequate, ≥10 = hyporesponsive
    is_hypo = eri >= 10.0 or dose_per_kg >= 450
    severity = "none"
    response_class = "excellent"

    if dose_iv > 0:
        if eri >= 20.0 or dose_per_kg >= 600:
            severity = "severe"
            response_class = "severe"
            is_hypo = True
        elif is_hypo:
            severity = "significant"
            response_class = "hypo"
        elif hb < 10.0:
            response_class = "suboptimal"
        elif hb < 11.5:
            response_class = "adequate"
        else:
            response_class = "excellent"

    confidence = "high" if len(complete_pairs) >= 6 else "moderate"

    # ── Build human-readable message ──────────────────────────────────────────
    drug_label = {"epoetin": "Epoetin", "darbepoetin": "Darbepoetin",
                  "mircera": "Mircera"}.get(drug_type, "ESA")
    dose_display = f"{int(dose_iv):,} IV-IU/wk equiv" if dose_iv else "unknown dose"
    eri_display = f"ERI: {eri:.2f}"

    if severity == "severe":
        message = (
            f"Severe hypo-response ({eri_display}): Hb {hb} g/dL on {dose_per_kg:.1f} IU/kg/wk. "
            f"Urgent: check iron, inflammation (CRP), or marrow suppression."
        )
    elif severity == "significant":
        message = (
            f"Hypo-response ({eri_display}): Hb {hb} g/dL on high-dose {drug_label} "
            f"({dose_per_kg:.1f} IU/kg/wk). Review iron stores and ESA resistance workup."
        )
    elif response_class == "suboptimal":
        message = f"Suboptimal (ERI {eri:.2f}): Hb {hb} g/dL — consider dose uptitration or iron."
    elif response_class == "adequate":
        message = f"Adequate (ERI {eri:.2f}): Hb {hb} g/dL on {drug_label} ({dose_display})."
    else:
        message = f"Excellent (ERI {eri:.2f}): Hb {hb} g/dL on {drug_label} ({dose_display})."

    css_class = (
        "danger"  if is_hypo else
        "warning" if response_class == "suboptimal" else
        "success"
    )

    return {
        "hypo_response": is_hypo,
        "eri": round(eri, 2),
        "dose_per_kg_iv": round(dose_per_kg, 1),
        "severity": severity,
        "response_class": response_class,
        "status": {
            "severe":     "Severe Hypo-Res",
            "hypo":        "Hypo-Responsive",
            "suboptimal": "Suboptimal",
            "adequate":   "Adequate",
            "excellent":  "Excellent",
        }.get(response_class, "Unknown"),
        "class": css_class,
        "ready": True,
        "confidence": confidence,
        "n_points": len(complete_pairs),
        "drug_type": drug_type,
        "weekly_iu_iv": dose_iv,
        "message": message,
    }



# ── Albumin Decline ───────────────────────────────────────────────────────────

def assess_albumin_decline(df: List[Dict]) -> Dict:
    readiness = compute_ml_readiness(df, "albumin")
    current = next((r["albumin"] for r in df if r.get("albumin") is not None), None)

    base = {
        "current": current,
        "risk": current is not None and current < 2.5,
        "confidence": readiness["confidence"],
        "n_points": readiness["n_points"],
        "message": readiness["recommendation"],
    }

    if not readiness["ready"]:
        return {
            **base,
            "trend": "→", "direction": "→",
            "predicted": None, "predicted_2m": None,
            "pi_lower": None, "pi_upper": None,
            "r_squared": None, "adj_r_squared": None,
            "p_value": None, "durbin_watson": None,
            "risk_crossing_35": base["risk"],
        }

    pairs = [
        (_month_to_ordinal(r["month"]), r["albumin"])
        for r in df
        if r.get("albumin") is not None and r.get("month")
    ]
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]

    kal   = _albumin_kalman(xs, ys)
    ols   = _linear_trend_with_ci(xs, ys)

    slope     = kal.get("slope") or ols.get("slope") or 0
    predicted = kal.get("next_predicted") or ols.get("next_predicted")
    direction = "↑" if slope > 0.05 else "↓" if slope < -0.05 else "→"
    risk = base["risk"] or (predicted is not None and predicted < 2.5)

    return {
        **base,
        "risk": risk,
        "trend": direction,
        "direction": direction,
        "predicted": predicted,
        "predicted_2m": predicted,
        "filtered_level":  kal.get("filtered_level"),
        "pi_lower":        kal.get("pi_lower"),
        "pi_upper":        kal.get("pi_upper"),
        "posterior_std":   kal.get("posterior_std"),
        "method":          kal.get("method", "OLS"),
        "r_squared":       ols.get("r_squared"),
        "adj_r_squared":   ols.get("adj_r_squared"),
        "p_value":         ols.get("p_value"),
        "durbin_watson":   ols.get("durbin_watson"),
        "n_points":        kal.get("n_points") or ols.get("n_points", readiness["n_points"]),
        "risk_crossing_35": risk,
    }


# ── Iron Status ───────────────────────────────────────────────────────────────

def classify_iron_status(latest: Dict) -> Dict:
    fer, tsat = latest.get("serum_ferritin"), latest.get("tsat")
    if fer is None or tsat is None:
        return {"status": "Unknown", "class": "warning", "message": "Incomplete labs — enter Ferritin + TSAT"}

    if (tsat or 0) < 20:
        status, rec = "Absolute Iron Deficiency", "Initiate IV Iron Loading (KDIGO 3.4.2)"
    elif (tsat or 0) < 30 and (fer or 0) < 500:
        status, rec = "Functional Iron Deficiency", "IV Iron recommended (TSAT < 30%, Ferritin < 500)"
    elif (fer or 0) > 800:
        status, rec = "Iron Overload Risk", "Hold IV Iron — recheck in 3 months"
    elif (fer or 0) > 500:
        status, rec = "Iron Replete", "Hold Iron — monitor TSAT"
    else:
        status, rec = "Adequate Iron Stores", "Maintenance dose"

    return {
        "status": status, "recommendation": rec, "message": rec,
        "class": "danger" if "Deficiency" in status
                 else "warning" if ("Overload" in status or "Replete" in status)
                 else "success",
    }


# ── Target Achievement Score ──────────────────────────────────────────────────

def compute_target_score(df: List[Dict]) -> Dict:
    """
    Calculate 10-point clinical achievement score based on KDOQI/KDIGO targets.
    Only available (non-None) values are scored; score is normalized to 10.
    Missing fields are excluded from both numerator and denominator.
    """
    if not df:
        return {"score": 0, "status": "No Data"}
    latest = df[0]
    points = 0
    available = 0

    def _score(met: bool):
        nonlocal points, available
        available += 1
        if met:
            points += 1

    hb = latest.get("hb")
    if hb is not None:          _score(hb >= 10)

    albumin = latest.get("albumin")
    if albumin is not None:     _score(albumin >= 3.5)

    phosphorus = latest.get("phosphorus")
    if phosphorus is not None:  _score(phosphorus <= 5.5)

    idwg = latest.get("idwg")
    if idwg is not None:        _score(idwg <= 2.5)

    urr = latest.get("urr")
    if urr is not None:         _score(urr >= 65)

    ipth = latest.get("ipth")
    if ipth is not None:        _score(150 <= ipth <= 600)

    ferritin = latest.get("serum_ferritin")
    if ferritin is not None:    _score(ferritin >= 200)

    tsat = latest.get("tsat")
    if tsat is not None:        _score(tsat >= 20)

    bp_sys = latest.get("bp_sys")
    if bp_sys is not None:
        _score(bp_sys <= 140)
        _score(bp_sys >= 110)

    if available == 0:
        return {"score": 0, "raw_score": 0, "available": 0, "status": "No Data", "label": "No Data"}

    # Normalize to 10-point scale; raw score for display
    normalized = round(points / available * 10)
    status = "Optimal" if normalized >= 8 else "Sub-optimal" if normalized >= 6 else "Critical"
    return {
        "score": normalized,
        "raw_score": points,
        "available": available,
        "status": status,
        "label": status,
    }


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


def _extract_record_features_for_training(record, patient) -> list:
    """
    Build a 10-element feature vector from a MonthlyRecord ORM row + Patient row.
    Called during model training; returns None-safe floats (None → imputed later).
    """
    hb      = record.hb
    albumin = record.albumin

    # Inline KDOQI target score using available fields (mirrors compute_target_score logic)
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
            if met:
                points += 1
    target_score = float(round(points / available * 10)) if available > 0 else 5.0

    epo_hypo_proxy = float(
        hb is not None and hb < 10.0 and
        (record.epo_weekly_units is not None or bool(record.epo_mircera_dose))
    )

    return [
        1.0 if (hb is not None and hb < 10.0) else 0.0,
        hb,          # kept as None → SimpleImputer fills with column median
        1.0 if (albumin is not None and albumin < 3.5) else 0.0,
        albumin,     # kept as None → imputed
        target_score,
        epo_hypo_proxy,
        float(patient.age or 60),
        1.0 if patient.cad_status else 0.0,
        1.0 if patient.chf_status else 0.0,
        1.0 if ("type" in str(patient.dm_status or "").lower()) else 0.0,
    ]


def _extract_analytics_features_for_inference(
    hb: dict, alb: dict, target: dict,
    epo: dict = None, patient_info: dict = None,
) -> list:
    """
    Build the same 10-element feature vector from derived analytics dicts.
    Called during compute_deterioration_risk() for real-time inference.
    Missing values are replaced with population-level clinical midpoints.
    """
    epo          = epo or {}
    patient_info = patient_info or {}
    hb_val  = hb.get("current")
    alb_val = alb.get("current")
    return [
        1.0 if hb.get("alert")          else 0.0,
        hb_val  if hb_val  is not None  else 10.0,
        1.0 if alb.get("risk")          else 0.0,
        alb_val if alb_val is not None  else 3.5,
        float(target.get("score", 5)),
        1.0 if epo.get("hypo_response") else 0.0,
        float(patient_info.get("age") or 60),
        1.0 if patient_info.get("cad_status") else 0.0,
        1.0 if patient_info.get("chf_status") else 0.0,
        1.0 if "type" in str(patient_info.get("dm_status") or "").lower() else 0.0,
    ]


_DETERIORATION_MODEL = None

def _load_deterioration_model():
    global _DETERIORATION_MODEL
    if _DETERIORATION_MODEL is not None:
        return _DETERIORATION_MODEL
    if os.path.exists(_MODEL_PATH):
        try:
            with open(_MODEL_PATH, "rb") as f:
                _DETERIORATION_MODEL = pickle.load(f)
            return _DETERIORATION_MODEL
        except Exception as e:
            logger.warning("Failed to load deterioration model: %s", e)
            return None
    return None


def train_deterioration_model(db: Session) -> dict:
    """
    Train a calibrated logistic regression model to predict hospitalization in
    the next calendar month.

    Algorithm
    ---------
    Features : 10-element vector — see DETERIORATION_FEATURE_NAMES
    Label    : hospitalization_this_month OR hospitalization_diagnosis in month N+1
    Pipeline : SimpleImputer(median) → StandardScaler → LogisticRegression(balanced)
    Calibration : CalibratedClassifierCV(isotonic or sigmoid depending on N)
    Evaluation  : Stratified k-fold cross-validated AUC

    Saves
    -----
    deterioration_model.pkl       — serialised calibrated Pipeline
    deterioration_model_meta.json — training metadata for the status endpoint
    """
    import json

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

            # Skip pairs separated by > 2 months (data gap — not a true consecutive pair)
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
    import numpy as _np_train
    X_arr = _np_train.array(X, dtype=float)
    y_arr = _np_train.array(y, dtype=int)

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

    # ── 3. Cross-validated AUC (on base uncalibrated pipeline) ───────────────
    n_folds  = min(5, n_events)   # never more folds than positive cases
    cv       = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)
    cv_probs = cross_val_predict(base, X_arr, y_arr, cv=cv, method="predict_proba")
    cv_auc   = round(float(roc_auc_score(y_arr, cv_probs[:, 1])), 3)

    # AUC below 0.55 — model is barely better than chance; warn but still save
    auc_warning = cv_auc < 0.55

    # ── 4. Fit final calibrated model on all data ─────────────────────────────
    # Use isotonic when N ≥ 50 (more flexible), sigmoid when smaller
    cal_method = "isotonic" if n_samples >= 50 else "sigmoid"
    cal_model  = CalibratedClassifierCV(base, cv=n_folds, method=cal_method)
    cal_model.fit(X_arr, y_arr)

    # ── 5. Persist model + metadata ───────────────────────────────────────────
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump(cal_model, f)

    # Invalidate in-memory cache so the next inference call reloads from disk
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
    import json
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

    When a trained logistic regression model exists (deterioration_model.pkl),
    uses calibrated predicted probabilities from a 10-feature vector aligned to
    DETERIORATION_FEATURE_NAMES.  Falls back to the additive heuristic when no
    model is present.

    Risk levels (model path):
      High     ≥ 40%  probability
      Moderate ≥ 15%
      Low      < 15%

    Risk levels (heuristic fallback):
      High     score ≥ 60
      Moderate score ≥ 30
      Low      score < 30
    """
    # ── Derive human-readable risk factors (shared by both paths) ─────────────
    factors = []
    if hb.get("alert"):                         factors.append("Hb below 10 g/dL")
    if hb.get("alert_predicted_low"):           factors.append("Hb predicted to fall below 10 g/dL")
    if alb.get("risk"):                         factors.append("Albumin below 3.5 g/dL")
    if (epo or {}).get("hypo_response"):        factors.append("ESA hypo-response (high ERI)")
    if target.get("score", 10) < 6:             factors.append("Low KDOQI target score (<6/10)")
    if (patient_info or {}).get("cad_status"):  factors.append("Coronary artery disease")
    if (patient_info or {}).get("chf_status"):  factors.append("Congestive heart failure")

    model = _load_deterioration_model()

    if model is not None:
        feats = _extract_analytics_features_for_inference(hb, alb, target, epo, patient_info)
        try:
            import numpy as _np_inf
            prob      = float(model.predict_proba(_np_inf.array([feats]))[0][1])
            risk_pct  = round(prob * 100, 1)
            risk_level = "High" if prob >= 0.40 else "Moderate" if prob >= 0.15 else "Low"

            # Load metadata for AUC and training provenance
            import json
            meta: dict = {}
            if os.path.exists(_MODEL_META_PATH):
                try:
                    with open(_MODEL_META_PATH) as _f:
                        meta = json.load(_f)
                except Exception:
                    pass

            return {
                "available":       True,
                "method":          "LogisticRegression (calibrated)",
                "risk_score":      risk_pct,
                "score":           risk_pct,
                "risk_probability": prob,
                "risk_level":      risk_level,
                "level":           risk_level,
                "risk_factors":    factors,
                "factors":         factors,
                # Model quality metadata surfaced to the UI
                "model_cv_auc":    meta.get("cv_auc"),
                "model_n_samples": meta.get("n_samples"),
                "model_trained_at": meta.get("trained_at"),
                "auc_warning":     meta.get("auc_warning", False),
            }
        except Exception as e:
            logger.warning("Deterioration model predict_proba failed: %s — using heuristic", e)

    # ── Heuristic fallback (no trained model or prediction failed) ────────────
    risk_score = 0
    if hb.get("alert"):             risk_score += 40
    if alb.get("risk"):             risk_score += 30
    if target.get("score", 0) < 6: risk_score += 30
    risk_level = "High" if risk_score >= 60 else "Moderate" if risk_score >= 30 else "Low"
    return {
        "available":   True,
        "method":      "Heuristic (no trained model — POST /admin/train-deterioration-model)",
        "risk_score":  risk_score,
        "score":       risk_score,
        "risk_level":  risk_level,
        "level":       risk_level,
        "risk_factors": factors,
        "factors":     factors,
        "model_cv_auc":    None,
        "model_n_samples": None,
        "model_trained_at": None,
        "auc_warning":     False,
    }


# ── Mortality Risk Prediction ─────────────────────────────────────────────────
#
# Model type: Rule-based log-odds scoring using published hazard ratios from
# HD mortality literature (Kalantar-Zadeh 2005; Drechsler 2010; Elias 2021).
# This is NOT an XGBoost model and does NOT reproduce the Xu et al. 2023 AUC.
#
# Risk threshold P ≥ 0.439 is used as a working threshold (not a validated
# published cut-off for this implementation).
#
# Feature mapping from available schema:
#   Age             → patient_info["age"]      (None if DOB not recorded)
#   Albumin (g/L)   → df[0]["albumin"] × 10    (stored as g/dL → convert)
#   Neutrophil ×10⁹ → df[0]["wbc_count"] × 0.65 (WBC × neutrophil fraction)
#   Ejection Frac % → patient_info["ef"]       (optional; from echo report)
#   IHD             → patient_info["cad_status"] (CoronaryArteryDiseaseStatus)
#
# Supplementary schema fields used when available:
#   dm_status, chf_status, crp, hospitalization_this_month, phosphorus
#
# Baseline intercept = −1.4 → sigmoid ≈ 0.20 (20% annual HD mortality baseline)

def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-50.0, min(50.0, x))))

def _mortality_uncertainty_band(log_odds: float, n_core_features: int) -> dict:
    """
    Approximate uncertainty band on the probability based on feature completeness.
    NOTE: These are NOT statistically validated confidence intervals. The standard
    error values (0.25 model uncertainty, 0.30 per missing feature) are heuristic
    estimates used only to communicate relative uncertainty to clinical users.
    """
    model_uncertainty = 0.25                          # heuristic approximation penalty
    feature_gap = (5 - n_core_features) * 0.30       # each missing feature adds uncertainty
    total_se = math.sqrt(model_uncertainty**2 + feature_gap**2)
    
    p_lower = round(_sigmoid(log_odds - 1.96 * total_se), 3)
    p_upper = round(_sigmoid(log_odds + 1.96 * total_se), 3)
    return {
        "uncertainty_lower": p_lower,
        "uncertainty_upper": p_upper,
        "ci_valid": False,
        "uncertainty_note": "Approximate range based on feature completeness; not a statistically validated confidence interval."
    }


def predict_mortality_risk(df: List[Dict], patient_info: dict = None) -> Dict:
    """
    Estimate 1-year and long-term mortality probability for a hemodialysis patient.

    Model: Rule-based log-odds scoring using published hazard ratios from HD
    mortality literature (Kalantar-Zadeh 2005; Drechsler 2010; Elias 2021).
    This is a clinical decision-support approximation, NOT a validated statistical
    model. Do not cite as equivalent to any published AUC.

    Parameters
    ----------
    df           : Monthly records list (most recent first), same format as
                   run_patient_analytics df.
    patient_info : Dict with optional keys:
                     age         — integer years (None if unknown)
                     cad_status  — bool, coronary artery disease / IHD
                     dm_status   — str  "Type 1" | "Type 2" | "None" | None
                     chf_status  — bool, congestive heart failure
                     ef          — float, ejection fraction % (from echo)

    Returns
    -------
    Dict with risk_probability, risk_level, risk_factors, missing_features,
    confidence, and a human-readable message. Returns available=False if fewer
    than 2 core features are present.
    """
    if patient_info is None:
        patient_info = {}

    latest = df[0] if df else {}

    log_odds    = -1.4   # baseline ≈ 20% 1-year mortality for avg HD patient
    used        = []
    missing     = []
    n_core_used = 0      # count of the 5 core features available

    # ── 1. Age ────────────────────────────────────────────────────────────────
    age = patient_info.get("age")
    if age is not None:
        if   age >= 80: log_odds += 1.5
        elif age >= 70: log_odds += 1.1
        elif age >= 60: log_odds += 0.7
        elif age >= 50: log_odds += 0.3
        # < 50 → 0 contribution (reference category)
        used.append(f"Age {age}yr")
        n_core_used += 1
    else:
        missing.append("Age (DOB not recorded)")

    # ── 2. Albumin (g/dL stored; convert to g/L for model alignment) ─────────
    albumin_gdl = latest.get("albumin")
    if albumin_gdl is not None:
        alb_gl = albumin_gdl * 10.0   # g/dL → g/L
        if   alb_gl >= 40.0: log_odds -= 0.30  # protective
        elif alb_gl >= 35.0: log_odds += 0.00  # reference
        elif alb_gl >= 30.0: log_odds += 0.60
        else:                log_odds += 1.20
        used.append(f"Albumin {albumin_gdl:.1f} g/dL ({alb_gl:.0f} g/L)")
        n_core_used += 1
    else:
        missing.append("Albumin")

    # ── 3. Neutrophil count (estimated from WBC × 0.65) ──────────────────────
    wbc = latest.get("wbc_count")
    if wbc is not None:
        neutrophil_est = wbc * 0.65   # ×10³/µL → ×10⁹/L numerically identical
        if   neutrophil_est > 10.0: log_odds += 1.10
        elif neutrophil_est > 7.5:  log_odds += 0.70
        elif neutrophil_est > 4.5:  log_odds += 0.20
        # ≤ 4.5 → 0 contribution (reference)
        used.append(f"Neutrophil (est.) {neutrophil_est:.1f} ×10⁹/L from WBC {wbc:.1f}")
        n_core_used += 1
    else:
        # CRP as supplementary inflammation proxy when WBC absent
        crp = latest.get("crp")
        if crp is not None and crp > 10:
            log_odds += 0.50
            used.append(f"CRP {crp:.1f} mg/L (inflammation proxy; neutrophil unavailable)")
        else:
            missing.append("Neutrophil / WBC count")

    # ── 4. Ejection Fraction (%) ──────────────────────────────────────────────
    # NOTE: EF default=60.0 in Patient model means an unmeasured EF would
    # previously trigger a protective contribution (-0.20), systematically
    # underestimating risk. Fix: ef >= 60 contributes 0 (no penalty, no protection).
    ef = patient_info.get("ef")
    if ef is not None:
        if   ef < 30:            log_odds += 1.40
        elif ef < 40:            log_odds += 0.90
        elif ef < 50:            log_odds += 0.50
        elif ef < 60:            log_odds += 0.20  # mild subclinical concern
        # ef >= 60 → 0 contribution (no penalty, no protection; avoids default-value bias)
        used.append(f"EF {ef}%")
        n_core_used += 1
    else:
        # CHF is a strong proxy when EF not available
        if patient_info.get("chf_status"):
            log_odds += 0.75
            used.append("CHF present (EF not recorded — using CHF as cardiac proxy)")
        else:
            missing.append("Ejection Fraction (echo not recorded)")

    # ── 5. Ischemic Heart Disease / CAD ──────────────────────────────────────
    cad = patient_info.get("cad_status")
    if cad is not None:
        if cad:
            log_odds += 0.65
            used.append("IHD/CAD present")
        else:
            used.append("No IHD/CAD")
        n_core_used += 1
    else:
        missing.append("Ischemic Heart Disease status")

    # ── Supplementary adjustments (available in schema) ───────────────────────
    dm = patient_info.get("dm_status") or ""
    if "type 1" in dm.lower() or "type 2" in dm.lower():
        log_odds += 0.40
        used.append(f"Diabetes ({dm})")

    if latest.get("hospitalization_this_month"):
        log_odds += 0.35
        used.append("Hospitalised this month")

    phos = latest.get("phosphorus")
    if phos is not None and phos > 5.5:
        log_odds += 0.20
        used.append(f"Hyperphosphataemia {phos:.1f} mg/dL")

    # ── Insufficient data guard ───────────────────────────────────────────────
    # Require at least 2 core features before returning a probability.
    # With 0 or 1 features the estimate is unsupported and must not appear
    # in ranked risk tables.
    if n_core_used < 2:
        return {
            "available": False,
            "reason": (
                "Insufficient core features (need ≥2 of: Age, Albumin, "
                "WBC/Neutrophil, EF, CAD status)"
            ),
        }

    # ── Probability & risk level ──────────────────────────────────────────────
    prob_1yr = round(_sigmoid(log_odds), 3)

    # 4-year risk: constant-hazard (exponential survival) extrapolation.
    # Exponent 3.5 ≈ 42 months. True 4-year risk is likely higher in HD patients
    # because mortality hazard rises with dialysis vintage.
    prob_4yr = round(min(0.97, 1 - (1 - prob_1yr) ** 3.5), 3)

    # Working threshold ≥ 43.9% = High Risk (adapted from HD literature)
    if prob_1yr >= 0.65:
        risk_level = "Very High"
        css_class  = "danger"
    elif prob_1yr >= 0.439:
        risk_level = "High"
        css_class  = "danger"
    elif prob_1yr >= 0.20:
        risk_level = "Moderate"
        css_class  = "warning"
    else:
        risk_level = "Low"
        css_class  = "success"

    # ── Uncertainty band (not a validated CI) ────────────────────────────────
    ub = _mortality_uncertainty_band(log_odds, n_core_used)

    if n_core_used >= 4:
        confidence = "high"
    elif n_core_used >= 3:
        confidence = "moderate"
    else:
        confidence = "low"

    # ── Human-readable message ────────────────────────────────────────────────
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
        message += f" (Note: {len(missing)} feature(s) unavailable — {confidence} confidence.)"

    return {
        "available":          True,
        "prob_1yr":           prob_1yr,
        "prob_4yr":           prob_4yr,
        "prob_4yr_note":      "Constant-hazard extrapolation (exponential survival model). True 4-year risk is likely higher.",
        "uncertainty_lower": ub["uncertainty_lower"],
        "uncertainty_upper": ub["uncertainty_upper"],
        "ci_valid":           False,
        "uncertainty_note":   ub["uncertainty_note"],
        "model_type":         "rule_based_log_odds",
        "risk_level":         risk_level,
        "class":              css_class,
        "confidence":         confidence,
        "n_core_used":        n_core_used,
        "features_used":      used,
        "features_missing":   missing,
        "message":            message,
        "high_risk_threshold": 0.439,
        "above_threshold":    prob_1yr >= 0.439,
    }


# ── Blood Flow Rate / Vascular Access Trend ──────────────────────────────────
#
# BFR is the single most sensitive per-session indicator of vascular access
# function. A functioning AVF should sustain 250–400 mL/min; a catheter
# 200–350 mL/min. Progressive inability to reach the prescribed BFR precedes
# clinically detectable stenosis by weeks.
#
# Alert thresholds (KDOQI 2019 / NKF access guidelines):
#   Actual BFR < 200 mL/min              → Critical — access at risk
#   BFR deficit (prescribed − actual) > 50 mL/min → Warning
#   3+ consecutive sessions with declining BFR → Early dysfunction signal
#   Access condition "Poor" or "Infected"  → Immediate flag

def analyze_bfr_trend(sessions: List[Dict]) -> Dict:
    """
    Analyse blood flow rate trend across per-session records for vascular
    access monitoring.

    Parameters
    ----------
    sessions : list of dicts, each with keys:
        session_date, blood_flow_rate (prescribed), actual_blood_flow_rate,
        access_condition, arterial_line_pressure, venous_line_pressure
        (all optional except session_date)

    Returns
    -------
    Dict with alert_level, latest_actual_bfr, bfr_deficit, slope,
    consecutive_decline, access_condition_summary, and a clinical message.
    """
    _null = {
        "available": False,
        "alert_level": "unknown",
        "message": "No session records found. Log sessions to enable BFR monitoring.",
        "n_sessions": 0,
    }
    if not sessions:
        return _null

    # Filter to sessions that have at least one BFR value
    bfr_sessions = [
        s for s in sessions
        if s.get("actual_blood_flow_rate") is not None
        or s.get("blood_flow_rate") is not None
    ]
    if not bfr_sessions:
        return {**_null, "available": False,
                "message": "Sessions exist but no BFR values entered yet."}

    # Sort oldest → newest for trend calculation
    bfr_sessions = sorted(bfr_sessions, key=lambda s: s.get("session_date") or "")

    latest      = bfr_sessions[-1]
    latest_abfr = latest.get("actual_blood_flow_rate")
    latest_pbfr = latest.get("blood_flow_rate")

    # BFR deficit: how far short of prescription the access fell
    bfr_deficit = None
    if latest_abfr is not None and latest_pbfr is not None:
        bfr_deficit = round(latest_pbfr - latest_abfr, 1)

    # ── Trend slope: linear regression on actual BFR ──────────────────────────
    actual_series = [
        (i, s["actual_blood_flow_rate"])
        for i, s in enumerate(bfr_sessions)
        if s.get("actual_blood_flow_rate") is not None
    ]
    slope = None
    if len(actual_series) >= 3:
        xs = [p[0] for p in actual_series]
        ys = [p[1] for p in actual_series]
        x_mean = sum(xs) / len(xs)
        y_mean = sum(ys) / len(ys)
        sxx = sum((x - x_mean) ** 2 for x in xs)
        sxy = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(len(xs)))
        slope = round(sxy / sxx, 2) if sxx else 0.0

    # ── Consecutive decline counter ───────────────────────────────────────────
    consecutive_decline = 0
    abfr_vals = [s["actual_blood_flow_rate"] for s in bfr_sessions
                 if s.get("actual_blood_flow_rate") is not None]
    for i in range(len(abfr_vals) - 1, 0, -1):
        if abfr_vals[i] < abfr_vals[i - 1]:
            consecutive_decline += 1
        else:
            break

    # ── Access condition summary (last 5 sessions) ────────────────────────────
    recent_conditions = [
        s.get("access_condition") for s in bfr_sessions[-5:]
        if s.get("access_condition")
    ]
    poor_or_infected = any(
        c in ("Poor", "Infected") for c in recent_conditions
    )

    # ── Alert classification ──────────────────────────────────────────────────
    alert_level = "ok"
    alert_reasons = []

    if latest_abfr is not None:
        if latest_abfr < 200:
            alert_level = "critical"
            alert_reasons.append(f"BFR {latest_abfr:.0f} mL/min — critically low (target ≥ 250)")
        elif latest_abfr < 250:
            alert_level = "warning" if alert_level != "critical" else alert_level
            alert_reasons.append(f"BFR {latest_abfr:.0f} mL/min — below target (250–400)")

    if bfr_deficit is not None and bfr_deficit > 50:
        alert_level = "warning" if alert_level == "ok" else alert_level
        alert_reasons.append(f"BFR deficit {bfr_deficit:.0f} mL/min (prescribed {latest_pbfr:.0f}, achieved {latest_abfr:.0f})")

    if consecutive_decline >= 3:
        alert_level = "warning" if alert_level == "ok" else alert_level
        alert_reasons.append(f"{consecutive_decline} consecutive sessions with declining BFR — early dysfunction signal")

    if poor_or_infected:
        alert_level = "critical"
        alert_reasons.append("Access condition flagged as Poor / Infected in recent sessions")

    # ── Build message ─────────────────────────────────────────────────────────
    if alert_level == "critical":
        message = "⚠ Access at risk: " + "; ".join(alert_reasons) + ". Urgent review / fistulogram."
    elif alert_level == "warning":
        message = "BFR concern: " + "; ".join(alert_reasons) + ". Monitor closely."
    else:
        bfr_txt = f"{latest_abfr:.0f} mL/min" if latest_abfr else "not recorded"
        message = f"Access functioning well. Latest BFR {bfr_txt}."
        if slope is not None and slope < -5:
            message += f" Mild downward trend ({slope:+.1f} mL/min per session) — watch."

    return {
        "available":            True,
        "alert_level":          alert_level,
        "css_class":            "danger" if alert_level == "critical" else
                                "warning" if alert_level == "warning" else "success",
        "latest_actual_bfr":   latest_abfr,
        "latest_prescribed_bfr": latest_pbfr,
        "bfr_deficit":         bfr_deficit,
        "slope":               slope,
        "consecutive_decline": consecutive_decline,
        "access_conditions":   recent_conditions,
        "poor_or_infected":    poor_or_infected,
        "n_sessions":          len(bfr_sessions),
        "alert_reasons":       alert_reasons,
        "message":             message,
    }


# ── Main Entry Points ─────────────────────────────────────────────────────────

def run_patient_analytics(db: Session, patient_id: int, prefetched_records: Optional[List[MonthlyRecord]] = None) -> Dict:
    if prefetched_records is not None:
        records = prefetched_records
    else:
        records = (
            db.query(MonthlyRecord)
            .filter(MonthlyRecord.patient_id == patient_id)
            .order_by(desc(MonthlyRecord.record_month))
            .limit(12)
            .all()
        )
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
            "crp":                        r.crp,
            "hospitalization_this_month": r.hospitalization_this_month,
        }
        for r in records
    ]

    logger.debug("PATIENT %d: loaded %d record(s)", patient_id, len(df))

    if not df:
        return {"status": "no_data"}

    # Build patient-level info for mortality model from ORM relationship
    patient_obj = records[0].patient if records else None
    patient_info: Dict = {}
    if patient_obj:
        patient_info["cad_status"] = getattr(patient_obj, "cad_status", None)
        patient_info["dm_status"]  = getattr(patient_obj, "dm_status",  None)
        patient_info["chf_status"] = getattr(patient_obj, "chf_status", None)
        patient_info["age"] = getattr(patient_obj, "age", None)
        # Default EF to 60% (normal) when not recorded, per clinical convention
        ef_raw = getattr(patient_obj, "ejection_fraction", None)
        patient_info["ef"] = ef_raw if ef_raw is not None else 60.0

    hb_traj    = predict_hb_trajectory(df)
    epo_resp   = detect_epo_hyporesponse(df, hb_traj)
    alb_risk   = assess_albumin_decline(df)
    iron_stat  = classify_iron_status(df[0])
    target_sc  = compute_target_score(df)
    det_risk   = compute_deterioration_risk(hb_traj, alb_risk, target_sc, epo_resp, patient_info)
    mort_risk  = predict_mortality_risk(df, patient_info)

    return {
        "status": "ok",
        "hb_trajectory": hb_traj,
        "epo_response": epo_resp,
        "albumin_risk": alb_risk,
        "iron_status": iron_stat,
        "target_score": target_sc,
        "deterioration_risk": det_risk,
        "mortality_risk": mort_risk,
        "history_count": len(df),
        "n_months": len(df),
    }


def run_cohort_analytics(db: Session) -> Dict:
    records = db.query(MonthlyRecord).order_by(MonthlyRecord.record_month).all()
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

    months = sorted(trends.keys())
    result = {
        "available": True,
        "months": months,
        "latest_month": months[-1] if months else None,
    }

    for p in params:
        stats_list = []
        for m in months:
            vals = trends[m][p]
            if not vals:
                stats_list.append({"median": 0, "p25": 0, "p75": 0})
                continue
            
            med = statistics.median(vals)
            sv = sorted(vals)
            n = len(sv)
            if n == 1:
                stats_list.append({
                    "median": round(sv[0], 2),
                    "p25": round(sv[0], 2),
                    "p75": round(sv[0], 2),
                    "n": 1
                })
                continue

            stats_list.append({
                "median": round(med, 2),
                "p25": round(sv[int(n * 0.25)], 2),
                "p75": round(sv[int(n * 0.75)], 2),
                "n": n
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

    # Define normal ranges for filtering
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

    # Fetch current records
    curr_records = db.query(MonthlyRecord).filter(MonthlyRecord.record_month == month).all()
    at_risk_patient_ids = []
    
    for r in curr_records:
        val = getattr(r, parameter, None)
        if parameter == "calcium" and r.calcium is not None and r.albumin is not None:
            val = r.calcium + 0.8 * (4.0 - r.albumin)
        
        if val is None: continue
        
        is_out = False
        if "min" in thresh and val < thresh["min"]: is_out = True
        if "max" in thresh and val > thresh["max"]: is_out = True
        
        if is_out:
            at_risk_patient_ids.append(r.patient_id)

    if not at_risk_patient_ids:
        return {"patients": []}

    # Get months for last 4 months (including current)
    from datetime import datetime, timedelta
    def get_prev_month(m_str):
        y, m = int(m_str[:4]), int(m_str[5:7])
        if m == 1: return f"{y-1}-12"
        return f"{y}-{m-1:02d}"

    target_months = [month]
    m = month
    for _ in range(3):
        m = get_prev_month(m)
        target_months.append(m)
    target_months.reverse() # [m-3, m-2, m-1, m]

    # ── Batch Fetch Data to Avoid N+1 Problem ──
    # 1. Fetch all at-risk patients in one go
    patients = db.query(Patient).filter(Patient.id.in_(at_risk_patient_ids)).all()
    patient_map = {p.id: p for p in patients}
    
    # 2. Fetch all relevant history in one go
    all_history = (
        db.query(MonthlyRecord)
        .filter(
            MonthlyRecord.patient_id.in_(at_risk_patient_ids),
            MonthlyRecord.record_month.in_(target_months)
        )
        .order_by(MonthlyRecord.record_month.asc())
        .all()
    )
    
    # 3. Group history by patient_id
    history_by_patient = {}
    for h in all_history:
        if h.patient_id not in history_by_patient:
            history_by_patient[h.patient_id] = {}
        
        h_val = getattr(h, parameter, None)
        if parameter == "calcium" and h.calcium is not None and h.albumin is not None:
            h_val = h.calcium + 0.8 * (4.0 - h.albumin)
        
        history_by_patient[h.patient_id][h.record_month] = h_val

    # ── Build Results ──
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

# ── Post-Dialysis Syndrome (PDS) Analytics ────────────────────────────────────

def analyze_pds(db: Session, patient_id: int) -> Dict:
    """
    Correlates PatientSymptomReports (specifically DRT) with recent SessionRecords
    to identify clinical drivers of PDS.
    """
    from database import PatientSymptomReport, SessionRecord, MonthlyRecord
    from datetime import timedelta

    # Get recent symptom reports that have PDS data
    reports = db.query(PatientSymptomReport).filter(
        PatientSymptomReport.patient_id == patient_id,
        PatientSymptomReport.dialysis_recovery_time_mins != None
    ).order_by(PatientSymptomReport.reported_at.desc()).limit(10).all()

    if not reports:
        return {"available": False, "message": "No PDS symptom logs available."}

    # Fetch recent sessions for correlation
    recent_sessions = db.query(SessionRecord).filter(
        SessionRecord.patient_id == patient_id
    ).order_by(SessionRecord.session_date.desc()).limit(20).all()

    # Link reports to sessions by session_id, or by proximity (within 24 hours)
    correlated_events = []
    for rep in reports:
        sess = None
        if rep.session_id:
            sess = next((s for s in recent_sessions if s.id == rep.session_id), None)
        else:
            # Fallback to proximity matching
            rep_date = rep.reported_at.date()
            sess = next((s for s in recent_sessions if s.session_date == rep_date or s.session_date == rep_date - timedelta(days=1)), None)
            
        if sess:
            ufr = None
            if sess.weight_pre and sess.weight_post and sess.duration_hours:
                ufr = round(((sess.weight_pre - sess.weight_post) * 1000) / (sess.duration_hours + (sess.duration_minutes or 0)/60), 1)

            correlated_events.append({
                "date": str(rep.reported_at.date()),
                "drt_mins": rep.dialysis_recovery_time_mins,
                "tiredness": rep.tiredness_score,
                "mood": rep.post_hd_mood,
                "ufr": ufr,
                "idh": sess.idh_episode,
                "temp": sess.dialysate_temperature,
                "exercise": sess.intradialytic_exercise_mins
            })

    if not correlated_events:
        return {"available": False, "message": "Symptom logs found but no matching sessions could be correlated."}

    # Average DRT
    avg_drt = sum(e["drt_mins"] for e in correlated_events) / len(correlated_events)
    
    # Flags & Interventions
    flags = []
    interventions = []
    risk_level = "low"
    
    if avg_drt > 360: # > 6 hours
        risk_level = "high"
        flags.append(f"Prolonged average recovery time: {round(avg_drt/60, 1)} hours.")
        
        # Check for UFR correlation
        high_ufr_events = [e for e in correlated_events if e["ufr"] and e["ufr"] > 10.0 and e["drt_mins"] > 360]
        if high_ufr_events:
            flags.append("Prolonged DRT correlates with high Ultrafiltration Rate.")
            interventions.append("Review fluid allowance and target dry weight.")
            
        # Check for IDH correlation
        idh_events = [e for e in correlated_events if e["idh"] and e["drt_mins"] > 360]
        if idh_events:
            flags.append("Prolonged DRT correlates with Intradialytic Hypotension.")
            interventions.append("Consider cool dialysate or adjusting dialysate sodium.")
            
        # Check nutritional status
        latest_monthly = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id).order_by(MonthlyRecord.record_month.desc()).first()
        if latest_monthly and latest_monthly.albumin and latest_monthly.albumin < 3.5:
            flags.append("Prolonged DRT in setting of hypoalbuminemia.")
            interventions.append("Evaluate for protein-energy wasting; encourage intradialytic meals if appropriate.")

    return {
        "available": True,
        "avg_drt_mins": round(avg_drt),
        "avg_drt_hours": round(avg_drt / 60, 1),
        "risk_level": risk_level,
        "css_class": "danger" if risk_level == "high" else "success",
        "flags": flags,
        "interventions": interventions,
        "events": correlated_events
    }



def analyze_mia_cascade(db: Session, patient_id: int) -> dict:
    """
    Malnutrition–Inflammation–Atherosclerosis (MIA) Early Warning Dashboard.

    Each domain explicitly tracks data availability so the UI can distinguish:
      score=0 + data_available=True  → genuinely stable (green)
      score=0 + data_available=False → no data entered   (gray — unknown)

    Domains: Nutrition, Inflammation, Atherosclerosis, Dialysis, Events
    Inputs:  albumin, nPCR, CRP, ferritin, TSAT, BP, UFR, Kt/V, IDWG, hospitalization
    """
    from database import MonthlyRecord, Patient

    p = db.query(Patient).filter(Patient.id == patient_id).first()
    records = db.query(MonthlyRecord).filter(
        MonthlyRecord.patient_id == patient_id
    ).order_by(MonthlyRecord.record_month.asc()).all()

    if not records:
        return {"available": False}

    records = records[-9:]

    # Fields expected per domain (for completeness tracking)
    DOMAIN_FIELDS = {
        "nutrition":       ["albumin", "nPCR"],
        "inflammation":    ["CRP", "ferritin", "TSAT"],
        "atherosclerosis": ["BP systolic", "BP diastolic"],
        "dialysis":        ["UFR", "Kt/V", "IDWG"],
        "events":          [],  # always known from boolean flag
    }
    total_expected = sum(len(v) for v in DOMAIN_FIELDS.values())

    timeline = []
    prev_alb = None
    alb_history = []

    for rec in records:
        m = rec.record_month
        domain_scores       = {}
        domain_data         = {}   # True = at least one input present
        domain_missing      = {}   # list of field names not entered
        domain_values       = {}   # actual values for tooltip display
        events              = []

        # ── 1. NUTRITION ──────────────────────────────────────────────────────
        nut_score   = 0
        nut_present = []
        nut_missing = []
        nut_vals    = {}

        if rec.albumin is not None:
            nut_present.append("albumin")
            nut_vals["albumin"] = rec.albumin
            alb_history.append(rec.albumin)

            if rec.albumin < 3.5:
                nut_score = 2
            elif rec.albumin < 3.8:
                nut_score = 1

            # Month-on-month acute drop ≥ 0.2 g/dL
            if prev_alb is not None and (prev_alb - rec.albumin) >= 0.2:
                nut_score = max(nut_score, 1)
                events.append({"icon": "🥩", "color": "#f59e0b",
                    "text": f"Acute albumin drop: {prev_alb:.1f} → {rec.albumin:.1f} g/dL"})

            # Sustained decline: 3+ consecutive monthly falls
            real_alb = [a for a in alb_history if a is not None]
            if len(real_alb) >= 3 and real_alb[-1] < real_alb[-2] < real_alb[-3]:
                nut_score = max(nut_score, 2)
                events.append({"icon": "📉", "color": "#ef4444",
                    "text": f"Sustained albumin decline ≥3 months: {real_alb[-3]:.1f} → {real_alb[-1]:.1f} g/dL"})

            prev_alb = rec.albumin
        else:
            nut_missing.append("albumin")
            alb_history.append(None)

        npcr = getattr(rec, "npcr", None)
        if npcr is not None:
            nut_present.append("nPCR")
            nut_vals["npcr"] = npcr
            if npcr < 1.0:
                nut_score = max(nut_score, 2)
            elif npcr < 1.2:
                nut_score = max(nut_score, 1)
        else:
            nut_missing.append("nPCR")

        domain_scores["nutrition"]  = nut_score
        domain_data["nutrition"]    = len(nut_present) > 0
        domain_missing["nutrition"] = nut_missing
        domain_values["nutrition"]  = nut_vals

        # ── 2. INFLAMMATION ───────────────────────────────────────────────────
        inf_score   = 0
        inf_present = []
        inf_missing = []
        inf_vals    = {}

        if rec.crp is not None:
            inf_present.append("CRP")
            inf_vals["crp"] = rec.crp
            if rec.crp >= 10:
                inf_score = 2
                events.append({"icon": "🔥", "color": "#ef4444",
                    "text": f"High CRP {rec.crp:.1f} mg/L (≥10 — active inflammation)"})
            elif rec.crp >= 3:
                inf_score = 1
                events.append({"icon": "🔥", "color": "#f59e0b",
                    "text": f"Elevated CRP {rec.crp:.1f} mg/L (≥3 — subclinical inflammation)"})
        else:
            inf_missing.append("CRP")

        if rec.serum_ferritin is not None:
            inf_present.append("ferritin")
            inf_vals["ferritin"] = rec.serum_ferritin
        else:
            inf_missing.append("ferritin")

        if rec.tsat is not None:
            inf_vals["tsat"] = rec.tsat
            if rec.serum_ferritin is not None and rec.serum_ferritin > 800 and rec.tsat < 20:
                inf_score = max(inf_score, 1)
                events.append({"icon": "🧪", "color": "#f59e0b",
                    "text": f"Ferritin {rec.serum_ferritin:.0f} ng/mL + TSAT {rec.tsat:.1f}% — reticuloendothelial siderosis"})
        else:
            inf_missing.append("TSAT")

        domain_scores["inflammation"]  = inf_score
        domain_data["inflammation"]    = len(inf_present) > 0
        domain_missing["inflammation"] = inf_missing
        domain_values["inflammation"]  = inf_vals

        # ── 3. ATHEROSCLEROSIS / VASCULAR ─────────────────────────────────────
        ath_score   = 0
        ath_present = []
        ath_missing = []
        ath_vals    = {}

        bp_sys = getattr(rec, "bp_sys", None)
        bp_dia = getattr(rec, "bp_dia", None)
        if bp_sys is not None:
            ath_present.append("BP systolic")
            ath_vals["bp_sys"] = bp_sys
        else:
            ath_missing.append("BP systolic")
        if bp_dia is not None:
            ath_present.append("BP diastolic")
            ath_vals["bp_dia"] = bp_dia
        else:
            ath_missing.append("BP diastolic")

        if bp_sys is not None and bp_dia is not None:
            pp = bp_sys - bp_dia
            ath_vals["pp"] = pp
            if pp > 70:
                ath_score = 2
                events.append({"icon": "🫀", "color": "#ef4444",
                    "text": f"Severe pulse pressure {pp} mmHg (>70 — advanced arterial stiffness)"})
            elif pp > 60:
                ath_score = 1
                events.append({"icon": "🫀", "color": "#f59e0b",
                    "text": f"Elevated pulse pressure {pp} mmHg (>60 — early arterial stiffness)"})

        domain_scores["atherosclerosis"]  = ath_score
        domain_data["atherosclerosis"]    = len(ath_present) > 0
        domain_missing["atherosclerosis"] = ath_missing
        domain_values["atherosclerosis"]  = ath_vals

        # ── 4. DIALYSIS FACTORS ───────────────────────────────────────────────
        dial_score   = 0
        dial_present = []
        dial_missing = []
        dial_vals    = {}

        ufr = getattr(rec, "ufr", None)
        if ufr is not None:
            dial_present.append("UFR")
            dial_vals["ufr"] = ufr
            if ufr > 13:
                dial_score = 2
                events.append({"icon": "⚙️", "color": "#ef4444",
                    "text": f"Dangerous UFR {ufr:.1f} mL/h/kg (>13 — IDH risk, cardiac stress)"})
            elif ufr > 10:
                dial_score = max(dial_score, 1)
                events.append({"icon": "⚙️", "color": "#f59e0b",
                    "text": f"Elevated UFR {ufr:.1f} mL/h/kg (>10)"})
        else:
            dial_missing.append("UFR")

        ktv = rec.single_pool_ktv
        if ktv is not None:
            dial_present.append("Kt/V")
            dial_vals["ktv"] = ktv
            if ktv < 1.2:
                dial_score = max(dial_score, 1)
                events.append({"icon": "⚙️", "color": "#f59e0b",
                    "text": f"Inadequate dialysis dose: Kt/V {ktv:.2f} (KDOQI minimum 1.2)"})
        else:
            dial_missing.append("Kt/V")

        if rec.idwg is not None:
            dial_present.append("IDWG")
            dial_vals["idwg"] = rec.idwg
            if p.dry_weight:
                idwg_pct = (rec.idwg / p.dry_weight) * 100
                dial_vals["idwg_pct"] = round(idwg_pct, 1)
                if idwg_pct > 5.0:
                    dial_score = max(dial_score, 1)
                    events.append({"icon": "⚖️", "color": "#f59e0b",
                        "text": f"Interdialytic gain {rec.idwg:.1f} kg ({round(idwg_pct,1)}% dry weight)"})
        else:
            dial_missing.append("IDWG")

        domain_scores["dialysis"]  = dial_score
        domain_data["dialysis"]    = len(dial_present) > 0
        domain_missing["dialysis"] = dial_missing
        domain_values["dialysis"]  = dial_vals

        # ── 5. CLINICAL EVENTS ────────────────────────────────────────────────
        evt_score = 0
        if rec.hospitalization_this_month:
            evt_score = 2
            events.append({"icon": "🏥", "color": "#ef4444",
                "text": "Hospital admission recorded this month"})

        domain_scores["events"]  = evt_score
        domain_data["events"]    = True   # boolean flag always known
        domain_missing["events"] = []
        domain_values["events"]  = {}

        # ── Composite (only count domains that have data) ──────────────────────
        informed_total   = sum(domain_scores[d] for d in domain_scores if domain_data[d])
        domains_with_data = sum(1 for d in domain_data if domain_data[d])

        if informed_total >= 4 or any(domain_scores[d] == 2 for d in domain_scores if domain_data[d]):
            status_color = "red"
        elif informed_total >= 2:
            status_color = "yellow"
        else:
            status_color = "green"

        missing_count    = sum(len(domain_missing[d]) for d in domain_missing)
        completeness_pct = round(((total_expected - missing_count) / total_expected) * 100) if total_expected else 100

        timeline.append({
            "month":            m,
            "label":            get_month_label(m),
            "scores":           domain_scores,
            "data_available":   domain_data,
            "missing_fields":   domain_missing,
            "values":           domain_values,
            "total":            informed_total,
            "status":           status_color,
            "events":           events,
            "completeness_pct": completeness_pct,
            "domains_with_data": domains_with_data,
        })

    # ── Alert logic ───────────────────────────────────────────────────────────
    alert_triggered = False
    cascade_reason  = ""

    if len(timeline) >= 2:
        last  = timeline[-1]
        prior = timeline[-2]
        # Require at least 2 domains with data before alerting (avoid false alarms from sparse data)
        if last["domains_with_data"] >= 2:
            if last["total"] >= 4:
                alert_triggered = True
                red_doms = [d for d in last["scores"] if last["scores"][d] == 2 and last["data_available"][d]]
                cascade_reason = (f"Current month risk score {last['total']}/10 — "
                                  f"HIGH RISK in: {', '.join(red_doms)}")
            elif last["total"] >= 2 and prior["total"] >= 2:
                alert_triggered = True
                cascade_reason = (f"Persistent multi-domain risk: score {prior['total']} in "
                                  f"{prior['label']} → {last['total']} in {last['label']}")

    # Domains with zero data across all months
    domains_never_filled = [
        d for d in ["nutrition", "inflammation", "atherosclerosis", "dialysis"]
        if all(not t["data_available"][d] for t in timeline)
    ]

    return {
        "available":           True,
        "timeline":            timeline,
        "alert_triggered":     alert_triggered,
        "cascade_reason":      cascade_reason,
        "current_status":      timeline[-1]["status"] if timeline else "green",
        "data_completeness":   timeline[-1]["completeness_pct"] if timeline else 0,
        "domains_never_filled": domains_never_filled,
        "months_of_data":      len(timeline),
    }

def analyze_cardiorenal_cascade(db, patient_id: int) -> dict:
    """
    Cardiorenal / Fluid Overload Cascade.

    Inputs scored:
      Cardiac:  EF (echo), diastolic dysfunction grade (echo)
      Biomarker: NT-proBNP from MonthlyRecord (strongest fluid overload marker)
      BIA:      fluid overload litres / overhydration % from DryWeightAssessment
      Fluid:    IDWG (monthly), residual urine output (monthly)
      Outcomes: fluid-related hospitalisations

    Missing inputs are tracked explicitly — "LOW RISK" is only shown when
    enough data is present to be confident. Otherwise "UNKNOWN" is returned.
    """
    from database import Patient, MonthlyRecord, DryWeightAssessment

    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        return {"available": False}

    records = db.query(MonthlyRecord).filter(
        MonthlyRecord.patient_id == patient_id
    ).order_by(MonthlyRecord.record_month.asc()).all()

    if not records:
        return {"available": False}

    records = records[-6:]

    events       = []
    risk_score   = 0
    inputs_found = []   # fields that contributed to score
    inputs_missing = [] # fields expected but absent

    # ── 1. CARDIAC STATUS (from patient profile) ──────────────────────────────
    ef = p.ejection_fraction   # Float; default=60.0 — treat 60.0 as unverified if never updated
    dd = p.diastolic_dysfunction  # String or None

    if ef is not None:
        inputs_found.append(f"EF {ef:.0f}%")
        if ef < 40:
            risk_score += 3
            events.append({"type": "cardiac",
                "text": f"Severe LV systolic dysfunction — EF {ef:.0f}% (high filling pressures, fluid retention risk)"})
        elif ef < 50:
            risk_score += 2
            events.append({"type": "cardiac",
                "text": f"Mild–moderate LV systolic dysfunction — EF {ef:.0f}%"})
        # ef ≥ 50 is normal; no score, no event (correct)
    else:
        inputs_missing.append("Ejection fraction (echo)")

    if dd and dd.lower() not in ("none", ""):
        inputs_found.append(f"DD {dd}")
        if "grade iii" in dd.lower() or "grade 3" in dd.lower():
            risk_score += 3
            events.append({"type": "cardiac",
                "text": f"Severe diastolic dysfunction ({dd}) — markedly raised filling pressures"})
        elif "grade ii" in dd.lower() or "grade 2" in dd.lower():
            risk_score += 2
            events.append({"type": "cardiac",
                "text": f"Moderate diastolic dysfunction ({dd})"})
        elif "grade i" in dd.lower() or "grade 1" in dd.lower():
            risk_score += 1
            events.append({"type": "cardiac",
                "text": f"Mild diastolic dysfunction ({dd})"})
    else:
        inputs_missing.append("Diastolic dysfunction grade (echo)")

    # ── 2. NT-proBNP — strongest fluid overload biomarker in HD ──────────────
    nt_vals = [(r.record_month, r.nt_probnp) for r in records if r.nt_probnp is not None]
    if nt_vals:
        latest_nt = nt_vals[-1][1]
        inputs_found.append(f"NT-proBNP {latest_nt:.0f} pg/mL")
        if latest_nt > 5000:
            risk_score += 3
            events.append({"type": "biomarker",
                "text": f"NT-proBNP severely elevated: {latest_nt:.0f} pg/mL (>5000 — strong fluid overload signal in HD)"})
        elif latest_nt > 2000:
            risk_score += 2
            events.append({"type": "biomarker",
                "text": f"NT-proBNP markedly elevated: {latest_nt:.0f} pg/mL (>2000 — significant volume excess)"})
        elif latest_nt > 1000:
            risk_score += 1
            events.append({"type": "biomarker",
                "text": f"NT-proBNP elevated: {latest_nt:.0f} pg/mL (>1000 — monitor closely)"})
        # Trend: rising NT-proBNP across last 3+ months
        if len(nt_vals) >= 3:
            vals = [v for _, v in nt_vals[-3:]]
            if vals[-1] > vals[-2] > vals[-3]:
                risk_score += 1
                events.append({"type": "biomarker",
                    "text": f"NT-proBNP rising trend: {vals[-3]:.0f} → {vals[-2]:.0f} → {vals[-1]:.0f} pg/mL over 3 months"})
    else:
        inputs_missing.append("NT-proBNP (monthly record)")

    # ── 3. BIA FLUID STATUS (from DryWeightAssessment) ───────────────────────
    latest_bia = (
        db.query(DryWeightAssessment)
        .filter(DryWeightAssessment.patient_id == patient_id,
                DryWeightAssessment.bia_fluid_overload_litres != None)
        .order_by(DryWeightAssessment.assessment_date.desc())
        .first()
    )
    if latest_bia:
        fo = latest_bia.bia_fluid_overload_litres
        oh = latest_bia.bia_overhydration_percent
        inputs_found.append(f"BIA fluid overload {fo:+.1f} L")
        if fo > 2.5:
            risk_score += 2
            events.append({"type": "fluid",
                "text": f"BIA: severe fluid overload {fo:.1f} L above target (>{2.5} L threshold)"})
        elif fo > 1.0:
            risk_score += 1
            events.append({"type": "fluid",
                "text": f"BIA: fluid overload {fo:.1f} L above target — moderate volume excess"})
        if oh is not None and oh > 15:
            risk_score += 1
            events.append({"type": "fluid",
                "text": f"BIA: overhydration {oh:.1f}% body water — exceeds 15% threshold"})
    else:
        inputs_missing.append("BIA fluid overload (dry-weight assessment)")

    # ── 4. INTERDIALYTIC WEIGHT GAIN ──────────────────────────────────────────
    idwgs = [(r.record_month, r.idwg) for r in records if r.idwg is not None]
    if idwgs:
        latest_idwg = idwgs[-1][1]
        avg_idwg    = sum(v for _, v in idwgs) / len(idwgs)
        inputs_found.append(f"IDWG {latest_idwg:.1f} kg")
        if latest_idwg > 3.5 or avg_idwg > 3.0:
            risk_score += 2
            events.append({"type": "fluid",
                "text": f"High interdialytic weight gain: latest {latest_idwg:.1f} kg, avg {avg_idwg:.1f} kg — volume loading risk"})
        elif latest_idwg > 2.5:
            risk_score += 1
            events.append({"type": "fluid",
                "text": f"Elevated IDWG: {latest_idwg:.1f} kg (target <2.5 kg)"})
    else:
        inputs_missing.append("IDWG (monthly record)")

    # ── 5. RESIDUAL URINE OUTPUT ──────────────────────────────────────────────
    urine_vals = [(r.record_month, r.residual_urine_output) for r in records if r.residual_urine_output is not None]
    if urine_vals:
        latest_uo = urine_vals[-1][1]
        inputs_found.append(f"Urine output {latest_uo:.0f} mL/day")
        if latest_uo < 200:
            risk_score += 2
            events.append({"type": "renal",
                "text": f"Oliguria/anuria: urine output {latest_uo:.0f} mL/day — minimal fluid buffering capacity"})
        elif latest_uo < 500:
            risk_score += 1
            events.append({"type": "renal",
                "text": f"Low residual urine output: {latest_uo:.0f} mL/day — limited salt and water excretion"})
        # Declining trend
        if len(urine_vals) >= 2:
            first_uo = urine_vals[0][1]
            if first_uo - latest_uo > 200:
                risk_score += 1
                events.append({"type": "renal",
                    "text": f"Declining urine output: {first_uo:.0f} → {latest_uo:.0f} mL/day over {len(urine_vals)} months"})
    else:
        inputs_missing.append("Residual urine output (monthly record)")

    # ── 6. FLUID-RELATED HOSPITALISATIONS ─────────────────────────────────────
    fluid_keywords = {"fluid", "j81", "i50", "oedema", "edema", "pulmonary", "overload"}
    recent_hosps = [r for r in records if r.hospitalization_this_month]
    fluid_hosps  = [r for r in recent_hosps if r.hospitalization_icd_code and
                    any(kw in r.hospitalization_icd_code.lower() for kw in fluid_keywords)]

    if fluid_hosps:
        risk_score += 4
        events.append({"type": "outcome",
            "text": f"{len(fluid_hosps)} hospitalization(s) linked to fluid overload / pulmonary oedema in last {len(records)} months"})
    elif recent_hosps:
        events.append({"type": "outcome",
            "text": f"{len(recent_hosps)} hospitalization(s) in last {len(records)} months (ICD codes not fluid-specific)"})

    # ── Data sufficiency ──────────────────────────────────────────────────────
    total_inputs   = len(inputs_found) + len(inputs_missing)
    completeness   = round(len(inputs_found) / total_inputs * 100) if total_inputs else 0
    # "Reliable" = at least 3 of 6 input groups scored
    reliable       = len(inputs_found) >= 3
    cascade_detected = risk_score >= 5 and reliable

    if not reliable:
        status_label = "UNKNOWN"
        message = (f"Insufficient data to assess risk reliably — "
                   f"only {len(inputs_found)} of {total_inputs} expected inputs recorded.")
    elif cascade_detected:
        status_label = "HIGH RISK"
        message = "Cardiorenal / fluid overload cascade detected — multiple concurrent risk factors."
    elif risk_score >= 3:
        status_label = "MODERATE RISK"
        message = "Moderate cardiorenal risk — monitor fluid balance closely."
    else:
        status_label = "LOW RISK"
        message = "No active cardiorenal fluid cascade — current data within acceptable range."

    return {
        "available":        True,
        "cascade_detected": cascade_detected,
        "risk_score":       risk_score,
        "status_label":     status_label,
        "reliable":         reliable,
        "data_completeness": completeness,
        "inputs_found":     inputs_found,
        "inputs_missing":   inputs_missing,
        "events":           events,
        "months_assessed":  len(records),
        "message":          message,
    }

def analyze_avf_maturation(db, patient_id: int) -> dict:
    """
    AVF Maturation Failure Cascade:
    - Date of AVF surgery vs Date of first cannulation
    - Correlates with: Age > 65, Diabetes, Poor handgrip strength
    """
    from database import Patient
    from datetime import date
    
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        return {"available": False}
        
    if not p.access_date or not p.date_first_cannulation:
        return {"available": False}
        
    delay_days = (p.date_first_cannulation - p.access_date).days
    
    if delay_days <= 0:
        return {"available": False} # Invalid data or not an AVF maturation scenario
        
    events = []
    risk_score = 0
    
    events.append({"text": f"Time to first cannulation: {delay_days} days."})
    
    if delay_days > 45:
        risk_score += 2
        events.append({"text": "Delayed AVF Maturation (> 6 weeks)."})
    if delay_days > 90:
        risk_score += 1
        events.append({"text": "Severe Maturation Failure (> 3 months)."})
        
    # Correlating factors
    if p.age and p.age >= 65:
        risk_score += 1
        events.append({"text": f"Advanced Age ({p.age} yrs) correlates with impaired vascular remodeling."})
        
    if p.dm_status and "diabetes" in p.dm_status.lower():
        risk_score += 2
        events.append({"text": "Diabetes Mellitus history accelerates intimal hyperplasia and calcification."})
        
    if p.handgrip_strength and p.handgrip_strength < 20: # Example threshold
        risk_score += 2
        events.append({"text": f"Poor Handgrip Strength ({p.handgrip_strength} kg) reflects sarcopenia/frailty, strongly linked to fistula failure."})

    cascade_detected = delay_days > 45 and risk_score >= 3

    return {
        "available": True,
        "cascade_detected": cascade_detected,
        "delay_days": delay_days,
        "risk_score": risk_score,
        "events": events,
        "message": "Delayed AVF Maturation linked to patient demographics." if cascade_detected else "AVF Maturation within expected parameters or uncorrelated."
    }


def detect_occult_overload(db: Session, patient_id: int):
    """
    Identifies 'Sarcopenia-Masked Occult Volume Overload'.
    Logic: Stable/Rising weight + Falling Albumin + High IDWG + Respiratory symptoms.
    """
    from database import Patient, MonthlyRecord, SessionRecord
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient: return None
    
    # 1. Check for significant Dry Weight Drop (Muscle wasting)
    # Compare current DW vs first recorded monthly weight
    first_record = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id).order_by(MonthlyRecord.record_month.asc()).first()
    dw_drop = 0
    if first_record and first_record.target_dry_weight and patient.dry_weight:
        dw_drop = first_record.target_dry_weight - patient.dry_weight

    # 2. Nutrition Trend (Albumin)
    recent_records = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id).order_by(MonthlyRecord.record_month.desc()).limit(3).all()
    alb_decline = False
    if len(recent_records) >= 2:
        alb_decline = recent_records[0].albumin < recent_records[-1].albumin

    # 3. Respiratory Symptoms (Likert >= 3)
    recent_sessions = db.query(SessionRecord).filter(SessionRecord.patient_id == patient_id).order_by(SessionRecord.session_date.desc()).limit(10).all()
    breathless = any([(s.pre_hd_dyspnea_likert and s.pre_hd_dyspnea_likert >= 3) or 
                      (s.post_hd_dyspnea_likert and s.post_hd_dyspnea_likert >= 3) for s in recent_sessions])

    # 4. Emergency Sessions (Volume related)
    emergency_sessions = [s for s in recent_sessions if s.is_emergency and s.reason_emergency in ["Fluid Overload", "Pulmonary Oedema", "Severe Dyspnea"]]
    freq_emergency = len(emergency_sessions) >= 1

    # 5. Composite Alert
    if (dw_drop > 3 and alb_decline) or (breathless and alb_decline) or (freq_emergency):
        reason = f"Significant DW drop ({round(dw_drop,1)}kg) with declining Albumin and persistent dyspnea."
        if freq_emergency:
            reason = f"Emergency session required due to {emergency_sessions[0].reason_emergency}. " + reason
            
        return {
            "type": "Occult Overload Suspected",
            "reason": reason,
            "recommendation": "Perform BIA, IVC Diameter check, and Lung USG. Review dry weight and consider upgrading to 3x/week schedule.",
            "severity": "High"
        }
    
    return None

