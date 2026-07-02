"""
ml_esa.py
=========
ESA (Erythropoiesis-Stimulating Agent) Dose Normalization and Hyporesponse Detection.

All ESAs are normalised to a single common currency: weekly SC IU equivalents.
This facility uses subcutaneous administration exclusively — no IV correction is applied.
"""
import math as _math
import re
import logging
from typing import Optional, List, Dict


logger = logging.getLogger(__name__)

# ── ESA Pharmacokinetics ──────────────────────────────────────────────────────
#
# Half-lives for SC administration (the only route used at this facility):
#   Epoetin alfa/beta SC  ≈ 24 h = 1.0 day
#   Darbepoetin alfa SC   ≈ 49 h = 2.04 days
#   Methoxy-PEG-EPO SC    ≈ 134 h = 5.58 days  (Mircera)
#
# PK correction for ODE epo_norm:
#   For the same potency-equivalent weekly IU, different dosing schedules deliver
#   different monthly AUC due to half-life differences.  Mircera dosed monthly
#   has ~5.45× higher AUC than weekly epoetin at the same "equivalent weekly IU".
#   The ODE absorbs this via a lower patient-specific k_epo for Mircera patients,
#   which is fitted automatically from observed Hb data.
#
# Reference: weekly epoetin SC (4 doses/month, t½=1 day).
#   All correction factors are expressed relative to this reference.

_THALF_EPO_DAYS  = 1.0          # epoetin alfa/beta SC ≈ 24 h
_THALF_DARB_DAYS = 49.0 / 24.0  # darbepoetin alfa SC  ≈ 49 h
_THALF_MIRC_DAYS = 134.0 / 24.0 # methoxy-PEG-EPO SC   ≈ 134 h


def _monthly_auc_factor(thalf_days: float, n_doses: int) -> float:
    """
    Total AUC[0, 30 days] for n_doses equally-spaced SC doses each of 1 IU.
    Units: IU·days.  Assumes first-order elimination from a 1-compartment model.
    """
    k = _math.log(2) / thalf_days
    interval = 30.0 / n_doses
    return sum(
        (1.0 - _math.exp(-k * (30.0 - i * interval))) / k
        for i in range(n_doses)
    )


# Compute once at module load — reference AUC for weekly epoetin (4 doses/month)
_F_EPO_WEEKLY_REF: float = _monthly_auc_factor(_THALF_EPO_DAYS, n_doses=4)  # ≈ 5.77 IU-days


def pk_correction_factor(drug_type: str, frequency: str) -> float:
    """
    PK AUC correction factor for ODE epo_norm relative to weekly-epoetin reference.

    factor = AUC_{drug,schedule} / AUC_{epoetin,weekly}  at the same weekly_sc_iu value.

    Values > 1.0 indicate more monthly exposure per equivalent weekly IU.  The ODE
    will fit k_epo proportionally lower for such patients, correctly separating
    drug-specific receptor pharmacology from dose-response.

    Typical values:
        Epoetin 3×/week : ≈ 0.98  (slightly less uniform than weekly)
        Epoetin weekly  : = 1.00  (reference)
        Darbepoetin weekly: ≈ 2.02 (longer t½ → less pulsatile)
        Mircera monthly : ≈ 5.45  (essentially flat concentration over 30 days)
    """
    _n_doses: dict = {
        "tiw": 13, "biw": 9, "weekly": 4, "biweekly": 2,
        "every_10_days": 3, "monthly": 1,
    }
    _thalf: dict = {
        "epoetin":     _THALF_EPO_DAYS,
        "darbepoetin": _THALF_DARB_DAYS,
        "mircera":     _THALF_MIRC_DAYS,
    }
    thalf = _thalf.get(drug_type, _THALF_EPO_DAYS)
    n = _n_doses.get(frequency, 4)
    # General formula: factor = (4/n) × F(thalf, n) / F_REF
    # — accounts for the total monthly dose being 4×weekly regardless of schedule.
    return (4.0 / n) * _monthly_auc_factor(thalf, n) / _F_EPO_WEEKLY_REF

# ── ESA Dose Normalization ────────────────────────────────────────────────────
#
# All ESAs are normalised to a single common currency: weekly SC IU equivalents.
# SC is the only route used at this facility; no IV correction factor is applied.
#
# Conversion chain (per published clinical guidance):
#   Darbepoetin 1 mcg/week  = 200 IU/week  epoetin SC
#   Mircera (monthly)       → weekly darbepoetin equiv = monthly_mcg ÷ 4
#                           → weekly SC IU equiv       = (monthly_mcg ÷ 4) × 200
#                                                      = monthly_mcg × 50
#   Mircera (biweekly)      → weekly SC IU equiv       = biweekly_mcg × 100
#
# Mircera threshold bands (for equivalence checks):
#   ≤ 8 000 IU/week epoetin  ↔  ≤ 40 mcg/week darbepoetin  →  120 mcg/month Mircera
#   8 001–16 000 IU/week     ↔  41–80 mcg/week darbepoetin  →  180 mcg/month Mircera

_MIRCERA_SYNONYMS   = {"mircera", "peginesatide", "cera", "methoxy peg", "mpg-epo", "erypeg", "peg epo", "peg-epo", "ery peg", "eripack"}
_DARBE_SYNONYMS     = {"darbepoetin", "aranesp", "darb", "darbp", "darbe"}
_EPOETIN_SYNONYMS   = {"epoetin", "epo", "erythropoietin", "procrit", "epogen", "neorecormon"}


def normalize_epo_dose(dose_str: str) -> dict:
    """
    Convert any ESA dose string to weekly SC IU equivalents.

    This facility uses subcutaneous administration exclusively.
    No IV correction factor is applied — all output is in SC IU/week.

    Conversion factors (SC basis):
      Epoetin alfa/beta SC:  dose IU × frequency multiplier
      Darbepoetin alfa SC:   1 mcg = 200 SC IU/week epoetin equivalent
      Mircera SC (monthly):  monthly_mcg × 50  (= monthly_mcg / 4 weeks × 200)
      Mircera SC (biweekly): biweekly_mcg × 100
    """
    null = {"weekly_iu_sc": None, "drug_type": None, "frequency": None,
            "dose_value": None, "original": dose_str, "confidence": "low", "route": "sc"}
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
    weekly_iu  = None

    # ── Detect drug type ──────────────────────────────────────────────────────
    if any(k in s for k in _DARBE_SYNONYMS):
        drug_type = "darbepoetin"
    elif any(k in s for k in _MIRCERA_SYNONYMS) or s.startswith("m-") or "mcg" in s:
        drug_type = "mircera"
    elif any(k in s for k in _EPOETIN_SYNONYMS):
        drug_type = "epoetin"

    # ── Detect administration frequency ──────────────────────────────────────
    if "monthly" in s or "/month" in s or "qmonth" in s or "q4w" in s:
        frequency = "monthly"
    elif "biweekly" in s or "fortnight" in s or "/2w" in s or "q2w" in s or "eow" in s or "2 weeks" in s or "every 2 weeks" in s:
        frequency = "biweekly"
    elif "10 days" in s or "every 10 days" in s or "q10d" in s:
        frequency = "every_10_days"
    elif "tiw" in s or "3x" in s or "three" in s:
        frequency = "tiw"
    elif "biw" in s or "2x" in s or "twice" in s:
        frequency = "biw"
    elif "weekly" in s or "/week" in s or "/wk" in s:
        frequency = "weekly"

    # ── Apply SC conversion factors ───────────────────────────────────────────
    if drug_type == "mircera":
        # Mircera SC: 1 mcg ≈ 200 SC IU/week epoetin equivalent
        if frequency == "unknown":
            frequency = "monthly"
        if frequency == "monthly":
            weekly_iu = dose_value * 50.0        # monthly_mcg / 4 × 200
        elif frequency == "biweekly":
            weekly_iu = dose_value * 100.0       # biweekly_mcg / 2 × 200
        elif frequency == "every_10_days":
            weekly_iu = (dose_value / 10.0) * 7.0 * 200.0
        elif frequency == "weekly":
            weekly_iu = dose_value * 200.0

    elif drug_type == "darbepoetin":
        # Darbepoetin SC: 1 mcg = 200 SC IU/week epoetin equivalent
        if frequency == "unknown":
            frequency = "weekly"
        if frequency == "weekly":
            weekly_iu = dose_value * 200.0
        elif frequency == "biweekly":
            weekly_iu = (dose_value / 2.0) * 200.0

    elif drug_type == "epoetin":
        # Epoetin SC: dose is already in IU; multiply by weekly frequency.
        if frequency == "tiw":
            weekly_iu = dose_value * 3
        elif frequency == "biw":
            weekly_iu = dose_value * 2
        elif frequency == "weekly":
            weekly_iu = dose_value
        elif frequency == "biweekly":
            weekly_iu = dose_value / 2.0
        else:
            # Default to weekly for epoetin if frequency is not specified
            frequency = "weekly"
            weekly_iu = dose_value

    if weekly_iu is not None:
        weekly_iu = round(weekly_iu, 2)

    # ── PK-corrected effective monthly AUC ────────────────────────────────────
    # AUC[0-30 days] in IU-days for the actual dosing schedule, accounting for
    # each drug's SC half-life.  Mircera dosed monthly accumulates ~5.45× more
    # monthly AUC than the same "equivalent weekly IU" of epoetin given weekly.
    pk_factor: float = pk_correction_factor(drug_type, frequency)
    effective_monthly_auc_iu: Optional[float] = (
        round(weekly_iu * pk_factor * _F_EPO_WEEKLY_REF, 1) if weekly_iu is not None else None
    )

    return {
        "weekly_iu_sc":             weekly_iu,
        "drug_type":                drug_type,
        "frequency":                frequency,
        "dose_value":               dose_value,
        "original":                 dose_str,
        "route":                    "sc",
        "confidence":               "high" if drug_type != "unknown" else "low",
        "pk_correction_factor":     round(pk_factor, 4),
        "effective_monthly_auc_iu": effective_monthly_auc_iu,
    }


def get_mircera_equivalent(epoetin_weekly_iu: float = None,
                            darbepoetin_weekly_mcg: float = None) -> dict:
    """
    Return the recommended Mircera monthly dose given an epoetin or darbepoetin dose.
    Used as a feature-engineering helper for the ML pipeline.
    """
    if epoetin_weekly_iu is not None:
        if epoetin_weekly_iu <= 8000:
            return {"mircera_monthly_mcg": 120, "band": "≤8000 IU/week", "basis": "epoetin"}
        elif epoetin_weekly_iu <= 16000:
            return {"mircera_monthly_mcg": 180, "band": "8001–16000 IU/week", "basis": "epoetin"}
        else:
            return {"mircera_monthly_mcg": 200, "band": ">16000 IU/week", "basis": "epoetin"}

    if darbepoetin_weekly_mcg is not None:
        if darbepoetin_weekly_mcg <= 40:
            return {"mircera_monthly_mcg": 120, "band": "≤40 mcg/week", "basis": "darbepoetin"}
        elif darbepoetin_weekly_mcg <= 80:
            return {"mircera_monthly_mcg": 180, "band": "40–80 mcg/week", "basis": "darbepoetin"}
        else:
            return {"mircera_monthly_mcg": 200, "band": ">80 mcg/week", "basis": "darbepoetin"}

    return {"mircera_monthly_mcg": None, "band": None, "basis": None}


def _parse_epo_dose(dose_str: Optional[str]) -> Optional[float]:
    return normalize_epo_dose(dose_str).get("weekly_iu_sc")


# ── Desidustat (HIF-PHI) IU approximation ────────────────────────────────────
#
# Desidustat (Oxemia) is an oral HIF prolyl-hydroxylase inhibitor — mechanistically
# different from injectable ESAs but produces the same erythropoietic outcome.
# The ODE requires a numeric epo_norm signal; without this the model sees epo_norm=0
# and fits a spuriously high k_prod, making per-patient calibration unreliable.
#
# Approximation basis (DREAM-ND RCT, Agarwal et al. JASN 2021):
#   Desidustat 100 mg TIW maintained median Hb ≈10.5 g/dL, comparable to
#   epoetin ~6 000 IU/week SC.
#   Per-mg-per-dose estimate: 6 000 IU/wk ÷ (100 mg × 3 doses/wk) ≈ 20 IU/wk per mg·dose.
#
# The ODE fits k_epo per-patient from observed Hb, so the absolute scale is
# self-correcting once ≥3 monthly records are available.  The approximation only
# needs to be non-zero and proportional to dose.

_DESIDUSTAT_IU_PER_MG_DOSE: float = 20.0   # IU/week per (mg × doses/week)


def _parse_desidustat_weekly_iu(dose_str: str) -> Optional[float]:
    """Convert a Desidustat dose string to weekly SC IU equivalent for the ODE."""
    if not dose_str:
        return None
    s = dose_str.lower()
    numbers = re.findall(r'\d+(?:\.\d+)?', s)
    if not numbers:
        return None
    mg = float(numbers[0])
    if "once daily" in s or " od" in s or "daily" in s:
        doses_per_week = 7.0
    elif "twice" in s or " bd" in s or "biw" in s or "2x" in s:
        doses_per_week = 2.0
    else:
        doses_per_week = 3.0   # TIW is the most common schedule (DREAM-ND)
    return round(mg * doses_per_week * _DESIDUSTAT_IU_PER_MG_DOSE, 2)


def _resolve_weekly_iu_sc(record: dict) -> Optional[float]:
    """Return weekly SC IU equivalent from a record dict.

    Priority order:
      1. Parsed epo_mircera_dose string (Mircera / darbepoetin / epoetin).
      2. Manually entered epo_weekly_units.
      3. Desidustat dose string — approximated to IU equivalent (see module note).
    """
    dose_str = record.get("epo_mircera_dose")
    if dose_str:
        parsed = normalize_epo_dose(dose_str)
        if parsed.get("confidence") == "high" and parsed.get("weekly_iu_sc") is not None:
            return parsed.get("weekly_iu_sc")

    stored = record.get("epo_weekly_units")
    if stored is not None:
        return float(stored)

    desd = record.get("desidustat_dose")
    if desd:
        iu = _parse_desidustat_weekly_iu(desd)
        if iu is not None:
            return iu

    return None


def _resolve_pk_corrected_iu(record: dict) -> Optional[float]:
    """
    Weekly SC IU × pk_correction_factor — use this for the ODE's epo_norm.

    Returns the SUM of ESA and Desidustat contributions so that patients on
    concurrent or transitioning therapies are modelled correctly by the ODE fitter.

    For ESA: weekly_iu × pk_factor (Mircera ≈5.45, Darbepoetin ≈2.02, Epoetin 1.0).
    For Desidustat: pk_factor = 1.0 (oral, t½ ≈8 h, TIW ≈ weekly-epoetin AUC profile).
    """
    esa_pk: Optional[float] = None
    dose_str = record.get("epo_mircera_dose")
    if dose_str:
        parsed = normalize_epo_dose(dose_str)
        if parsed.get("confidence") == "high" and parsed.get("weekly_iu_sc") is not None:
            esa_pk = parsed["weekly_iu_sc"] * parsed["pk_correction_factor"]
    if esa_pk is None:
        stored = record.get("epo_weekly_units")
        if stored is not None:
            esa_pk = float(stored)

    # Desidustat: pk_factor = 1.0 (short t½, frequent dosing ≈ weekly-epoetin AUC profile)
    desd_pk: Optional[float] = None
    desd = record.get("desidustat_dose")
    if desd:
        iu = _parse_desidustat_weekly_iu(desd)
        if iu is not None:
            desd_pk = iu

    if esa_pk is None and desd_pk is None:
        return None
    return (esa_pk or 0.0) + (desd_pk or 0.0)


def resolve_esa_weekly_iu(record: dict) -> Optional[float]:
    """ESA-only weekly SC IU (Mircera/darbepoetin/epoetin). Excludes Desidustat.

    Use this when you need to override ESA and Desidustat independently in the
    digital twin scenario sandbox (e.g. 'stop Desidustat, keep Mircera').
    """
    dose_str = record.get("epo_mircera_dose")
    if dose_str:
        parsed = normalize_epo_dose(dose_str)
        if parsed.get("confidence") == "high" and parsed.get("weekly_iu_sc") is not None:
            return parsed["weekly_iu_sc"]
    stored = record.get("epo_weekly_units")
    if stored is not None:
        return float(stored)
    return None


def resolve_desidustat_weekly_iu(record: dict) -> Optional[float]:
    """Desidustat-only weekly SC IU equivalent. Excludes ESA.

    Use this when you need to override ESA and Desidustat independently in the
    digital twin scenario sandbox (e.g. 'stop Desidustat, keep Mircera').
    """
    desd = record.get("desidustat_dose")
    if desd:
        return _parse_desidustat_weekly_iu(desd)
    return None


def resolve_esa_pk_corrected_iu(record: dict) -> Optional[float]:
    """ESA-only weekly SC IU × pk_correction_factor. Excludes Desidustat.

    This is the ESA half of _resolve_pk_corrected_iu(): the two-compartment ODE
    now models injectable ESA (this channel) and the oral HIF-PHI Desidustat
    (resolve_desidustat_weekly_iu) as *separate* stimulation channels so their
    distinct dose-response and iron dependence are not conflated into one k_epo.
    """
    dose_str = record.get("epo_mircera_dose")
    if dose_str:
        parsed = normalize_epo_dose(dose_str)
        if parsed.get("confidence") == "high" and parsed.get("weekly_iu_sc") is not None:
            return parsed["weekly_iu_sc"] * parsed["pk_correction_factor"]
    stored = record.get("epo_weekly_units")
    if stored is not None:
        return float(stored)
    return None


def detect_epo_hyporesponse(df: List[Dict], hb_meta: Dict = None) -> Dict:  # noqa: ARG001 — hb_meta reserved for future caller context
    """
    Assess ESA (Epoetin / Darbepoetin / Mircera) response quality.
    """
    # Import here to avoid circular dependency
    from ml_trends import _hb_endo

    # T1-4: Defensive sort descending
    df = sorted(df, key=lambda x: x.get("month", ""), reverse=True)

    # Drop duplicate months — same month entered twice produces identical ERI values
    # in the rolling window, making 2 distinct observations look like 3.
    seen_months: set = set()
    deduped = []
    for r in df:
        m = r.get("month") or r.get("record_month")
        if m not in seen_months:
            seen_months.add(m)
            deduped.append(r)
    df = deduped

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
        if r.get("hb") is not None and _resolve_weekly_iu_sc(r) is not None
    ]

    if len(complete_pairs) < 3:
        missing = []
        hb_count = sum(1 for r in df if r.get("hb") is not None)
        dose_count = sum(1 for r in df if _resolve_weekly_iu_sc(r) is not None)
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

    dose_iv = _resolve_weekly_iu_sc(latest) or 0
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

        r_dose_iv = _resolve_weekly_iu_sc(r) or 0
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
    dose_display = f"{int(dose_iv):,} SC-IU/wk" if dose_iv else "unknown dose"

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
            "dose_per_kg_sc": round(dose_per_kg, 1),
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
            "weekly_iu_sc": dose_iv,
            "transfusion_confounded": transfusion_confounded,
            "hb_raw": round(hb_raw, 1),
            "hb_corrected": round(hb, 1),
            "message": message,
        }
    }
