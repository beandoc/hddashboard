"""
services/twin_validation.py
============================
Scenario input validation for the Digital Dialysis Twin.

Two-tier system (mirrors validators.py pattern):
  HARD_LIMITS  — physiologically impossible → ScenarioValidationError (422)
  SOFT_RANGES  — clinically unusual → warning string returned to caller

Usage:
    clean, warnings = validate_scenario(raw_dict)
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from services.twin_utils import _safe_float

# ── Hard limits (reject entirely — impossible physiology) ────────────────────
HARD_LIMITS: Dict[str, Tuple[float, float]] = {
    "session_h":            (0.5,   12.0),
    "qb_ml_min":            (50.0,  600.0),
    "qd_ml_min":            (100.0, 1200.0),
    "uf_volume_L":          (0.0,   8.0),
    "uf_rate_ml_kg_h":      (0.0,   25.0),
    "dialysate_temp":       (33.0,  39.0),
    "dialysate_sodium":     (120.0, 160.0),
    "esa_weekly_iu":        (0.0,   60_000.0),
    "desidustat_weekly_iu": (0.0,   25_000.0),  # 300 mg OD × 7 × 20 ≈ 42 000; clinical ceiling ~150 mg OD
    "iron_tsat_target":     (0.0,   100.0),
    "p_binder_pbe":         (0.0,   30.0),
    "p_intake_mg_day":      (0.0,   6_000.0),
    "koa_urea":             (200.0, 2_500.0),
}

# ── Soft ranges (warn but allow) ─────────────────────────────────────────────
SOFT_RANGES: Dict[str, Tuple[float, float, str]] = {
    "session_h":            (3.0,   5.5,      "Session <3 h or >5.5 h is outside typical HD practice"),
    "qb_ml_min":            (200.0, 450.0,    "Blood flow <200 or >450 mL/min is outside typical range"),
    "uf_rate_ml_kg_h":      (3.5,   10.0,     "UF rate >10 mL/kg/h exceeds KDOQI safety threshold"),
    "dialysate_temp":       (35.0,  37.0,     "Dialysate temperature outside 35–37 °C may cause haemodynamic instability"),
    "dialysate_sodium":     (135.0, 145.0,    "Dialysate Na outside 135–145 mEq/L risks dysnatraemia"),
    "esa_weekly_iu":        (0.0,   30_000.0, "ESA dose >30 000 IU/week is unusually high; verify intent"),
    "desidustat_weekly_iu": (0.0,   15_000.0, "Desidustat equivalent >15 000 IU/week corresponds to >250 mg OD; verify intent"),
}

# ── Allowed keys (unknown keys dropped silently with a warning) ───────────────
ALLOWED_KEYS = set(HARD_LIMITS.keys()) | {"qb_ml_min", "qd_ml_min"}


class ScenarioValidationError(ValueError):
    """Raised when a hard limit is violated; caller should return HTTP 422."""
    pass


def validate_scenario(raw) -> Tuple[Dict, List[str]]:
    """
    Validate and clean a raw scenario dict.

    Returns (clean_dict, warnings).  Raises ScenarioValidationError for
    hard-limit violations.  Booleans, non-numeric strings, and explicit
    None values are dropped.  Unknown keys are dropped with a warning.
    """
    if not isinstance(raw, dict):
        raise ScenarioValidationError("scenario must be a JSON object")

    clean: Dict = {}
    warnings: List[str] = []

    for key, value in raw.items():
        if value is None:
            continue
        if isinstance(value, bool):
            warnings.append(f"Ignored non-numeric value for '{key}'")
            continue

        numeric = _safe_float(value)
        import math
        if math.isnan(numeric):
            if isinstance(value, str):
                warnings.append(f"Ignored unparseable value for '{key}': {value!r}")
            continue

        if key not in ALLOWED_KEYS:
            warnings.append(f"Unknown scenario key '{key}' ignored")
            continue

        if key in HARD_LIMITS:
            lo, hi = HARD_LIMITS[key]
            if not (lo <= numeric <= hi):
                raise ScenarioValidationError(
                    f"'{key}' value {numeric} is outside physiological bounds [{lo}, {hi}]"
                )

        if key in SOFT_RANGES:
            lo, hi, msg = SOFT_RANGES[key]
            if not (lo <= numeric <= hi):
                warnings.append(msg)

        clean[key] = numeric

    return clean, warnings
