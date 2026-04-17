"""
ml_analytics.py
===============
Clinical Trend Analysis Engine for Hemodialysis Patients.

Implements OLS linear regression with 95% prediction intervals for
longitudinal lab trend analysis (Hb, Albumin, Phosphorus). When
statsmodels is available, produces full OLS diagnostics: R², adjusted R²,
F-statistic p-value, and Durbin-Watson statistic for autocorrelation
detection — suitable for inclusion in research-grade clinical reporting.

Note: Monthly lab data (n ≤ 12 per patient) is inherently small-sample.
Predictions should be interpreted as clinical trend indicators, not
population-level statistical inferences.
"""
import re
import statistics
import logging
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database import MonthlyRecord, Patient

try:
    from scipy.stats import t as t_dist
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
    Convert any ESA dose string to weekly IU equivalents.

    Returns dict with keys:
      weekly_iu   – float IU/week EPO equivalent, or None
      drug_type   – 'epoetin' | 'darbepoetin' | 'mircera' | 'unknown'
      frequency   – 'weekly' | 'biweekly' | 'monthly' | 'tiw' | 'biw' | 'unknown'
      dose_value  – numeric dose as entered (IU for epoetin, mcg for darbe/mircera)
      original    – raw input string
      confidence  – 'high' | 'low'
    """
    null = {"weekly_iu": None, "drug_type": None, "frequency": None,
            "dose_value": None, "original": None, "confidence": None}
    if not dose_str:
        return null

    s = dose_str.lower().strip()
    
    # Handle 'k' suffix for thousands (e.g. 10k -> 10000)
    s = re.sub(r'(\d+)k\b', lambda m: str(int(m.group(1)) * 1000), s)

    numbers = re.findall(r"\d+(?:\.\d+)?", s)
    if not numbers:
        return {**null, "original": dose_str, "drug_type": "unknown", "confidence": "low"}

    dose_value = float(numbers[0])
    drug_type  = "unknown"
    frequency  = "unknown"
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

    # ── Mircera (methoxy-PEG epoetin beta) ───────────────────────────────────
    if drug_type == "mircera":
        # Default Mircera to monthly if no frequency token found
        if frequency == "unknown":
            frequency = "monthly"

        if frequency == "monthly":
            # monthly_mcg × 50  =  (mcg/month ÷ 4 weeks) × 200 IU/mcg
            weekly_iu = dose_value * 50.0
        elif frequency == "biweekly":
            # biweekly_mcg × 100  =  (mcg/2w ÷ 2 weeks) × 200 IU/mcg
            weekly_iu = dose_value * 100.0

    # ── Darbepoetin alfa ──────────────────────────────────────────────────────
    elif drug_type == "darbepoetin":
        if frequency == "unknown":
            frequency = "weekly"

        if frequency == "weekly":
            weekly_iu = dose_value * 200.0        # 1 mcg/week = 200 IU/week
        elif frequency == "biweekly":
            # biweekly dose ÷ 2 = weekly mcg, then × 200
            weekly_iu = (dose_value / 2) * 200.0

    # ── Epoetin alfa / beta ───────────────────────────────────────────────────
    elif drug_type == "epoetin":
        if frequency in ("tiw", "unknown") and "tiw" in s:
            weekly_iu = dose_value * 3
            frequency = "tiw"
        elif frequency == "biw" or "biw" in s:
            weekly_iu = dose_value * 2
            frequency = "biw"
        else:
            # single weekly dose or ambiguous — treat as per-session × 3 if IU < 10000
            # (most centres dose epoetin TIW; single doses >30000 IU are genuinely weekly)
            if frequency == "unknown":
                frequency = "tiw" if dose_value <= 10000 else "weekly"
                weekly_iu = dose_value * 3 if frequency == "tiw" else dose_value
            else:
                weekly_iu = dose_value

    if weekly_iu is not None:
        weekly_iu = round(weekly_iu, 2)

    return {
        "weekly_iu": weekly_iu,
        "drug_type": drug_type,
        "frequency": frequency,
        "dose_value": dose_value,
        "original": dose_str,
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
    return normalize_epo_dose(dose_str).get("weekly_iu")


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
    trend = _linear_trend_with_ci([p[0] for p in pairs], [p[1] for p in pairs])
    predicted = trend["next_predicted"]
    alert_predicted = predicted is not None and predicted < 10.0

    return {
        **base,
        "ready_for_prediction": True,
        "predicted": predicted,
        "next_predicted": predicted,
        "pi_lower": trend.get("pi_lower"),
        "pi_upper": trend.get("pi_upper"),
        "r_squared": trend.get("r_squared"),
        "adj_r_squared": trend.get("adj_r_squared"),
        "p_value": trend.get("p_value"),
        "durbin_watson": trend.get("durbin_watson"),
        "n_points": trend.get("n_points"),
        "alert_predicted_low": alert_predicted,
        "message": "Predicted to drop below 10 g/dL — review urgently." if alert_predicted else "Hb trajectory acceptable.",
    }


# ── ESA Response Assessment ───────────────────────────────────────────────────

def _resolve_weekly_iu(record: dict) -> Optional[float]:
    """Return weekly IU equivalent from a record, preferring stored value then parsing dose string."""
    stored = record.get("epo_weekly_units")
    if stored is not None:
        return float(stored)
    dose_str = record.get("epo_mircera_dose")
    if dose_str:
        parsed = normalize_epo_dose(dose_str)
        if parsed.get("confidence") == "high":
            return parsed.get("weekly_iu")
    return None


def detect_epo_hyporesponse(df: List[Dict], hb_meta: Dict = None) -> Dict:  # noqa: ARG001
    """
    Assess ESA (Epoetin / Darbepoetin / Mircera) response quality.

    Response classification:
      excellent      Hb ≥ 11.5 g/dL on any dose
      adequate       10 ≤ Hb < 11.5 g/dL
      suboptimal     Hb 10–11.5 but on high dose (>10 000 IU/week)
      hypo-response  Hb < 10 g/dL AND dose > 10 000 IU/week
      severe         Hb < 8.5 g/dL AND dose > 10 000 IU/week

    Returns a dict compatible with the existing analytics API.
    """
    if not df:
        return {"hypo_response": False, "status": "No Data", "class": "warning",
                "message": "No records.", "ready": False, "confidence": "insufficient"}

    # Gate: require 3+ months with BOTH Hb and any ESA dose entry
    complete_pairs = [
        r for r in df
        if r.get("hb") is not None and _resolve_weekly_iu(r) is not None
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
    hb   = latest.get("hb") or 0
    dose = _resolve_weekly_iu(latest) or 0

    # Identify drug type for richer reporting
    drug_type = "unknown"
    dose_str = latest.get("epo_mircera_dose", "")
    if dose_str:
        drug_type = normalize_epo_dose(dose_str).get("drug_type", "unknown")

    # Mircera equivalence band (for display in analytics)
    mircera_equiv = None
    if drug_type != "mircera" and dose > 0:
        mircera_equiv = get_mircera_equivalent(epoetin_weekly_iu=dose)

    # ── Classify response ─────────────────────────────────────────────────────
    hypo_response = False
    severity      = "none"
    response_class = "excellent"

    if dose > 0:
        if hb < 8.5 and dose > 10000:
            hypo_response  = True
            severity       = "severe"
            response_class = "severe"
        elif hb < 10.0 and dose > 10000:
            hypo_response  = True
            severity       = "significant"
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
    dose_display = f"{int(dose):,} IU/week equiv" if dose else "unknown dose"

    if severity == "severe":
        message = (
            f"Severe hypo-response: Hb {hb} g/dL on {drug_label} "
            f"({dose_display}). Urgent: check iron saturation, "
            f"inflammation (CRP), marrow suppression."
        )
    elif severity == "significant":
        message = (
            f"Hypo-response: Hb {hb} g/dL on high-dose {drug_label} "
            f"({dose_display}). Review iron stores, access recirculation, "
            f"compliance, and consider ESA resistance workup."
        )
        if mircera_equiv and drug_type != "mircera":
            message += (
                f" Mircera switch option: "
                f"{mircera_equiv['mircera_monthly_mcg']} mcg/month."
            )
    elif response_class == "suboptimal":
        message = f"Suboptimal Hb {hb} g/dL — consider dose uptitration or iron supplementation."
    elif response_class == "adequate":
        message = f"Adequate response — Hb {hb} g/dL on {drug_label} ({dose_display})."
    else:
        message = f"Excellent ESA response — Hb {hb} g/dL on {drug_label} ({dose_display})."

    css_class = (
        "danger"  if severity in ("severe", "significant") else
        "warning" if response_class == "suboptimal" else
        "success"
    )

    return {
        "hypo_response": hypo_response,
        "severity": severity,
        "response_class": response_class,
        "status": {
            "severe":     "Severe Hypo-Response",
            "significant":"Hypo-Response",
            "suboptimal": "Suboptimal",
            "adequate":   "Adequate",
            "excellent":  "Excellent",
        }.get(response_class, "Unknown"),
        "class": css_class,
        "ready": True,
        "confidence": confidence,
        "n_points": len(complete_pairs),
        "drug_type": drug_type,
        "weekly_iu_equiv": dose,
        "mircera_monthly_equiv": mircera_equiv,
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
    trend = _linear_trend_with_ci([p[0] for p in pairs], [p[1] for p in pairs])
    slope = trend.get("slope") or 0
    predicted = trend["next_predicted"]
    direction = "up" if slope > 0.05 else "down" if slope < -0.05 else "→"
    risk = base["risk"] or (predicted is not None and predicted < 2.5)

    return {
        **base,
        "risk": risk,
        "trend": direction,
        "direction": direction,
        "predicted": predicted,
        "predicted_2m": predicted,
        "pi_lower": trend.get("pi_lower"),
        "pi_upper": trend.get("pi_upper"),
        "r_squared": trend.get("r_squared"),
        "adj_r_squared": trend.get("adj_r_squared"),
        "p_value": trend.get("p_value"),
        "durbin_watson": trend.get("durbin_watson"),
        "n_points": trend.get("n_points", readiness["n_points"]),
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
    Each met target = 1 point. Max score = 10.
    """
    if not df:
        return {"score": 0, "status": "No Data"}
    latest = df[0]
    points = 0
    # 1. Anemia (Hb >= 10)
    if (latest.get("hb") or 0) >= 10:          points += 1
    # 2. Nutrition (Albumin >= 3.5) - Note: KDIGO target is 3.5 but user threshold is 2.5
    if (latest.get("albumin") or 0) >= 3.5:    points += 1
    # 3. Mineral (Phos <= 5.5)
    if (latest.get("phosphorus") or 10) <= 5.5: points += 1
    # 4. Fluid (IDWG <= 2.5)
    if (latest.get("idwg") or 10) <= 2.5:      points += 1
    # 5. Adequacy (URR >= 65%)
    if (latest.get("urr") or 0) >= 65:         points += 1
    # 6. PTH (150 - 600)
    ipth = latest.get("ipth")
    if ipth and 150 <= ipth <= 600:           points += 1
    # 7. Iron Stores (Ferritin >= 200)
    if (latest.get("serum_ferritin") or 0) >= 200: points += 1
    # 8. Iron Utility (TSAT >= 20%)
    if (latest.get("tsat") or 0) >= 20:         points += 1
    # 9. BP Control Max (Sys <= 140)
    if (latest.get("bp_sys") or 200) <= 140:   points += 1
    # 10. BP Control Min (Sys >= 110)
    if (latest.get("bp_sys") or 0) >= 110:     points += 1

    status = "Optimal" if points >= 8 else "Sub-optimal" if points >= 6 else "Critical"
    return {"score": points, "label": status, "status": status}


# ── Deterioration Risk ────────────────────────────────────────────────────────

def compute_deterioration_risk(hb: Dict, alb: Dict, target: Dict) -> Dict:
    risk_score = 0
    factors = []
    if hb.get("alert"):              risk_score += 40; factors.append("Falling Hb")
    if alb.get("risk"):              risk_score += 30; factors.append("Declining Albumin")
    if target.get("score", 0) < 6:  risk_score += 30; factors.append("Low Target Score")
    risk_level = "High" if risk_score >= 60 else "Moderate" if risk_score >= 30 else "Low"
    return {
        "available": True,
        "risk_score": risk_score, "score": risk_score,
        "risk_level": risk_level, "level": risk_level,
        "risk_factors": factors, "factors": factors,
    }


# ── Main Entry Points ─────────────────────────────────────────────────────────

def run_patient_analytics(db: Session, patient_id: int) -> Dict:
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
        }
        for r in records
    ]

    logger.debug("PATIENT %d: loaded %d record(s)", patient_id, len(df))

    if not df:
        return {"status": "no_data"}

    hb_traj    = predict_hb_trajectory(df)
    epo_resp   = detect_epo_hyporesponse(df, hb_traj)
    alb_risk   = assess_albumin_decline(df)
    iron_stat  = classify_iron_status(df[0])
    target_sc  = compute_target_score(df)
    det_risk   = compute_deterioration_risk(hb_traj, alb_risk, target_sc)

    return {
        "status": "ok",
        "hb_trajectory": hb_traj,
        "epo_response": epo_resp,
        "albumin_risk": alb_risk,
        "iron_status": iron_stat,
        "target_score": target_sc,
        "deterioration_risk": det_risk,
        "history_count": len(df),
        "n_months": len(df),
    }


def run_cohort_analytics(db: Session) -> Dict:
    records = db.query(MonthlyRecord).order_by(MonthlyRecord.record_month).all()
    if not records:
        return {"available": False}

    trends: Dict = {}
    for r in records:
        m = r.record_month
        if m not in trends:
            trends[m] = {"hb": [], "alb": [], "phos": []}
        if r.hb:        trends[m]["hb"].append(r.hb)
        if r.albumin:   trends[m]["alb"].append(r.albumin)
        if r.phosphorus: trends[m]["phos"].append(r.phosphorus)

    months = sorted(trends.keys())
    hb_stats, alb_stats, phos_stats = [], [], []
    for m in months:
        for key, stats_list in [("hb", hb_stats), ("alb", alb_stats), ("phos", phos_stats)]:
            vals = trends[m][key]
            if not vals:
                stats_list.append({"median": 0, "p25": 0, "p75": 0})
                continue
            med = statistics.median(vals)
            sv = sorted(vals)
            n = len(sv)
            if n == 1:
                stats_list.append({
                    "median": round(sv[0], 1),
                    "p25": round(sv[0], 1),
                    "p75": round(sv[0], 1),
                    "n": 1
                })
                continue

            stats_list.append({
                "median": round(med, 1),
                "p25": round(sv[int(n * 0.25)], 1),
                "p75": round(sv[int(n * 0.75)], 1),
                "n": n
            })

    return {
        "available": True,
        "months": months,
        "hb": hb_stats,
        "alb": alb_stats,
        "phos": phos_stats,
        "latest_month": months[-1] if months else None,
    }
