"""Vascular Access Intelligence service.

Aggregates per-session vascular metrics into clinically actionable trends:
  - Dynamic venous pressure monitoring
  - Access flow (Qa) trends with decline detection
  - Recirculation % trending (KDOQI alert > 10%)
  - Cannulation difficulty distribution and failure-rate tracking
  - Hemostasis time trend
  - Aneurysm flag longitudinal tracking

All functions operate on pre-fetched session data to avoid N+1 queries.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from database import Patient, SessionRecord


# ── KDOQI / clinical thresholds ───────────────────────────────────────────────
_RECIRC_ALERT_PCT: float = 10.0      # recirculation > 10% = significant (KDOQI)
_FLOW_DECLINE_THRESHOLD: float = 0.20  # >20% Qa decline from baseline = alert
_VENOUS_PRESSURE_HIGH: float = 250.0  # mmHg — rising VP suggests downstream stenosis
_HEMOSTASIS_PROLONGED_MINS: float = 20.0  # > 20 min hemostasis time = concern
_CANNULATION_DIFFICULT_RATE: float = 0.25  # ≥25% difficult/failed sessions = alert


def _safe_mean(values: List[float]) -> Optional[float]:
    valid = [v for v in values if v is not None]
    return round(statistics.mean(valid), 2) if valid else None


def _trend_direction(values: List[Optional[float]]) -> str:
    valid = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(valid) < 3:
        return "insufficient_data"
    x_mean = sum(i for i, _ in valid) / len(valid)
    y_mean = sum(v for _, v in valid) / len(valid)
    num = sum((i - x_mean) * (v - y_mean) for i, v in valid)
    den = sum((i - x_mean) ** 2 for i, _ in valid)
    if den == 0:
        return "stable"
    slope = num / den
    # Normalise slope relative to mean
    rel = slope / y_mean if y_mean else 0
    if rel > 0.03:
        return "increasing"
    if rel < -0.03:
        return "decreasing"
    return "stable"


def compute_patient_vascular_intelligence(
    db: Session,
    patient_id: int,
    lookback_months: int = 3,
) -> Dict[str, Any]:
    """
    Compute the full vascular intelligence profile for a single patient.

    Parameters
    ----------
    lookback_months : int
        How many calendar months of sessions to include (default: 3).
    """
    from datetime import date, timedelta

    # Build cutoff record_month string
    today = date.today()
    cutoff = today.replace(day=1)
    for _ in range(lookback_months - 1):
        cutoff = (cutoff - timedelta(days=1)).replace(day=1)
    cutoff_str = cutoff.strftime("%Y-%m")

    sessions: List[SessionRecord] = (
        db.query(SessionRecord)
        .filter(
            SessionRecord.patient_id == patient_id,
            SessionRecord.record_month >= cutoff_str,
        )
        .order_by(SessionRecord.session_date)
        .all()
    )

    total = len(sessions)

    # ── 1. Venous pressure trend ──────────────────────────────────────────────
    vp_series: List[Tuple[str, float]] = [
        (str(s.session_date), s.venous_line_pressure)
        for s in sessions
        if s.venous_line_pressure is not None
    ]
    vp_values = [v for _, v in vp_series]
    vp_trend = _trend_direction(vp_values)
    vp_mean = _safe_mean(vp_values)
    vp_alert = vp_trend == "increasing" and (vp_mean or 0) > _VENOUS_PRESSURE_HIGH * 0.8

    # ── 2. Access flow (Qa) trend ─────────────────────────────────────────────
    flow_series: List[Tuple[str, float]] = [
        (str(s.session_date), s.access_flow_qa)
        for s in sessions
        if s.access_flow_qa is not None
    ]
    flow_values = [v for _, v in flow_series]
    flow_trend = _trend_direction(flow_values)
    flow_alert = False
    flow_baseline: Optional[float] = None
    flow_current: Optional[float] = None
    if len(flow_values) >= 4:
        mid = len(flow_values) // 2
        flow_baseline = _safe_mean(flow_values[:mid])
        flow_current = _safe_mean(flow_values[mid:])
        if flow_baseline and flow_current:
            pct_decline = (flow_baseline - flow_current) / flow_baseline
            flow_alert = pct_decline >= _FLOW_DECLINE_THRESHOLD

    # ── 3. Recirculation % ────────────────────────────────────────────────────
    recirc_series: List[Tuple[str, float]] = [
        (str(s.session_date), s.access_recirculation_percent)
        for s in sessions
        if s.access_recirculation_percent is not None
    ]
    recirc_values = [v for _, v in recirc_series]
    recirc_latest = recirc_series[-1][1] if recirc_series else None
    recirc_alert = recirc_latest is not None and recirc_latest > _RECIRC_ALERT_PCT
    # Alert if ANY recent 5 readings exceed threshold
    recent_recirc = recirc_values[-5:]
    recirc_any_high = any(v > _RECIRC_ALERT_PCT for v in recent_recirc)

    # ── 4. Cannulation difficulty ─────────────────────────────────────────────
    difficulty_counts: Dict[str, int] = defaultdict(int)
    for s in sessions:
        key = (s.cannulation_difficulty or "routine").lower()
        difficulty_counts[key] += 1

    avf_sessions = [s for s in sessions if s.cannulation_difficulty is not None]
    failed_or_difficult = difficulty_counts.get("difficult", 0) + difficulty_counts.get("failed", 0)
    cannulation_alert = False
    if avf_sessions:
        rate = failed_or_difficult / len(avf_sessions)
        cannulation_alert = rate >= _CANNULATION_DIFFICULT_RATE

    infiltration_count = sum(1 for s in sessions if s.needle_infiltration)

    # ── 5. Hemostasis time ────────────────────────────────────────────────────
    hemostasis_series: List[Tuple[str, float]] = [
        (str(s.session_date), s.hemostasis_time_mins)
        for s in sessions
        if getattr(s, "hemostasis_time_mins", None) is not None
    ]
    hemostasis_values = [v for _, v in hemostasis_series]
    hemostasis_mean = _safe_mean(hemostasis_values)
    hemostasis_trend = _trend_direction(hemostasis_values)
    hemostasis_alert = hemostasis_mean is not None and hemostasis_mean > _HEMOSTASIS_PROLONGED_MINS

    # ── 6. Aneurysm tracking ──────────────────────────────────────────────────
    aneurysm_series = [
        {"date": str(s.session_date), "flagged": s.aneurysm_flag or False}
        for s in sessions
    ]
    aneurysm_flagged_count = sum(1 for s in sessions if s.aneurysm_flag)
    aneurysm_recent = any(s.aneurysm_flag for s in sessions[-6:]) if sessions else False

    # ── 7. Steal signs ────────────────────────────────────────────────────────
    steal_count = sum(1 for s in sessions if s.steal_signs_flag)

    # ── Summary alerts ────────────────────────────────────────────────────────
    alerts: List[str] = []
    if recirc_alert or recirc_any_high:
        alerts.append("recirculation_elevated")
    if flow_alert:
        alerts.append("access_flow_declining")
    if vp_alert:
        alerts.append("venous_pressure_rising")
    if cannulation_alert:
        alerts.append("cannulation_difficulty_high")
    if hemostasis_alert:
        alerts.append("hemostasis_prolonged")
    if aneurysm_recent:
        alerts.append("aneurysm_detected")
    if steal_count > 0:
        alerts.append("steal_signs_present")

    return {
        "patient_id": patient_id,
        "lookback_months": lookback_months,
        "total_sessions": total,
        "cutoff_month": cutoff_str,
        # Venous pressure
        "venous_pressure": {
            "series": vp_series,
            "mean": vp_mean,
            "trend": vp_trend,
            "alert": vp_alert,
            "threshold": _VENOUS_PRESSURE_HIGH,
        },
        # Access flow
        "access_flow": {
            "series": flow_series,
            "baseline_mean": flow_baseline,
            "current_mean": flow_current,
            "trend": flow_trend,
            "alert": flow_alert,
        },
        # Recirculation
        "recirculation": {
            "series": recirc_series,
            "latest": recirc_latest,
            "any_high": recirc_any_high,
            "alert": recirc_alert or recirc_any_high,
            "threshold": _RECIRC_ALERT_PCT,
        },
        # Cannulation
        "cannulation": {
            "counts": dict(difficulty_counts),
            "infiltration_count": infiltration_count,
            "difficult_rate": round(failed_or_difficult / len(avf_sessions) * 100, 1) if avf_sessions else None,
            "alert": cannulation_alert,
        },
        # Hemostasis
        "hemostasis": {
            "series": hemostasis_series,
            "mean_mins": hemostasis_mean,
            "trend": hemostasis_trend,
            "alert": hemostasis_alert,
            "threshold_mins": _HEMOSTASIS_PROLONGED_MINS,
        },
        # Aneurysm
        "aneurysm": {
            "series": aneurysm_series,
            "flagged_count": aneurysm_flagged_count,
            "recent_flag": aneurysm_recent,
            "steal_count": steal_count,
        },
        # Summary
        "alerts": alerts,
        "alert_count": len(alerts),
    }
