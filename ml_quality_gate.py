"""
ml_quality_gate.py
==================
Input data quality gate for hemodialysis digital twin and ACM models.

Validates lab values and session parameters *before* they enter any kinetic
model, ODE solver, or ML pipeline. Returns structured flags rather than
silently accepting or crashing on implausible inputs.

Clinical thresholds derived from:
  - HEMO Study exclusion criteria (Daugirdas & Depner, NDT 2017; PMC5837547)
  - KDOQI HD Adequacy Guidelines (Guideline 3 — post-dialysis sampling)
  - KDIGO CKD-MBD 2017 target ranges
  - Typical ESRD lab value distributions from published cohort studies

Usage:
    from ml_quality_gate import validate_monthly_record, validate_session_inputs

    flags = validate_monthly_record(rec_dict)
    if flags.has_errors:
        logger.warning(flags.summary())
    # Cleaned dict with implausible values replaced by None:
    clean = flags.cleaned_record
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Clinical range tables ─────────────────────────────────────────────────────
# Format: (hard_min, soft_min, soft_max, hard_max, unit)
# hard_* → reject (set to None)  |  soft_* → warn (keep but flag)

_LAB_RANGES: Dict[str, Tuple] = {
    # Hematopoietic
    "hb":               (4.0,   6.0,  17.0,  20.0,  "g/dL"),
    "hct":              (12.0, 18.0,  55.0,  65.0,  "%"),
    # Iron panel
    "serum_ferritin":   (1.0,   5.0, 1200.0, 5000.0, "µg/L"),
    "tsat":             (1.0,   5.0,  80.0,  100.0, "%"),
    # Biochemistry
    "albumin":          (1.0,   2.5,   5.5,   7.0,  "g/dL"),
    "calcium":          (4.0,   7.0,  12.0,  15.0,  "mg/dL"),
    "phosphorus":       (0.5,   1.5,  10.0,  15.0,  "mg/dL"),
    "serum_potassium":  (2.0,   3.0,   7.0,   9.0,  "mEq/L"),
    "serum_sodium":     (115.0,120.0, 155.0, 165.0, "mEq/L"),
    "serum_bicarbonate":(10.0, 14.0,  38.0,  45.0,  "mEq/L"),
    "crp":              (0.0,   0.0,  150.0, 300.0,  "mg/L"),
    "wbc_count":        (1.0,   2.0,  25.0,  50.0,  "×10³/µL"),
    "mch":              (15.0, 18.0,  40.0,  50.0,  "pg"),
    "mcv":              (50.0, 60.0,  120.0, 140.0, "fL"),
    # Dialysis adequacy
    "single_pool_ktv":  (0.1,   0.5,   3.0,   4.0,  ""),
    "urr":              (5.0,  20.0,  98.0,  100.0, "%"),
    "pre_dialysis_urea":(5.0,  15.0,  200.0, 300.0, "mg/dL"),
    "post_dialysis_urea":(2.0,  3.0,  120.0, 200.0, "mg/dL"),
    # Weight
    "last_prehd_weight":(20.0, 30.0,  200.0, 250.0, "kg"),
    "target_dry_weight":(20.0, 30.0,  200.0, 250.0, "kg"),
    "idwg":             (-0.5,  0.0,   7.0,  10.0,  "kg"),
}

# Session-level parameters for the digital twin simulator
_SESSION_RANGES: Dict[str, Tuple] = {
    "qb_ml_min":        (50.0,  150.0, 550.0, 700.0, "mL/min"),
    "qd_ml_min":        (100.0, 200.0, 900.0,1000.0, "mL/min"),
    "session_h":        (0.5,   1.5,   8.0,  12.0,  "hours"),
    "uf_volume_L":      (0.0,   0.0,   6.0,   8.0,  "L"),
    "uf_rate_ml_kg_h":  (0.0,   0.0,  25.0,  30.0,  "mL/kg/h"),
    "dialysate_temp":   (33.0, 34.0,  39.0,  40.0,  "°C"),
    "dialysate_sodium": (120.0,130.0, 150.0, 155.0, "mEq/L"),
    "p_binder_pbe":     (0.0,   0.0,  20.0,  30.0,  "PBE units"),
    "koa_urea":         (50.0, 100.0,2000.0,3000.0, "mL/min"),
}

# HEMO Study-specific consistency checks (cross-field)
# Format: (check_name, lambda → bool, severity, message)
_CONSISTENCY_CHECKS = [
    (
        "post_bun_exceeds_pre",
        lambda r: (
            r.get("post_dialysis_urea") is not None and
            r.get("pre_dialysis_urea")  is not None and
            float(r["post_dialysis_urea"]) > float(r["pre_dialysis_urea"]) * 1.05
        ),
        "error",
        "Post-dialysis BUN > pre-dialysis BUN — impossible without transfusion or lab error",
    ),
    (
        "urr_implausible",
        lambda r: (
            r.get("urr") is not None and
            r.get("pre_dialysis_urea") is not None and
            r.get("post_dialysis_urea") is not None and
            abs(float(r["urr"]) / 100 -
                (1 - float(r["post_dialysis_urea"]) / max(float(r["pre_dialysis_urea"]), 0.1))
            ) > 0.15
        ),
        "warn",
        "URR inconsistent with pre/post BUN — possible transcription mismatch",
    ),
    (
        "ktv_urr_mismatch",
        lambda r: (
            r.get("single_pool_ktv") is not None and
            r.get("urr") is not None and
            float(r["single_pool_ktv"]) > 2.5 and float(r["urr"]) < 70
        ),
        "warn",
        "High Kt/V (>2.5) with low URR (<70%) — check for sampling error",
    ),
    (
        "weight_loss_exceeds_uf",
        lambda r: (
            r.get("last_prehd_weight") is not None and
            r.get("target_dry_weight") is not None and
            float(r["last_prehd_weight"]) > float(r["target_dry_weight"]) * 1.15
        ),
        "warn",
        "Pre-HD weight >15% above dry weight — confirm IDWG not a scale artefact",
    ),
    (
        "ferritin_tsat_sequestration",
        lambda r: (
            r.get("serum_ferritin") is not None and
            r.get("tsat") is not None and
            float(r["serum_ferritin"]) > 600 and float(r["tsat"]) < 15
        ),
        "warn",
        "High ferritin + very low TSAT — likely iron sequestration (inflammation), not iron overload",
    ),
    (
        "hb_iron_inconsistency",
        lambda r: (
            r.get("hb") is not None and
            r.get("tsat") is not None and
            float(r["hb"]) > 13.5 and float(r["tsat"]) < 10
        ),
        "warn",
        "Hb >13.5 with TSAT <10% — verify Hb (transfusion recently?) or TSAT lab accuracy",
    ),
]


# ── Flag dataclass ────────────────────────────────────────────────────────────

@dataclass
class QualityFlag:
    field:    str
    severity: str          # "error" | "warn"
    message:  str
    value:    Any = None
    expected: str = ""


@dataclass
class QualityReport:
    flags:          List[QualityFlag] = field(default_factory=list)
    cleaned_record: Dict              = field(default_factory=dict)

    @property
    def has_errors(self) -> bool:
        return any(f.severity == "error" for f in self.flags)

    @property
    def has_warnings(self) -> bool:
        return any(f.severity == "warn" for f in self.flags)

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.flags if f.severity == "error")

    @property
    def warn_count(self) -> int:
        return sum(1 for f in self.flags if f.severity == "warn")

    def summary(self) -> str:
        errs  = [f"{f.field}: {f.message}" for f in self.flags if f.severity == "error"]
        warns = [f"{f.field}: {f.message}" for f in self.flags if f.severity == "warn"]
        parts = []
        if errs:
            parts.append(f"ERRORS ({len(errs)}): " + "; ".join(errs))
        if warns:
            parts.append(f"WARNINGS ({len(warns)}): " + "; ".join(warns))
        return " | ".join(parts) if parts else "OK"

    def as_dict(self) -> Dict:
        return {
            "has_errors":   self.has_errors,
            "has_warnings": self.has_warnings,
            "error_count":  self.error_count,
            "warn_count":   self.warn_count,
            "flags": [
                {"field": f.field, "severity": f.severity,
                 "message": f.message, "value": f.value}
                for f in self.flags
            ],
        }


# ── Core validation functions ─────────────────────────────────────────────────

def _check_range(
    record:    Dict,
    field:     str,
    ranges:    Dict[str, Tuple],
) -> List[QualityFlag]:
    """Validate a single numeric field against hard/soft bounds."""
    flags = []
    if field not in ranges or field not in record or record[field] is None:
        return flags

    try:
        v = float(record[field])
    except (TypeError, ValueError):
        flags.append(QualityFlag(
            field=field, severity="error",
            message=f"Non-numeric value '{record[field]}'",
            value=record[field],
        ))
        return flags

    if math.isnan(v) or math.isinf(v):
        flags.append(QualityFlag(
            field=field, severity="error",
            message="NaN or Inf value", value=v,
        ))
        return flags

    hard_min, soft_min, soft_max, hard_max, unit = ranges[field]

    if v < hard_min or v > hard_max:
        flags.append(QualityFlag(
            field=field, severity="error",
            message=f"Value {v} {unit} outside physiologic range [{hard_min}–{hard_max}] — excluded from model",
            value=v,
            expected=f"{hard_min}–{hard_max} {unit}",
        ))
    elif v < soft_min or v > soft_max:
        flags.append(QualityFlag(
            field=field, severity="warn",
            message=f"Value {v} {unit} outside expected range [{soft_min}–{soft_max}] — review",
            value=v,
            expected=f"{soft_min}–{soft_max} {unit}",
        ))

    return flags


def validate_monthly_record(record: Dict) -> QualityReport:
    """
    Validate all lab fields in a monthly record dict.

    Returns QualityReport with:
      .flags           — list of QualityFlag (errors + warnings)
      .cleaned_record  — copy of record with hard-error fields set to None
    """
    import copy
    flags: List[QualityFlag] = []
    cleaned = copy.deepcopy(record)

    for field in _LAB_RANGES:
        field_flags = _check_range(record, field, _LAB_RANGES)
        flags.extend(field_flags)
        # Hard errors → null out to prevent propagation
        if any(f.severity == "error" for f in field_flags):
            cleaned[field] = None

    # Cross-field consistency checks
    for name, check_fn, severity, msg in _CONSISTENCY_CHECKS:
        try:
            if check_fn(cleaned):
                flags.append(QualityFlag(field=name, severity=severity, message=msg))
        except Exception:
            pass

    report = QualityReport(flags=flags, cleaned_record=cleaned)
    if report.has_errors:
        logger.warning("Quality gate: %d error(s) in monthly record — %s",
                       report.error_count, report.summary())
    return report


def validate_session_inputs(params: Dict) -> QualityReport:
    """
    Validate session/simulation parameters before passing to kinetic models.
    Clamps values to physiologic hard bounds rather than nulling them out,
    since simulation needs numeric inputs for all parameters.
    """
    import copy
    flags: List[QualityFlag] = []
    cleaned = copy.deepcopy(params)

    for field in _SESSION_RANGES:
        if field not in params or params[field] is None:
            continue
        field_flags = _check_range(params, field, _SESSION_RANGES)
        flags.extend(field_flags)
        if any(f.severity == "error" for f in field_flags):
            hard_min, _, _, hard_max, _ = _SESSION_RANGES[field]
            try:
                original = float(params[field])
                clamped = max(hard_min, min(hard_max, original))
                cleaned[field] = clamped
                logger.warning(
                    "Quality gate: %s=%s clamped to physiologic bounds [%s–%s]",
                    field, original, hard_min, hard_max,
                )
            except (TypeError, ValueError):
                cleaned[field] = None

    return QualityReport(flags=flags, cleaned_record=cleaned)


def validate_ode_inputs(
    hb0:      float,
    records:  List[Dict],
) -> QualityReport:
    """
    Quick check of ODE-specific inputs.
    Validates baseline Hb and checks for minimum required history.
    """
    flags = []
    cleaned = {"hb0": hb0, "n_records": len(records)}

    if hb0 is None or math.isnan(hb0) or hb0 < 4.0 or hb0 > 20.0:
        flags.append(QualityFlag(
            field="hb0", severity="error",
            message=f"Baseline Hb={hb0} out of range [4–20 g/dL] — ODE not reliable",
            value=hb0,
        ))

    n_hb = sum(1 for r in records if r.get("hb") is not None)
    if n_hb < 3:
        flags.append(QualityFlag(
            field="n_records", severity="warn",
            message=f"Only {n_hb} Hb data points — ODE using population-prior parameters (not patient-calibrated)",
            value=n_hb,
        ))

    return QualityReport(flags=flags, cleaned_record=cleaned)


def quality_score(report: QualityReport) -> float:
    """
    Data quality score 0–100 for display.
    Starts at 100; deduct 20 per error, 5 per warning.
    """
    score = 100.0 - report.error_count * 20 - report.warn_count * 5
    return max(0.0, score)
