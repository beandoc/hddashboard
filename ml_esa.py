"""
ml_esa.py
=========
ESA (Erythropoiesis-Stimulating Agent) Dose Normalization and Hyporesponse Detection.

All ESAs are normalised to a single common currency: weekly EPO-IU equivalents.
"""
import re
import logging
from typing import Optional, List, Dict

import numpy as np

logger = logging.getLogger(__name__)

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
    route      = "iv" if "iv" in s else "sc" if "sc" in s or "subcut" in s else "sc"  # Default to SC for HD
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
            weekly_iu = (dose_value / 4.0) * mult
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


def _resolve_weekly_iu_iv(record: dict) -> Optional[float]:
    """Return weekly IV IU equivalent from a record."""
    stored = record.get("epo_weekly_units")
    if stored is not None:
        pass

    dose_str = record.get("epo_mircera_dose")
    if dose_str:
        parsed = normalize_epo_dose(dose_str)
        if parsed.get("confidence") == "high":
            return parsed.get("weekly_iu_iv")

    if stored is not None:
        return float(stored) * 1.42  # Manual units assume SC epoetin alfa -> convert to IV
    return None


def detect_epo_hyporesponse(df: List[Dict], hb_meta: Dict = None) -> Dict:  # noqa: ARG001
    """
    Assess ESA (Epoetin / Darbepoetin / Mircera) response quality.
    """
    # Import here to avoid circular dependency
    from ml_trends import _hb_endo

    # T1-4: Defensive sort descending
    df = sorted(df, key=lambda x: x.get("month", ""), reverse=True)
    if not df:
        return {
            "available": False,
            "error":     "No records available.",
            "data": {
                "hypo_response": False, "status": "No Data", "class": "warning",
                "message": "No records.", "ready": False, "confidence": "insufficient"
            }
        }

    # Gate: require 3+ months with BOTH Hb and any ESA dose entry
    complete_pairs = [
        r for r in df
        if r.get("hb") is not None and _resolve_weekly_iu_iv(r) is not None
    ]

    if len(complete_pairs) < 3:
        missing = []
        hb_count = sum(1 for r in df if r.get("hb") is not None)
        dose_count = sum(1 for r in df if _resolve_weekly_iu_iv(r) is not None)
        if hb_count < 3: missing.append(f"Hb ({3-hb_count} more required)")
        if dose_count < 3: missing.append(f"ESA dose ({3-dose_count} more required)")

        return {
            "available": False,
            "error":     f"Need 3+ months (currently have {len(complete_pairs)}).",
            "data": {
                "hypo_response": False,
                "status": "Insufficient Data",
                "class": "warning",
                "ready": False,
                "confidence": "insufficient",
                "inputs_missing": missing,
                "message": (
                    f"Need 3+ months with both Hb and ESA dose recorded "
                    f"(currently have {len(complete_pairs)})."
                ),
            }
        }

    latest = complete_pairs[0]
    # BUG 5 FIX: use explicit None check instead of `or 0.1`
    hb_raw = latest.get("hb")
    hb_raw = hb_raw if hb_raw is not None else 0.1
    transfusion_units = latest.get("transfusion_units") or 0
    transfusion_confounded = transfusion_units > 0

    # Use endogenous Hb for ERI; transfusion-boosted Hb would inflate the denominator
    hb = _hb_endo(hb_raw, transfusion_units) if transfusion_confounded else hb_raw

    dose_iv = _resolve_weekly_iu_iv(latest) or 0
    weight = latest.get("weight")
    if not weight or weight <= 0:
        return {
            "available": False,
            "error":     "Current weight not recorded.",
            "data": {
                "hypo_response": False,
                "status": "Incomplete Data",
                "class": "warning",
                "ready": False,
                "confidence": "insufficient",
                "message": "Current weight not recorded — ERI calculation requires weight.",
            }
        }

    # ── ESA Resistance Index (ERI) Calculation (Sustained over 3 Months) ───────
    eris = []
    dose_per_kgs = []

    for r in complete_pairs[:3]:
        r_hb_raw = r.get("hb") or 0.1
        r_trans  = r.get("transfusion_units") or 0
        r_hb     = _hb_endo(r_hb_raw, r_trans) if r_trans > 0 else r_hb_raw

        r_dose_iv = _resolve_weekly_iu_iv(r) or 0
        r_w       = r.get("weight") or weight  # fallback to latest weight

        if r_w and r_w > 0:
            r_dpk = r_dose_iv / r_w
            r_eri = r_dpk / r_hb if r_hb > 0 else 0
            eris.append(r_eri)
            dose_per_kgs.append(r_dpk)

    # Rolling 3-month averages for display
    eri         = sum(eris) / len(eris) if eris else 0
    dose_per_kg = sum(dose_per_kgs) / len(dose_per_kgs) if dose_per_kgs else 0

    # Identify drug type (latest recorded)
    drug_type = "unknown"
    dose_str = latest.get("epo_mircera_dose", "")
    if dose_str:
        drug_type = normalize_epo_dose(dose_str).get("drug_type", "unknown")

    # ── Classify response ─────────────────────────────────────────────────────
    hypo_months   = sum(1 for e, d in zip(eris, dose_per_kgs) if e >= 10.0 or d >= 450)
    severe_months = sum(1 for e, d in zip(eris, dose_per_kgs) if e >= 20.0 or d >= 600)

    is_hypo = hypo_months >= 2
    severity = "none"
    response_class = "excellent"

    if dose_iv > 0:
        if severe_months >= 2:
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

    transfusion_note = (
        f" [Hb corrected: {hb_raw} → {hb:.1f} g/dL after {transfusion_units} PRBC unit(s)]"
        if transfusion_confounded else ""
    )

    if severity == "severe":
        message = (
            f"Sustained severe hypo-response (Avg ERI {eri:.1f}): Hb {hb:.1f} g/dL on {dose_per_kg:.1f} IU/kg/wk. "
            f"Urgent: check iron, inflammation (CRP), or marrow suppression.{transfusion_note}"
        )
    elif severity == "significant":
        message = (
            f"Sustained hypo-response (Avg ERI {eri:.1f}): Hb {hb:.1f} g/dL on high-dose {drug_label} "
            f"({dose_per_kg:.1f} IU/kg/wk). Review iron stores and ESA resistance workup.{transfusion_note}"
        )
    elif response_class == "suboptimal":
        message = f"Suboptimal (ERI {eri:.2f}): Hb {hb:.1f} g/dL — consider dose uptitration or iron.{transfusion_note}"
    elif response_class == "adequate":
        message = f"Adequate (ERI {eri:.2f}): Hb {hb:.1f} g/dL on {drug_label} ({dose_display}).{transfusion_note}"
    else:
        message = f"Excellent (ERI {eri:.2f}): Hb {hb:.1f} g/dL on {drug_label} ({dose_display}).{transfusion_note}"

    css_class = (
        "danger"  if is_hypo else
        "warning" if response_class == "suboptimal" else
        "success"
    )

    return {
        "available": True,
        "error":     None,
        "data": {
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
            "transfusion_confounded": transfusion_confounded,
            "hb_raw": round(hb_raw, 1),
            "hb_corrected": round(hb, 1),
            "message": message,
        }
    }
