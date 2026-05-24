from typing import Dict, List, Optional

# Values that are physiologically impossible — almost certainly unit errors.
# Violating these raises ValueError and blocks the save.
HARD_LIMITS: Dict[str, tuple] = {
    "hb":               (2.0,  22.0),   # g/dL — Hb 50 means user entered mmol/L or mg/dL
    "albumin":          (0.8,   6.0),   # g/dL — > 6.0 is physically impossible (serum albumin max ~5.5)
    "calcium":          (3.0,  18.0),   # mg/dL
    "phosphorus":       (0.5,  20.0),   # mg/dL
    "serum_ferritin":   (1,  50000),    # ng/mL — > 50000 is instrument/unit error
    "wbc_count":        (0.1,  50.0),   # ×10³/µL
    "serum_creatinine": (0.2,  40.0),   # mg/dL
    "serum_potassium":  (1.5,  10.0),   # mEq/L — outside = incompatible with life
    "serum_sodium":     (100,  180),    # mEq/L
    "tsat":             (0.0, 100.0),   # % — transferrin saturation cannot exceed 100%
}

# Values outside typical clinical targets — likely entered correctly but flagged for review.
# These only produce warnings; the save is not blocked.
PHYSIOLOGICAL_RANGES: Dict[str, tuple] = {
    "albumin":          (1.5,   5.5),
    "hb":               (4.0,  18.0),
    "phosphorus":       (1.0,  12.0),
    "serum_ferritin":   (5,   5000),
    "wbc_count":        (1.0,  30.0),
    "serum_creatinine": (0.5,  25.0),
    "calcium":          (5.0,  15.0),
    "serum_potassium":  (2.0,   9.0),
    "serum_sodium":     (110,  160),
    "tsat":             (0.0,  100.0),
}


def validate_hard_limits(record: Dict) -> None:
    """Raise ValueError for physiologically impossible values.

    Call before any DB write. A hit here means a unit error or a transcription
    mistake — the value cannot be correct as entered.
    """
    for field, (lo, hi) in HARD_LIMITS.items():
        val = record.get(field)
        if val is None:
            continue
        try:
            fval = float(val)
        except (ValueError, TypeError):
            continue
        if not (lo <= fval <= hi):
            label = field.replace("_", " ").title()
            raise ValueError(
                f"{label} value of {fval} is outside the physiologically possible range "
                f"[{lo}–{hi}]. Please verify units and re-enter."
            )


def validate_lab_values(record: Dict) -> List[str]:
    """Return soft-warning messages for values outside typical clinical ranges.

    The caller decides whether to surface these to the user. Unlike
    validate_hard_limits(), this never raises — it only informs.
    """
    warnings = []
    for field, (lo, hi) in PHYSIOLOGICAL_RANGES.items():
        val = record.get(field)
        if val is None:
            continue
        try:
            fval = float(val)
        except (ValueError, TypeError):
            continue
        if not (lo <= fval <= hi):
            label = field.replace("_", " ").title()
            warnings.append(
                f"{label} ({fval}) is outside typical range [{lo}–{hi}]. Please verify units."
            )
    return warnings
