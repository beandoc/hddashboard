"""
services/pressure_analysis.py
==============================
Circuit pressure trend analysis for early vascular access failure detection.

Clinical thresholds (conservative, based on KDOQI 2019 Vascular Access Guidelines
and standard HD unit alarm limits):

  Arterial line pressure (negative mmHg — suction from access):
    Warning:  mean ≤ −200 mmHg   (poor inflow, possible needle malpositioning)
    Alert:    mean ≤ −220 mmHg   (likely inflow stenosis)
    Trend:    slope ≤ −8 mmHg/session (worsening across recent sessions)

  Venous line pressure (positive mmHg — return limb):
    Warning:  mean ≥ 180 mmHg   (venous outflow resistance rising)
    Alert:    mean ≥ 210 mmHg   (outflow stenosis probable)
    Trend:    slope ≥  8 mmHg/session (escalating)

  Transmembrane pressure / TMP (positive mmHg):
    Warning:  mean ≥ 250 mmHg
    Alert:    mean ≥ 300 mmHg   (membrane/circuit flow-limiting obstruction)

  Combined risk: both arterial AND venous in alert range → highest-priority flag.

Minimum sessions for a trend to be computed: 3.
Minimum sessions to fire a level-1 alert: 3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── Clinical thresholds ──────────────────────────────────────────────────────

_ART_WARN  = -200.0   # mmHg  (more negative = worse inflow)
_ART_ALERT = -220.0
_ART_SLOPE = -8.0     # mmHg/session (getting more negative)

_VEN_WARN  =  180.0   # mmHg
_VEN_ALERT =  210.0
_VEN_SLOPE =   8.0    # mmHg/session (rising)

_TMP_WARN  =  250.0   # mmHg
_TMP_ALERT =  300.0

_MIN_SESSIONS = 3     # require at least this many data points to fire an alert


# ── Internal helpers ─────────────────────────────────────────────────────────

def _slope(values: list[float]) -> Optional[float]:
    """Ordinary least-squares slope through (index, value) pairs.

    Returns None when fewer than 2 points are present.
    Values should be ordered oldest → newest so a positive slope means
    the quantity is rising over time.
    """
    n = len(values)
    if n < 2:
        return None
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return round(num / den, 2) if den else None


def _mean(values: list[float]) -> Optional[float]:
    return round(sum(values) / len(values), 1) if values else None


# ── Public data model ────────────────────────────────────────────────────────

@dataclass
class PressureSignal:
    """Aggregated pressure metrics and risk flags for one patient."""

    patient_id:   int
    patient_name: str
    sessions_n:   int          # sessions with at least one pressure field

    # ── Arterial ──────────────────────────────────────────────────────────
    art_mean:    Optional[float] = None   # mean over recent sessions (mmHg)
    art_slope:   Optional[float] = None   # mmHg/session (negative = worsening)
    art_values:  list[float]     = field(default_factory=list)   # oldest→newest

    # ── Venous ────────────────────────────────────────────────────────────
    ven_mean:    Optional[float] = None
    ven_slope:   Optional[float] = None
    ven_values:  list[float]     = field(default_factory=list)

    # ── TMP ───────────────────────────────────────────────────────────────
    tmp_mean:    Optional[float] = None
    tmp_slope:   Optional[float] = None
    tmp_values:  list[float]     = field(default_factory=list)

    # ── Risk classification ────────────────────────────────────────────────
    arterial_risk:  str = "ok"    # "ok" | "warning" | "alert"
    venous_risk:    str = "ok"
    tmp_risk:       str = "ok"
    combined_risk:  bool = False  # arterial + venous both ≥ alert level

    # Human-readable alert messages for the alerts page
    flags: list[str] = field(default_factory=list)

    @property
    def max_risk(self) -> str:
        """Highest risk level across all three channels."""
        levels = {"alert": 2, "warning": 1, "ok": 0}
        worst = max(levels.get(r, 0) for r in [self.arterial_risk, self.venous_risk, self.tmp_risk])
        return {2: "alert", 1: "warning", 0: "ok"}[worst]


# ── Core computation ─────────────────────────────────────────────────────────

def compute_pressure_signals(
    patient_id: int,
    patient_name: str,
    sessions: list,           # list of SessionRecord ORM objects, most-recent first
) -> Optional[PressureSignal]:
    """
    Compute trend signals from the supplied session list.

    Sessions should be ordered most-recent → oldest (as returned by
    _fetch_recent_n_sessions). Internally we reverse to oldest→newest
    so OLS slopes are directionally intuitive.

    Returns None when no pressure data exists for this patient.
    """
    # Collect values oldest → newest (reverse of query order)
    art_vals: list[float] = []
    ven_vals: list[float] = []
    tmp_vals: list[float] = []

    for s in reversed(sessions):
        if s.arterial_line_pressure is not None:
            art_vals.append(float(s.arterial_line_pressure))
        if s.venous_line_pressure is not None:
            ven_vals.append(float(s.venous_line_pressure))
        if s.transmembrane_pressure is not None:
            tmp_vals.append(float(s.transmembrane_pressure))

    sessions_with_data = max(len(art_vals), len(ven_vals), len(tmp_vals))
    if sessions_with_data == 0:
        return None

    sig = PressureSignal(
        patient_id=patient_id,
        patient_name=patient_name,
        sessions_n=sessions_with_data,
        art_values=art_vals,
        ven_values=ven_vals,
        tmp_values=tmp_vals,
        art_mean=_mean(art_vals),
        art_slope=_slope(art_vals),
        ven_mean=_mean(ven_vals),
        ven_slope=_slope(ven_vals),
        tmp_mean=_mean(tmp_vals),
        tmp_slope=_slope(tmp_vals),
    )

    # ── Classify arterial risk ─────────────────────────────────────────────
    if len(art_vals) >= _MIN_SESSIONS and sig.art_mean is not None:
        if sig.art_mean <= _ART_ALERT:
            sig.arterial_risk = "alert"
            sig.flags.append(
                f"High Arterial Pressure (mean {sig.art_mean:.0f} mmHg) — inflow stenosis suspected"
            )
        elif sig.art_mean <= _ART_WARN:
            sig.arterial_risk = "warning"
            sig.flags.append(
                f"Elevated Arterial Pressure (mean {sig.art_mean:.0f} mmHg) — monitor inflow"
            )

    # Trend regardless of mean level
    if sig.art_slope is not None and sig.art_slope <= _ART_SLOPE and len(art_vals) >= _MIN_SESSIONS:
        if sig.arterial_risk == "ok":
            sig.arterial_risk = "warning"
        msg = f"Arterial Pressure Worsening ({sig.art_slope:+.1f} mmHg/session trend)"
        if msg not in sig.flags:
            sig.flags.append(msg)

    # ── Classify venous risk ───────────────────────────────────────────────
    if len(ven_vals) >= _MIN_SESSIONS and sig.ven_mean is not None:
        if sig.ven_mean >= _VEN_ALERT:
            sig.venous_risk = "alert"
            sig.flags.append(
                f"High Venous Pressure (mean {sig.ven_mean:.0f} mmHg) — outflow stenosis suspected"
            )
        elif sig.ven_mean >= _VEN_WARN:
            sig.venous_risk = "warning"
            sig.flags.append(
                f"Elevated Venous Pressure (mean {sig.ven_mean:.0f} mmHg) — monitor outflow"
            )

    if sig.ven_slope is not None and sig.ven_slope >= _VEN_SLOPE and len(ven_vals) >= _MIN_SESSIONS:
        if sig.venous_risk == "ok":
            sig.venous_risk = "warning"
        msg = f"Venous Pressure Escalating ({sig.ven_slope:+.1f} mmHg/session trend)"
        if msg not in sig.flags:
            sig.flags.append(msg)

    # ── Classify TMP risk ──────────────────────────────────────────────────
    if len(tmp_vals) >= _MIN_SESSIONS and sig.tmp_mean is not None:
        if sig.tmp_mean >= _TMP_ALERT:
            sig.tmp_risk = "alert"
            sig.flags.append(
                f"High TMP (mean {sig.tmp_mean:.0f} mmHg) — circuit/membrane flow obstruction"
            )
        elif sig.tmp_mean >= _TMP_WARN:
            sig.tmp_risk = "warning"
            sig.flags.append(f"Elevated TMP (mean {sig.tmp_mean:.0f} mmHg)")

    # ── Combined risk flag ─────────────────────────────────────────────────
    if sig.arterial_risk == "alert" and sig.venous_risk == "alert":
        sig.combined_risk = True
        sig.flags.insert(0, "COMBINED CIRCUIT PRESSURE ALERT — Early access failure risk")

    return sig


# ── Fleet-level aggregation ──────────────────────────────────────────────────

def compute_fleet_pressure_signals(
    db,
    patient_list: list,        # list of Patient ORM objects
    recent_sessions: dict,     # {patient_id: [SessionRecord, ...]} from _fetch_recent_n_sessions
) -> list[PressureSignal]:
    """
    Run compute_pressure_signals for every patient in patient_list.
    Returns a list of PressureSignal objects (only patients with data),
    sorted highest-risk first.
    """
    results: list[PressureSignal] = []

    for p in patient_list:
        sessions = recent_sessions.get(p.id, [])
        sig = compute_pressure_signals(p.id, p.name, sessions)
        if sig is not None:
            results.append(sig)

    risk_order = {"alert": 0, "warning": 1, "ok": 2}
    results.sort(key=lambda s: (risk_order.get(s.max_risk, 2), -(s.sessions_n)))
    return results
