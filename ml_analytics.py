"""
ml_analytics.py
===============
Predictive analytics for hemodialysis patients.

Models implemented:
1.  Hb Trajectory Predictor      — next month Hb forecast (linear regression)
2.  EPO Hypo-Response Detector   — flags poor EPO responders
3.  Albumin Decline Risk          — detects downward albumin trend
4.  Phosphorus Spike Predictor   — forecasts next month phosphorus
5.  Target Achievement Score      — 0-10 composite wellness score per patient
6.  Deterioration Risk Score      — combined multi-parameter risk flag
7.  Iron Status Classifier        — iron deficient / adequate / overloaded
8.  Trend Direction Indicators    — ↑ ↓ → for every parameter
9.  Cohort Percentile Ranking     — where does patient sit vs cohort
10. Data Completeness Score       — % of key fields filled

All models degrade gracefully with limited data:
  - 1 data point  : shows value, no trend
  - 2 data points : shows direction
  - 3+ points     : full regression + prediction
  - 6+ points     : high confidence predictions
"""

import os
import sys
import logging
import json
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── CLINICAL TARGETS ────────────────────────────────────────────────────────
TARGETS = {
    "hb":          {"low": 10.0, "high": 12.0,  "unit": "g/dL"},
    "albumin":     {"low": 3.5,  "high": None,   "unit": "g/dL"},
    "phosphorus":  {"low": None, "high": 5.5,    "unit": "mg/dL"},
    "ipth":        {"low": 150,  "high": 300,    "unit": "pg/mL"},
    "vit_d":       {"low": 20,   "high": None,   "unit": "ng/mL"},
    "tsat":        {"low": 30,   "high": None,   "unit": "%"},
    "ferritin":    {"low": 200,  "high": 500,    "unit": "ng/mL"},
    "idwg":        {"low": None, "high": 2.5,    "unit": "kg"},
    "calcium":     {"low": 8.5,  "high": 10.5,  "unit": "mg/dL"},
}

KEY_FIELDS = ["hb", "albumin", "phosphorus", "tsat",
              "serum_ferritin", "calcium", "ipth", "vit_d", "idwg"]


# ── DATA LOADING ─────────────────────────────────────────────────────────────

def load_patient_history(db: Session, patient_id: int) -> pd.DataFrame:
    """
    Load all monthly records for a patient as a sorted DataFrame.
    Returns empty DataFrame if no records exist.
    """
    from database import MonthlyRecord

    records = (
        db.query(MonthlyRecord)
        .filter(MonthlyRecord.patient_id == patient_id)
        .order_by(MonthlyRecord.record_month.asc())
        .all()
    )

    if not records:
        return pd.DataFrame()

    rows = []
    for r in records:
        rows.append({
            "month":            r.record_month,
            "month_num":        _month_to_num(r.record_month),
            "idwg":             r.idwg,
            "hb":               r.hb,
            "serum_ferritin":   r.serum_ferritin,
            "tsat":             r.tsat,
            "calcium":          r.calcium,
            "phosphorus":       r.phosphorus,
            "albumin":          r.albumin,
            "ipth":             r.ipth,
            "vit_d":            r.vit_d,
            "ast":              r.ast,
            "alt":              r.alt,
            "av_daily_calories":r.av_daily_calories,
            "av_daily_protein": r.av_daily_protein,
            "epo_dose_raw":     r.epo_mircera_dose,
            "epo_dose_num":     _parse_epo_dose(r.epo_mircera_dose),
        })

    return pd.DataFrame(rows)


def load_cohort_latest(db: Session, month_str: Optional[str] = None) -> pd.DataFrame:
    """Load latest record per patient for cohort-level analysis."""
    from database import MonthlyRecord, Patient

    if month_str is None:
        from dashboard_logic import get_current_month_str
        month_str = get_current_month_str()

    records = (
        db.query(MonthlyRecord, Patient)
        .join(Patient, MonthlyRecord.patient_id == Patient.id)
        .filter(
            MonthlyRecord.record_month == month_str,
            Patient.is_active == True
        )
        .all()
    )

    rows = []
    for rec, pat in records:
        rows.append({
            "patient_id":   pat.id,
            "name":         pat.name,
            "hb":           rec.hb,
            "albumin":      rec.albumin,
            "phosphorus":   rec.phosphorus,
            "idwg":         rec.idwg,
            "tsat":         rec.tsat,
            "serum_ferritin": rec.serum_ferritin,
            "ipth":         rec.ipth,
            "vit_d":        rec.vit_d,
            "calcium":      rec.calcium,
        })

    return pd.DataFrame(rows)


# ── HELPER FUNCTIONS ─────────────────────────────────────────────────────────

def _month_to_num(month_str: str) -> int:
    """Convert YYYY-MM to integer for regression. 2025-01 → 25001."""
    try:
        y, m = month_str.split("-")
        return int(y) * 100 + int(m)
    except Exception:
        return 0


def _parse_epo_dose(dose_str: Optional[str]) -> Optional[float]:
    """
    Extract numeric EPO dose from text.
    'EPO 4000u TIW' → 4000
    'Mircera 100mcg monthly' → 100
    'EPO 6000u TIW' → 6000
    """
    if not dose_str:
        return None
    import re
    numbers = re.findall(r"\d+(?:\.\d+)?", dose_str)
    if numbers:
        return float(numbers[0])
    return None


def _linear_trend(x: list, y: list) -> dict:
    """
    Fit linear regression on x, y.
    Returns slope, intercept, next_predicted, r_squared, direction.
    Requires at least 2 non-null points.
    """
    pairs = [(xi, yi) for xi, yi in zip(x, y) if yi is not None]
    if len(pairs) < 2:
        return {
            "slope": None, "intercept": None,
            "next_predicted": None, "r_squared": None,
            "direction": "→", "confidence": "insufficient_data",
            "n_points": len(pairs)
        }

    xs = np.array([p[0] for p in pairs], dtype=float)
    ys = np.array([p[1] for p in pairs], dtype=float)

    # Normalize x for numerical stability
    x_min = xs.min()
    xs_norm = xs - x_min

    # Fit
    coeffs = np.polyfit(xs_norm, ys, 1)
    slope = coeffs[0]
    intercept = coeffs[1]

    # Predict next month
    next_x = xs_norm.max() + 1
    next_predicted = slope * next_x + intercept

    # R-squared
    y_pred = slope * xs_norm + intercept
    ss_res = np.sum((ys - y_pred) ** 2)
    ss_tot = np.sum((ys - np.mean(ys)) ** 2)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

    # Direction (per unit = per month)
    if abs(slope) < 0.05:
        direction = "→"
    elif slope > 0:
        direction = "↑"
    else:
        direction = "↓"

    # Confidence based on data points and R²
    n = len(pairs)
    if n >= 6 and r_squared > 0.7:
        confidence = "high"
    elif n >= 3 and r_squared > 0.4:
        confidence = "moderate"
    else:
        confidence = "low"

    return {
        "slope": round(slope, 4),
        "intercept": round(intercept, 4),
        "next_predicted": round(float(next_predicted), 2),
        "r_squared": round(float(r_squared), 3),
        "direction": direction,
        "confidence": confidence,
        "n_points": n,
    }


def _in_target(value, param: str) -> Optional[bool]:
    """Check if a value is within clinical target range."""
    if value is None:
        return None
    t = TARGETS.get(param, {})
    low  = t.get("low")
    high = t.get("high")
    if low and value < low:
        return False
    if high and value > high:
        return False
    return True


# ── MODEL 1: HB TRAJECTORY PREDICTOR ────────────────────────────────────────

def predict_hb_trajectory(df: pd.DataFrame) -> dict:
    """
    Predict next month Hb using linear regression on history.
    Also detects if predicted Hb will cross below 10 g/dL.
    """
    if df.empty or "hb" not in df.columns:
        return {"available": False, "reason": "no_data"}

    result = _linear_trend(
        df["month_num"].tolist(),
        df["hb"].tolist()
    )
    result["available"] = True
    result["param"] = "hb"
    result["unit"] = "g/dL"
    result["current"] = df["hb"].dropna().iloc[-1] if df["hb"].dropna().shape[0] > 0 else None
    result["target_low"] = 10.0
    result["target_high"] = 12.0

    if result["next_predicted"] is not None:
        result["alert_predicted_low"] = result["next_predicted"] < 10.0
        result["alert_predicted_high"] = result["next_predicted"] > 12.0
    else:
        result["alert_predicted_low"] = False
        result["alert_predicted_high"] = False

    return result


# ── MODEL 2: EPO HYPO-RESPONSE DETECTOR ─────────────────────────────────────

def detect_epo_hyporesponse(df: pd.DataFrame) -> dict:
    """
    EPO hypo-response: Hb not rising (or falling) despite stable/increasing EPO dose.
    Criteria: last 3 months, EPO dose stable or increased, Hb change < +0.5 g/dL.
    Returns severity: none / mild / significant / severe
    """
    if df.empty or df.shape[0] < 3:
        return {"available": False, "reason": "need_3_months"}

    last3 = df.tail(3).copy()
    hb_values    = last3["hb"].dropna().tolist()
    dose_values  = last3["epo_dose_num"].dropna().tolist()

    if len(hb_values) < 2 or len(dose_values) < 2:
        return {"available": False, "reason": "missing_hb_or_dose"}

    hb_change   = hb_values[-1] - hb_values[0]
    dose_change = dose_values[-1] - dose_values[0]

    # Hypo-response: dose went up (or stable) but Hb didn't improve
    if dose_change >= 0 and hb_change < 0.5:
        if hb_values[-1] < 9.0:
            severity = "severe"
            recommendation = (
                "Hb critically low despite ESA. "
                "Investigate: iron deficiency (check TSAT), "
                "infection/inflammation (CRP), access recirculation, "
                "folate/B12 deficiency, compliance."
            )
        elif hb_values[-1] < 10.0:
            severity = "significant"
            recommendation = (
                "Hb below target despite stable/increased ESA dose. "
                "Check iron stores (TSAT ideally >30%), "
                "rule out occult blood loss or infection."
            )
        else:
            severity = "mild"
            recommendation = (
                "Hb response to ESA suboptimal. "
                "Optimise iron stores before increasing ESA dose further."
            )
        hypo_response = True
    else:
        severity = "none"
        recommendation = "ESA response appears adequate."
        hypo_response = False

    return {
        "available": True,
        "hypo_response": hypo_response,
        "severity": severity,
        "hb_change_3m": round(hb_change, 2),
        "dose_change_3m": dose_change,
        "current_hb": hb_values[-1],
        "recommendation": recommendation,
    }


# ── MODEL 3: ALBUMIN DECLINE RISK ────────────────────────────────────────────

def assess_albumin_decline(df: pd.DataFrame) -> dict:
    """
    Detect downward albumin trend. Flag if trajectory predicts
    albumin crossing below 3.5 within 2 months.
    """
    if df.empty or "albumin" not in df.columns:
        return {"available": False, "reason": "no_data"}

    trend = _linear_trend(df["month_num"].tolist(), df["albumin"].tolist())
    trend["available"] = True
    trend["param"] = "albumin"

    current = df["albumin"].dropna().iloc[-1] if df["albumin"].dropna().shape[0] > 0 else None
    trend["current"] = current

    # Predict 2 months ahead
    if trend["slope"] is not None and current is not None:
        predicted_2m = current + trend["slope"] * 2
        trend["predicted_2m"] = round(predicted_2m, 2)
        trend["risk_crossing_35"] = predicted_2m < 3.5
        trend["risk_crossing_25"] = predicted_2m < 2.5

        if predicted_2m < 2.5:
            trend["risk_level"] = "high"
            trend["recommendation"] = (
                "Albumin trajectory indicates severe hypoalbuminaemia within 2 months. "
                "Urgent dietitian referral, consider intradialytic parenteral nutrition."
            )
        elif predicted_2m < 3.5:
            trend["risk_level"] = "moderate"
            trend["recommendation"] = (
                "Albumin declining toward threshold. "
                "Review dietary protein intake, consider oral supplements."
            )
        else:
            trend["risk_level"] = "low"
            trend["recommendation"] = "Albumin trajectory stable."
    else:
        trend["predicted_2m"] = None
        trend["risk_crossing_35"] = False
        trend["risk_crossing_25"] = False
        trend["risk_level"] = "unknown"
        trend["recommendation"] = "Insufficient data for trend."

    return trend


# ── MODEL 4: PHOSPHORUS SPIKE PREDICTOR ─────────────────────────────────────

def predict_phosphorus(df: pd.DataFrame) -> dict:
    """Forecast next month phosphorus and flag if predicted > 5.5."""
    if df.empty:
        return {"available": False, "reason": "no_data"}

    trend = _linear_trend(df["month_num"].tolist(), df["phosphorus"].tolist())
    trend["available"] = True
    trend["param"] = "phosphorus"
    trend["alert_threshold"] = 5.5

    current = df["phosphorus"].dropna().iloc[-1] if df["phosphorus"].dropna().shape[0] > 0 else None
    trend["current"] = current

    if trend["next_predicted"] is not None:
        trend["alert_next_month"] = trend["next_predicted"] > 5.5
        if trend["alert_next_month"] and trend["direction"] == "↑":
            trend["recommendation"] = (
                "Rising phosphorus trend. "
                "Review phosphate binder compliance and dietary phosphorus intake "
                "before next month's review."
            )
        else:
            trend["recommendation"] = "Phosphorus trend stable or improving."
    else:
        trend["alert_next_month"] = False
        trend["recommendation"] = "Insufficient data."

    return trend


# ── MODEL 5: TARGET ACHIEVEMENT SCORE ────────────────────────────────────────

def compute_target_score(df: pd.DataFrame) -> dict:
    """
    Score 0–10 based on how many parameters are in target range.
    Uses most recent record. Tracks score over time.
    """
    if df.empty:
        return {"available": False, "score": None, "trend": None}

    latest = df.iloc[-1]

    checks = {
        "hb":         _in_target(latest.get("hb"), "hb"),
        "albumin":    _in_target(latest.get("albumin"), "albumin"),
        "phosphorus": _in_target(latest.get("phosphorus"), "phosphorus"),
        "tsat":       _in_target(latest.get("tsat"), "tsat"),
        "ferritin":   _in_target(latest.get("serum_ferritin"), "ferritin"),
        "calcium":    _in_target(latest.get("calcium"), "calcium"),
        "idwg":       _in_target(latest.get("idwg"), "idwg"),
        "ipth":       _in_target(latest.get("ipth"), "ipth"),
        "vit_d":      _in_target(latest.get("vit_d"), "vit_d"),
    }

    scored = {k: v for k, v in checks.items() if v is not None}
    if not scored:
        return {"available": False, "score": None}

    n_in_target = sum(1 for v in scored.values() if v)
    score = round((n_in_target / len(scored)) * 10, 1)

    # Historical scores
    historical_scores = []
    for _, row in df.iterrows():
        row_checks = {
            "hb":         _in_target(row.get("hb"), "hb"),
            "albumin":    _in_target(row.get("albumin"), "albumin"),
            "phosphorus": _in_target(row.get("phosphorus"), "phosphorus"),
            "idwg":       _in_target(row.get("idwg"), "idwg"),
        }
        row_scored = {k: v for k, v in row_checks.items() if v is not None}
        if row_scored:
            s = round((sum(1 for v in row_scored.values() if v) / len(row_scored)) * 10, 1)
            historical_scores.append({"month": row["month"], "score": s})

    score_trend = "→"
    if len(historical_scores) >= 2:
        delta = historical_scores[-1]["score"] - historical_scores[-2]["score"]
        if delta > 0.5:
            score_trend = "↑"
        elif delta < -0.5:
            score_trend = "↓"

    label = "Excellent" if score >= 8 else "Good" if score >= 6 else "Fair" if score >= 4 else "Poor"

    return {
        "available": True,
        "score": score,
        "label": label,
        "score_trend": score_trend,
        "checks": checks,
        "n_scored": len(scored),
        "n_in_target": n_in_target,
        "historical": historical_scores,
    }


# ── MODEL 6: DETERIORATION RISK SCORE ────────────────────────────────────────

def compute_deterioration_risk(df: pd.DataFrame) -> dict:
    """
    Combined risk score using multiple declining parameters.
    Clinically: patients with simultaneous decline across multiple
    parameters are at highest risk of hospitalisation/adverse outcome.

    Risk factors (each adds to score):
      +2 Hb < 9 or falling trend
      +2 Albumin < 3.0 or falling trend
      +1 Phosphorus > 6.5 or rising trend
      +1 IDWG > 3.0 or rising trend
      +1 iPTH > 600
      +1 Vit D < 12
      +2 EPO hypo-response (severe)
    """
    if df.empty:
        return {"available": False, "risk_score": None}

    latest = df.iloc[-1]
    risk_score = 0
    risk_factors = []

    # Hb
    hb = latest.get("hb")
    hb_trend = _linear_trend(df["month_num"].tolist(), df["hb"].tolist())
    if hb is not None and hb < 9.0:
        risk_score += 2
        risk_factors.append("Critical anaemia (Hb < 9)")
    elif hb_trend["direction"] == "↓" and hb_trend["n_points"] >= 3:
        risk_score += 1
        risk_factors.append("Declining Hb trend")

    # Albumin
    alb = latest.get("albumin")
    alb_trend = _linear_trend(df["month_num"].tolist(), df["albumin"].tolist())
    if alb is not None and alb < 3.0:
        risk_score += 2
        risk_factors.append("Severe hypoalbuminaemia (< 3.0)")
    elif alb_trend["direction"] == "↓" and alb_trend["n_points"] >= 3:
        risk_score += 1
        risk_factors.append("Declining albumin trend")

    # Phosphorus
    phos = latest.get("phosphorus")
    phos_trend = _linear_trend(df["month_num"].tolist(), df["phosphorus"].tolist())
    if phos is not None and phos > 6.5:
        risk_score += 1
        risk_factors.append("Severe hyperphosphataemia (> 6.5)")
    elif phos_trend["direction"] == "↑" and phos_trend["n_points"] >= 3:
        risk_score += 1
        risk_factors.append("Rising phosphorus trend")

    # IDWG
    idwg = latest.get("idwg")
    idwg_trend = _linear_trend(df["month_num"].tolist(), df["idwg"].tolist())
    if idwg is not None and idwg > 3.0:
        risk_score += 1
        risk_factors.append("High IDWG (> 3.0 kg)")
    elif idwg_trend["direction"] == "↑" and idwg_trend["n_points"] >= 3:
        risk_score += 1
        risk_factors.append("Rising IDWG trend")

    # iPTH
    ipth = latest.get("ipth")
    if ipth is not None and ipth > 600:
        risk_score += 1
        risk_factors.append("Severely elevated iPTH (> 600)")

    # Vit D
    vit_d = latest.get("vit_d")
    if vit_d is not None and vit_d < 12:
        risk_score += 1
        risk_factors.append("Severe Vit D deficiency (< 12)")

    # EPO response
    epo_result = detect_epo_hyporesponse(df)
    if epo_result.get("severity") == "severe":
        risk_score += 2
        risk_factors.append("Severe EPO hypo-response")

    # Risk categorisation
    if risk_score >= 6:
        risk_level = "HIGH"
        risk_color = "#c62828"
        action = "Urgent clinical review recommended within 2 weeks."
    elif risk_score >= 3:
        risk_level = "MODERATE"
        risk_color = "#e65100"
        action = "Increased monitoring. Review at next scheduled session."
    elif risk_score >= 1:
        risk_level = "LOW"
        risk_color = "#2e7d32"
        action = "Continue current management."
    else:
        risk_level = "MINIMAL"
        risk_color = "#1565c0"
        action = "Patient parameters stable."

    return {
        "available": True,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_color": risk_color,
        "risk_factors": risk_factors,
        "action": action,
        "n_factors": len(risk_factors),
    }


# ── MODEL 7: IRON STATUS CLASSIFIER ─────────────────────────────────────────

def classify_iron_status(df: pd.DataFrame) -> dict:
    """
    Classify iron status from Ferritin + TSAT.
    Categories: Absolute deficiency / Functional deficiency /
                Adequate / Overloaded
    """
    if df.empty:
        return {"available": False}

    latest = df.iloc[-1]
    ferritin = latest.get("serum_ferritin")
    tsat     = latest.get("tsat")
    hb       = latest.get("hb")

    if ferritin is None and tsat is None:
        return {"available": False, "reason": "no_iron_data"}

    if ferritin is not None and ferritin < 100:
        status = "Absolute Iron Deficiency"
        color  = "#c62828"
        recommendation = "IV iron replacement indicated regardless of TSAT."
    elif ferritin is not None and tsat is not None and ferritin < 500 and tsat < 20:
        status = "Functional Iron Deficiency"
        color  = "#e65100"
        recommendation = (
            "IV iron trial recommended. "
            "Ferritin adequate but TSAT low suggests functional deficiency."
        )
    elif ferritin is not None and ferritin > 800 and tsat is not None and tsat > 50:
        status = "Iron Overload"
        color  = "#6a1b9a"
        recommendation = "Hold IV iron. Risk of iron toxicity. Check for inflammation."
    elif ferritin is not None and ferritin > 500:
        status = "Iron Replete / Inflamed"
        color  = "#f57f17"
        recommendation = (
            "High ferritin may reflect inflammation rather than iron stores. "
            "Check CRP. TSAT more reliable guide to iron adequacy."
        )
    else:
        status = "Adequate"
        color  = "#2e7d32"
        recommendation = "Iron stores within target range."

    return {
        "available": True,
        "status": status,
        "color": color,
        "ferritin": ferritin,
        "tsat": tsat,
        "recommendation": recommendation,
    }


# ── MODEL 8: TREND DIRECTION INDICATORS ──────────────────────────────────────

def compute_all_trends(df: pd.DataFrame) -> dict:
    """Compute trend direction for all key parameters."""
    if df.empty:
        return {}

    x = df["month_num"].tolist()
    params = ["hb", "albumin", "phosphorus", "idwg",
              "serum_ferritin", "tsat", "ipth", "vit_d",
              "calcium", "av_daily_protein"]

    trends = {}
    for p in params:
        if p in df.columns:
            t = _linear_trend(x, df[p].tolist())
            trends[p] = {
                "direction":      t["direction"],
                "slope":          t["slope"],
                "confidence":     t["confidence"],
                "n_points":       t["n_points"],
                "next_predicted": t["next_predicted"],
            }

    return trends


# ── MODEL 9: COHORT PERCENTILE RANKING ───────────────────────────────────────

def compute_cohort_percentiles(
    db: Session, patient_id: int, month_str: Optional[str] = None
) -> dict:
    """
    Rank patient against cohort for each parameter.
    Returns percentile (0-100) for each key metric.
    """
    cohort_df = load_cohort_latest(db, month_str)

    if cohort_df.empty or cohort_df.shape[0] < 3:
        return {"available": False, "reason": "insufficient_cohort_data"}

    patient_row = cohort_df[cohort_df["patient_id"] == patient_id]
    if patient_row.empty:
        return {"available": False, "reason": "patient_not_in_cohort"}

    percentiles = {}
    for param in ["hb", "albumin", "phosphorus", "idwg", "tsat", "ipth"]:
        cohort_vals = cohort_df[param].dropna().tolist()
        patient_val = patient_row[param].values[0]

        if patient_val is None or len(cohort_vals) < 3:
            percentiles[param] = None
            continue

        # Percentile rank
        n_below = sum(1 for v in cohort_vals if v < patient_val)
        pct = round((n_below / len(cohort_vals)) * 100)

        # For parameters where lower is better (phosphorus, idwg),
        # invert so higher percentile = better
        inverted_params = {"phosphorus", "idwg"}
        display_pct = (100 - pct) if param in inverted_params else pct

        percentiles[param] = {
            "value": patient_val,
            "percentile": pct,
            "display_percentile": display_pct,
            "cohort_n": len(cohort_vals),
            "cohort_median": round(float(np.median(cohort_vals)), 2),
            "cohort_mean": round(float(np.mean(cohort_vals)), 2),
        }

    return {"available": True, "percentiles": percentiles}


# ── MODEL 10: DATA COMPLETENESS ───────────────────────────────────────────────

def compute_data_completeness(df: pd.DataFrame) -> dict:
    """Score data completeness — missing fields reduce ML accuracy."""
    if df.empty:
        return {"score": 0, "missing_fields": KEY_FIELDS, "n_records": 0}

    n_records = len(df)
    field_completeness = {}

    for field in KEY_FIELDS:
        if field in df.columns:
            filled = df[field].notna().sum()
            pct = round((filled / n_records) * 100)
            field_completeness[field] = pct
        else:
            field_completeness[field] = 0

    overall = round(sum(field_completeness.values()) / len(field_completeness))
    missing = [f for f, pct in field_completeness.items() if pct < 50]

    return {
        "score": overall,
        "n_records": n_records,
        "field_completeness": field_completeness,
        "missing_fields": missing,
        "ml_ready": n_records >= 3 and overall >= 60,
        "high_confidence": n_records >= 6 and overall >= 80,
    }


# ── MASTER FUNCTION ────────────────────────────────────────────────────────

def run_patient_analytics(
    db: Session,
    patient_id: int,
    month_str: Optional[str] = None
) -> dict:
    """
    Run all analytics models for a single patient.
    This is the main function called by the API endpoint.
    """
    df = load_patient_history(db, patient_id)

    if df.empty:
        return {
            "available": False,
            "reason": "No monthly records found for this patient.",
            "patient_id": patient_id,
        }

    try:
        result = {
            "available": True,
            "patient_id": patient_id,
            "n_months": len(df),
            "months": df["month"].tolist(),

            # Core predictions
            "hb_trajectory":       predict_hb_trajectory(df),
            "phosphorus_forecast":  predict_phosphorus(df),
            "albumin_decline":      assess_albumin_decline(df),

            # Clinical assessments
            "epo_response":         detect_epo_hyporesponse(df),
            "iron_status":          classify_iron_status(df),
            "deterioration_risk":   compute_deterioration_risk(df),
            "target_score":         compute_target_score(df),

            # Trend indicators for all parameters
            "trends":               compute_all_trends(df),

            # Data quality
            "data_completeness":    compute_data_completeness(df),

            # Cohort comparison
            "cohort_percentiles":   compute_cohort_percentiles(
                                        db, patient_id, month_str),

            # Raw data for charts (all months, all values)
            "chart_data": {
                "months":       df["month"].tolist(),
                "hb":           df["hb"].tolist(),
                "albumin":      df["albumin"].tolist(),
                "phosphorus":   df["phosphorus"].tolist(),
                "idwg":         df["idwg"].tolist(),
                "serum_ferritin": df["serum_ferritin"].tolist(),
                "tsat":         df["tsat"].tolist(),
                "ipth":         df["ipth"].tolist(),
                "vit_d":        df["vit_d"].tolist(),
                "calcium":      df["calcium"].tolist(),
                "epo_dose":     df["epo_dose_num"].tolist(),
                "epo_dose_raw": df["epo_dose_raw"].tolist(),
                "protein":      df["av_daily_protein"].tolist(),
            }
        }
    except Exception as e:
        logger.error(f"Analytics error for patient {patient_id}: {e}")
        result = {
            "available": False,
            "reason": f"Analytics error: {str(e)}",
            "patient_id": patient_id,
        }

    return result


# ── COHORT-LEVEL ANALYTICS ────────────────────────────────────────────────────

def run_cohort_analytics(db: Session) -> dict:
    """
    Run unit-wide analytics for the dashboard cohort panel.
    Returns median trends for last 12 months.
    """
    from database import MonthlyRecord, Patient

    records = (
        db.query(MonthlyRecord, Patient)
        .join(Patient, MonthlyRecord.patient_id == Patient.id)
        .filter(Patient.is_active == True)
        .order_by(MonthlyRecord.record_month.asc())
        .all()
    )

    if not records:
        return {"available": False}

    rows = []
    for rec, pat in records:
        rows.append({
            "month":      rec.record_month,
            "patient_id": pat.id,
            "hb":         rec.hb,
            "albumin":    rec.albumin,
            "phosphorus": rec.phosphorus,
            "idwg":       rec.idwg,
            "ipth":       rec.ipth,
        })

    df = pd.DataFrame(rows)
    months = sorted(df["month"].unique())[-12:]  # last 12 months
    df = df[df["month"].isin(months)]

    cohort_trends = {}
    for param in ["hb", "albumin", "phosphorus"]:
        monthly = []
        for month in months:
            vals = df[df["month"] == month][param].dropna().tolist()
            if vals:
                monthly.append({
                    "month":  month,
                    "median": round(float(np.median(vals)), 2),
                    "p25":    round(float(np.percentile(vals, 25)), 2),
                    "p75":    round(float(np.percentile(vals, 75)), 2),
                    "mean":   round(float(np.mean(vals)), 2),
                    "n":      len(vals),
                })
        cohort_trends[param] = monthly

    # Unit-level summary stats
    latest_month = months[-1] if months else None
    latest = df[df["month"] == latest_month] if latest_month else pd.DataFrame()

    summary = {}
    for param in ["hb", "albumin", "phosphorus", "idwg"]:
        vals = latest[param].dropna().tolist() if not latest.empty else []
        t = TARGETS.get(param, {})
        in_target = 0
        if vals and t:
            for v in vals:
                if (not t.get("low") or v >= t["low"]) and \
                   (not t.get("high") or v <= t["high"]):
                    in_target += 1
        summary[param] = {
            "median": round(float(np.median(vals)), 2) if vals else None,
            "pct_in_target": round(in_target / len(vals) * 100) if vals else None,
            "n": len(vals),
        }

    return {
        "available": True,
        "months": months,
        "cohort_trends": cohort_trends,
        "latest_month": latest_month,
        "summary": summary,
    }
