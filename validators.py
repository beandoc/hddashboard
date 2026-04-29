
from typing import List, Dict, Optional

PHYSIOLOGICAL_RANGES = {
    "albumin":    (1.5, 6.0),    # g/dL; if > 6.0, likely entered in g/L by mistake
    "hb":         (4.0, 18.0),   # g/dL
    "phosphorus": (1.0, 12.0),   # mg/dL
    "serum_ferritin": (5, 5000), # ng/mL
    "wbc_count":  (1.0, 30.0),   # ×10³/µL
    "serum_creatinine": (0.5, 25.0),
    "calcium": (5.0, 15.0),
    "serum_potassium": (2.0, 9.0),
    "serum_sodium": (110, 160),
}

def validate_lab_values(record: Dict) -> List[str]:
    """
    Check if lab values are within physiological limits.
    Returns a list of warning messages.
    """
    warnings = []
    for field, (lo, hi) in PHYSIOLOGICAL_RANGES.items():
        val = record.get(field)
        if val is not None:
            try:
                fval = float(val)
                if not (lo <= fval <= hi):
                    warnings.append(f"{field.replace('_', ' ').title()} ({fval}) is outside typical physiological range [{lo} - {hi}]. Please verify units.")
            except (ValueError, TypeError):
                pass
    return warnings
