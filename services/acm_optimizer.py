"""
services/acm_optimizer.py
=========================
Model-based closed-loop dose controller for the Anemia Control Model (ACM).

Where ml_acm._esa_recommendation applies fixed ±25% / +50% guideline *steps*,
this module *solves* the patient-specific erythropoiesis ODE (ml_acm_ode) for the
ESA (and HIF-PHI) dose that lands Hb inside the KDIGO target band at the forecast
horizon, with damping to reduce Hb cycling — the core of Fresenius-style ACM.

Design contract:
  • Pure functions: take records + scalars, return dicts. No DB access.
  • Safety guardrails from ml_acm (Hb ceiling/floor, iron-first, dose caps) are
    HARD constraints, applied after the unconstrained optimum is found.
  • Confidence gating: the optimizer is trusted ONLY when the ODE is calibrated
    on this patient (param_confidence high/moderate, k_epo identified). Otherwise
    it falls back to the existing heuristic and labels method="heuristic-fallback".
  • Inflammation labs (CRP/IL-6/…) are optional everywhere: absence never blocks a
    recommendation and never adds a penalty or flag.

Public API:
  optimize_esa(...)   -> dict   model-based ESA dose (with heuristic fallback)
  optimize_iron(...)  -> dict   quantified IV-iron repletion dose
  hifphi_switch(...)  -> dict|None   ESA-sparing HIF-PHI suggestion
  target_attainment(...) -> dict     P(in-target / overshoot / undershoot)
  compute_eri(...)    -> float|None  ESA Resistance Index (IU/kg/week per g/dL)
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Confidence levels at which the model-based optimizer is trusted.
_TRUSTED_CONFIDENCE = ("high", "moderate", "hybrid-calibrated", "ode-calibrated")


# ── ESA Resistance Index ──────────────────────────────────────────────────────

def compute_eri(weekly_iu_sc: Optional[float], weight_kg: Optional[float],
                hb: Optional[float]) -> Optional[float]:
    """ESA Resistance Index = weekly ESA IU / kg / (g/dL Hb).

    Higher ERI = more ESA needed per unit Hb = worse response. Returns None when
    dose, weight or Hb is missing/zero (ERI is undefined without an ESA dose).
    """
    if not weekly_iu_sc or not weight_kg or not hb:
        return None
    try:
        if weekly_iu_sc <= 0 or weight_kg <= 0 or hb <= 0:
            return None
        return round((weekly_iu_sc / weight_kg) / hb, 3)
    except (TypeError, ZeroDivisionError):
        return None


# ── Probabilistic target attainment ───────────────────────────────────────────

def _normal_cdf(x: float, mu: float, sigma: float) -> float:
    if sigma <= 0:
        return 1.0 if x >= mu else 0.0
    return 0.5 * (1.0 + math.erf((x - mu) / (sigma * math.sqrt(2.0))))


def target_attainment(hb_horizon: float, sigma: float,
                      low: float = 10.0, high: float = 11.5,
                      ceiling: float = 13.0, floor: float = 10.0) -> Dict:
    """Probability the horizon Hb lands in / above / below target.

    Normal approximation N(hb_horizon, sigma). `sigma` is the horizon-scaled ODE
    prediction SD (uncertainty_band_gd × √horizon).
    """
    p_below_low  = _normal_cdf(low, hb_horizon, sigma)
    p_below_high = _normal_cdf(high, hb_horizon, sigma)
    p_in_target  = max(0.0, p_below_high - p_below_low)
    p_overshoot  = 1.0 - _normal_cdf(ceiling, hb_horizon, sigma)
    p_undershoot = _normal_cdf(floor, hb_horizon, sigma) if floor != low else p_below_low
    return {
        "p_in_target":  round(p_in_target, 3),
        "p_overshoot":  round(p_overshoot, 3),
        "p_undershoot": round(p_undershoot, 3),
        "hb_horizon":   round(hb_horizon, 2),
        "sigma":        round(sigma, 3),
    }


# ── ESA dose optimizer ─────────────────────────────────────────────────────────

def optimize_esa(
    patient_id:          int,
    records:             List[Dict],
    current_iu_sc:       Optional[float],
    ferritin:            Optional[float],
    tsat:                Optional[float],
    crp:                 Optional[float],
    forecast_confidence: str = "heuristic",
    k_epo_near_zero:     bool = False,
    hb_target:           tuple = (10.0, 11.5),
    horizon:             int = 3,
    patient_meta:        Optional[Dict] = None,
) -> Dict:
    """Model-based ESA dose recommendation.

    Solves the fitted ODE for the weekly SC IU that brings Hb to the target
    midpoint at `horizon`, then applies hard safety constraints and per-cycle
    damping. Falls back to ml_acm._esa_recommendation when the ODE is not
    trustworthy for this patient.

    Returns a dict compatible with ml_acm._esa_recommendation plus:
        method, dose_response_curve, target_attainment.
    """
    # Import here to avoid a module-load cycle (ml_acm imports this module).
    from ml_acm import (
        _esa_recommendation, _to_float,
        HB_CEILING, ESA_MAX_INCREASE, ESA_MIN_DOSE_IU, TSAT_TARGET_LOW,
    )

    low, high = hb_target
    hb_mid = (low + high) / 2.0

    latest = records[0] if records else {}
    current_hb = _to_float(latest.get("hb"))

    def _fallback(reason: str) -> Dict:
        rec = _esa_recommendation(
            current_hb=current_hb,
            pred_1mo=current_hb, pred_3mo=current_hb,
            current_iu_sc=current_iu_sc,
            ferritin=ferritin, tsat=tsat, crp=crp,
            forecast_confidence=forecast_confidence,
            k_epo_near_zero=k_epo_near_zero,
        )
        rec["method"] = "heuristic-fallback"
        rec["dose_response_curve"] = []
        rec.setdefault("safety_flags", []).append(reason)
        return rec

    # ── Confidence gate: never dose-optimize on an unidentified k_epo ───────────
    trusted = (forecast_confidence in _TRUSTED_CONFIDENCE) and not k_epo_near_zero
    if not trusted or math.isnan(current_hb):
        return _fallback(
            f"Optimizer inactive (forecast '{forecast_confidence}'"
            f"{', k_epo≈0' if k_epo_near_zero else ''}) — using guideline step logic."
        )

    try:
        from ml_acm_ode import ode_predict_trajectory, hybrid_predict_trajectory
    except Exception as e:  # pragma: no cover
        return _fallback(f"ODE unavailable ({e}).")

    # Residual MLP correction is (approximately) dose-independent, so compute it
    # once at baseline and add it to every ODE evaluation during the search.
    correction = 0.0
    try:
        base_hybrid = hybrid_predict_trajectory(
            patient_id=patient_id, records=records, patient_meta=patient_meta,
            esa_scenario=current_iu_sc, horizon=horizon,
        )
        correction = float(base_hybrid.get("residual_correction") or 0.0)
    except Exception:
        pass
    decay = [1.0, 0.7, 0.4][min(horizon - 1, 2)]

    _cache: Dict[float, float] = {}

    def hb_at(dose: float) -> float:
        dose = round(max(0.0, dose), -1)  # 10-IU grid → stable cache keys
        if dose in _cache:
            return _cache[dose]
        od = ode_predict_trajectory(
            patient_id=patient_id, records=records,
            esa_scenario=dose, horizon=horizon,
        )
        if not od.get("available"):
            raise RuntimeError("ODE evaluation failed")
        hb = float(od["hb_ode_scenario"][horizon - 1]) + correction * decay
        _cache[dose] = hb
        return hb

    try:
        # Search bracket for the dose (weekly SC IU).
        cur = current_iu_sc if (current_iu_sc and current_iu_sc > 0) else 4000.0
        d_lo, d_hi = 0.0, max(cur * 4.0, 12000.0)
        hb_lo, hb_hi = hb_at(d_lo), hb_at(d_hi)

        if hb_hi < hb_mid:
            d_star = d_hi                     # even max dose undershoots
        elif hb_lo > hb_mid:
            d_star = d_lo                     # even zero dose overshoots
        else:
            # Monotone bisection on hb_at(d) − hb_mid.
            for _ in range(40):
                mid = 0.5 * (d_lo + d_hi)
                if hb_at(mid) < hb_mid:
                    d_lo = mid
                else:
                    d_hi = mid
                if d_hi - d_lo < 25.0:
                    break
            d_star = 0.5 * (d_lo + d_hi)
    except Exception as e:
        return _fallback(f"Optimizer search failed ({e}).")

    # ── Hard safety constraints ────────────────────────────────────────────────
    safety_flags: List[str] = []

    # 1. Hb above ceiling → unconditional hold (overrides optimum).
    if current_hb >= HB_CEILING:
        safety_flags.append(f"Hb {current_hb:.1f} ≥ {HB_CEILING} g/dL — hold ESA until Hb drops below 12.0")
        return {
            "action": "hold", "esa_change_pct": -100.0, "recommended_iu_sc": 0.0,
            "rationale": f"ESA held: Hb {current_hb:.1f} g/dL exceeds safety ceiling ({HB_CEILING} g/dL). Resume when Hb < 12.0.",
            "safety_flags": safety_flags, "method": "model-optimizer",
            "dose_response_curve": _dose_response_curve(hb_at, current_iu_sc),
            "target_attainment": None,
        }

    # 2. Hb ≥ 12 → force a reduction regardless of the optimum (KDIGO/TREAT).
    if current_hb >= 12.0 and current_iu_sc and current_iu_sc > 0:
        d_star = min(d_star, current_iu_sc * 0.75)
        safety_flags.append(f"Hb {current_hb:.1f} g/dL ≥ 12.0 — reduction enforced (CV/thrombotic risk; KDIGO §3.6.1).")

    # 3. Iron-first: do not escalate ESA into iron deficiency.
    iron_deficient = (
        (tsat is not None and tsat < TSAT_TARGET_LOW) or
        (ferritin is not None and ferritin < 100)
    )
    if iron_deficient and current_iu_sc and d_star > current_iu_sc:
        d_star = current_iu_sc
        safety_flags.append("Iron-deficient: ESA escalation capped — correct iron stores first (KDIGO §3.4.1).")

    # 4. Per-cycle damping (reduce Hb cycling): clamp change to [−50%, +50%].
    if current_iu_sc and current_iu_sc > 0:
        lo_cap = current_iu_sc * (1.0 - 0.50)
        hi_cap = current_iu_sc * (1.0 + ESA_MAX_INCREASE)
        d_capped = min(max(d_star, lo_cap), hi_cap)
        if abs(d_capped - d_star) > 1.0:
            safety_flags.append("Recommended change damped to ±50%/cycle to limit Hb cycling (KDIGO §3.4).")
        d_star = d_capped
        recommended_iu = round(max(ESA_MIN_DOSE_IU, d_star), -2)
        change_pct = round((recommended_iu - current_iu_sc) / current_iu_sc * 100.0, 1)
    else:
        recommended_iu = round(max(ESA_MIN_DOSE_IU, d_star), -2)
        change_pct = 0.0 if recommended_iu <= ESA_MIN_DOSE_IU else 100.0

    # Action label from the net change.
    if recommended_iu == 0.0:
        action = "hold"
    elif current_iu_sc and recommended_iu > current_iu_sc * 1.02:
        action = "increase"
    elif current_iu_sc and recommended_iu < current_iu_sc * 0.98:
        action = "decrease"
    elif not current_iu_sc:
        action = "increase"
    else:
        action = "maintain"

    # High CRP (only when present) — advisory, never blocks.
    if crp is not None and crp > 20:
        safety_flags.append(f"CRP {crp:.0f} mg/L — active inflammation may blunt ESA response; verify once resolved.")

    proj_hb = hb_at(recommended_iu)
    rationale = (
        f"Model-optimized: ODE projects Hb → {proj_hb:.1f} g/dL at +{horizon} mo on "
        f"{recommended_iu:,.0f} IU/week (target {low:.1f}–{high:.1f}, aim {hb_mid:.2f}). "
        f"{('Increase' if action=='increase' else 'Decrease' if action=='decrease' else 'Hold' if action=='hold' else 'Maintain')} "
        f"from {current_iu_sc:,.0f} IU/week." if current_iu_sc else
        f"Model-optimized starter dose {recommended_iu:,.0f} IU/week; ODE projects Hb → {proj_hb:.1f} g/dL at +{horizon} mo."
    )

    return {
        "action": action,
        "esa_change_pct": change_pct,
        "recommended_iu_sc": recommended_iu,
        "rationale": rationale,
        "safety_flags": safety_flags,
        "method": "model-optimizer",
        "dose_response_curve": _dose_response_curve(hb_at, recommended_iu),
        "target_attainment": _attainment_at(patient_id, records, recommended_iu, horizon, low, high, HB_CEILING),
    }


def _dose_response_curve(hb_at, marked_dose: Optional[float]) -> List[Dict]:
    """Sample Hb@horizon across a dose grid for the dashboard dose-response chart."""
    anchor = marked_dose if (marked_dose and marked_dose > 0) else 6000.0
    hi = max(anchor * 2.5, 12000.0)
    n = 12
    curve = []
    for i in range(n + 1):
        dose = round(hi * i / n, -2)
        try:
            curve.append({"dose": dose, "hb_horizon": round(hb_at(dose), 2)})
        except Exception:
            continue
    return curve


def _attainment_at(patient_id, records, dose, horizon, low, high, ceiling) -> Optional[Dict]:
    try:
        from ml_acm_ode import ode_predict_trajectory
        od = ode_predict_trajectory(patient_id=patient_id, records=records,
                                    esa_scenario=dose, horizon=horizon)
        if not od.get("available"):
            return None
        hb_h = float(od["hb_ode_scenario"][horizon - 1])
        sigma = float(od.get("uncertainty_band_gd") or 0.8) * math.sqrt(horizon)
        return target_attainment(hb_h, sigma, low=low, high=high, ceiling=ceiling)
    except Exception:
        return None


# ── IV iron optimizer ──────────────────────────────────────────────────────────

def optimize_iron(
    ferritin: Optional[float],
    tsat:     Optional[float],
    crp:      Optional[float],
) -> Dict:
    """Quantified IV-iron recommendation.

    Keeps every safety branch from ml_acm._iron_recommendation but, where
    supplementation is indicated, returns a numeric course dose (mg) instead of
    free text only. CRP is used only when present (RES-sequestration branch).
    """
    from ml_acm import (
        _iron_recommendation, FERRITIN_MAX, FERRITIN_REPLETE,
        TSAT_TARGET_LOW, TSAT_TARGET_HIGH, TSAT_CEILING,
    )

    base = _iron_recommendation(ferritin=ferritin, tsat=tsat, crp=crp)
    base["recommended_mg"] = None

    if base["action"] == "supplement":
        # Absolute deficiency (TSAT<20 or ferritin<100) → repletion course.
        # Functional deficiency (TSAT<30 & ferritin<200) → maintenance dose.
        absolute = (tsat is not None and tsat < TSAT_TARGET_LOW) or \
                   (ferritin is not None and ferritin < 100)
        if absolute:
            base["recommended_mg"] = 1000
            base["rationale"] += " Suggested course: 1000 mg IV iron (e.g. 5 × 200 mg iron sucrose) over 2 weeks, then recheck."
        else:
            base["recommended_mg"] = 200
            base["rationale"] += " Suggested maintenance: 200 mg IV iron this month."
    return base


# ── HIF-PHI (Desidustat) ESA-sparing suggestion ────────────────────────────────

def hifphi_switch(
    records:         List[Dict],
    eri:             Optional[float],
    resistance_flag: bool,
    current_esa_iu:  Optional[float],
    ferritin:        Optional[float],
    tsat:            Optional[float],
) -> Optional[Dict]:
    """Suggest an oral HIF-PHI (Desidustat) switch/optimization, or None.

    Triggers when a patient shows ESA hyporesistance on adequate iron (where
    HIF-PHIs, which also mobilize iron, may outperform escalating injectable ESA),
    or when the patient is already on Desidustat (surface it for continuity).
    Iron is checked with whatever labs exist; missing labs never force a switch.
    """
    from ml_esa import resolve_desidustat_weekly_iu

    already = bool(records) and (resolve_desidustat_weekly_iu(records[0]) or 0.0) > 0
    if already:
        return {
            "suggested": True,
            "reason": "Patient already on oral HIF-PHI (Desidustat); continue and titrate to Hb target.",
            "kind": "continue",
        }

    iron_adequate = (
        (tsat is None or tsat >= 20) and (ferritin is None or ferritin >= 100)
    )
    high_eri = eri is not None and eri > 10.0
    on_high_esa = bool(current_esa_iu) and current_esa_iu is not None and current_esa_iu >= 8000

    if (resistance_flag or high_eri) and iron_adequate and on_high_esa:
        return {
            "suggested": True,
            "reason": (
                "ESA hyporesponse on adequate iron with high dose requirement"
                + (f" (ERI {eri:.1f})" if eri is not None else "")
                + " — consider switching to an oral HIF-PHI (Desidustat), which raises "
                "endogenous EPO and mobilizes iron and may reduce injectable-ESA burden."
            ),
            "kind": "switch",
        }
    return None
