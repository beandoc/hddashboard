"""
ml_acm_ode.py
=============
Physiologically-grounded erythropoiesis ODE for the Anemia Control Model.

Implements the hybrid architecture used by Fresenius Medical Care's ACM
(Fuertinger et al., J Theor Biol 2014; CJASN 2024):

    Hb_predicted(t+1) = Hb_ODE(t+1)  +  MLP_residual(t+1)
                           ↑ physiologic       ↑ population-level
                           patient-specific    correction

ODE — Simplified monthly discrete erythropoiesis:
─────────────────────────────────────────────────
    Hb(t+1) = Hb(t) × (1 - k_loss)
             + k_epo × EPO_norm(t) × iron_frac(t)
             + k_prod
             - crp_penalty × CRP(t)

    where:
        EPO_norm(t)   = weekly_IU_SC(t) / dry_weight_kg   [IU/kg/week]
        iron_frac(t)  = min(1, TSAT(t)/30) or min(1, ferritin(t)/200)
        crp_penalty   = fixed constant × CRP(mg/L)  (inflammation suppresses EPO response)

Patient-specific parameters (3, fitted per patient from ≥3 months of history):
    k_epo   ∈ [0.0, 0.15]   — ESA sensitivity (g/dL per IU/kg/week per month)
    k_prod  ∈ [0.0, 1.5]    — basal monthly Hb production (endogenous EPO contribution)
    k_loss  ∈ [0.1, 0.50]   — RBC fractional decay per month (~1/4 → 120-day lifespan)

Fitting:
    scipy.optimize.minimize (L-BFGS-B), objective = MSE(Hb_ODE, Hb_observed)
    Falls back to population-mean parameters when < 3 data points are available.

Residual MLP:
    Population-level MLP trained on [32-feature ACM vector] → residual(t+1)
    where residual(t+1) = Hb_observed(t+1) - Hb_ODE_predicted(t+1)
    Stored separately (models/acm_residual_mlp.pkl).
"""
from __future__ import annotations

import json
import logging
import math
import os
import warnings
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ── Optional imports ──────────────────────────────────────────────────────────

try:
    from scipy.optimize import minimize, Bounds
    _SCIPY_AVAILABLE = True
except ImportError:
    _SCIPY_AVAILABLE = False

try:
    import joblib
    _JOBLIB_AVAILABLE = True
except ImportError:
    _JOBLIB_AVAILABLE = False

try:
    from sklearn.neural_network import MLPRegressor
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.impute import SimpleImputer
    from sklearn.model_selection import cross_val_predict, KFold
    from sklearn.metrics import mean_absolute_error, r2_score
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

# ── Paths ─────────────────────────────────────────────────────────────────────

ODE_PARAMS_DIR    = os.path.join("models", "ode_params")
RESIDUAL_MLP_PATH = os.path.join("models", "acm_residual_mlp.pkl")

# ── Population-level parameter priors (fallback when < 3 months data) ────────
# Derived from Fuertinger et al. 2014 and Barbieri et al. 2016 HD cohort medians

# k_epo recentered at 0.030: steady-state Hb* = (k_epo·epo_norm·iron_frac + k_prod - crp_pen·CRP) / k_loss
# At typical maintenance (85 IU/kg/wk, TSAT≥30%, CRP 5): Hb* ≈ (0.030×85×1 + 0.35 - 0.02) / 0.25 ≈ 11.3 g/dL
# Prior was 0.012 → Hb* ≈ 5.4 g/dL, causing phantom Hb-collapse forecasts for uncalibrated patients.
_POP_K_EPO   = 0.030   # g/dL per IU/kg/week per month — physiologically recentered
_POP_K_PROD  = 0.35    # g/dL/month basal production (endogenous EPO equivalent)
_POP_K_LOSS  = 0.25    # 25% monthly fractional decay ≈ 120-day RBC lifespan
_CRP_PENALTY = 0.004   # g/dL per mg/L CRP per month — inflammation suppression

# ── Reticulocyte compartment ──────────────────────────────────────────────────
# 10-day maturation delay: k_mat = 1 − exp(−30/10) ≈ 0.95 per monthly step.
# This represents ~95% of the reticulocyte pool maturing to RBCs within one
# monthly window.  At monthly resolution the temporal lag itself is sub-step
# (~1/3 of a month), but the two-compartment structure still matters because:
#   1. It decouples ESA stimulation from Hb delivery, so a dose change mid-month
#      is correctly carried into the next step via the R state.
#   2. The 5% carry-over (1 − K_MAT) accumulates correctly during multi-step
#      forecasts — e.g. a +50% ESA escalation ramps up rather than spiking.
#   3. It prepares the architecture for biweekly/session resolution where the
#      10-day lag becomes a full time-step.
K_MAT = 0.95   # reticulocyte maturation fraction per monthly step

# Conversion: observed reticulocyte % → ODE R state (g/dL equiv).
# Derivation: circulating retics as Hb-eq = (retic_pct/100)×Hb;
# these represent K_MAT×R produced over RETIC_BLOOD_DAYS ≈ 1.5 days in blood.
# R = (retic_pct/100) × Hb × 30 / (K_MAT × RETIC_BLOOD_DAYS)
RETIC_BLOOD_DAYS = 1.5   # mean reticulocyte blood lifespan (days)

# Singleton residual MLP
_residual_pipeline: Optional[object] = None
_residual_trained_at: Optional[str] = None
_residual_metrics: Dict = {}


# ── ODE engine ────────────────────────────────────────────────────────────────

def _safe(v, default: float = float("nan")) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _iron_factor(tsat: float, ferritin: float) -> float:
    """Iron availability fraction [0, 1] — scales ESA effectiveness."""
    if not math.isnan(tsat):
        return float(np.clip(tsat / 30.0, 0.0, 1.0))
    if not math.isnan(ferritin):
        return float(np.clip(ferritin / 200.0, 0.0, 1.0))
    return 0.75   # population-median fallback


def ode_step(
    hb_t:       float,
    epo_norm:   float,
    iron_frac:  float,
    crp:        float,
    params:     Tuple[float, float, float],
) -> float:
    """
    Single monthly ODE step.

    Hb(t+1) = Hb(t)×(1 - k_loss) + k_epo×EPO_norm×iron_frac + k_prod - crp_pen×CRP
    Clipped to physiologic range [6, 18] g/dL.
    """
    k_epo, k_prod, k_loss = params
    crp_val = crp if (not math.isnan(crp) and crp >= 0) else 5.0
    next_hb = (
        hb_t * (1.0 - k_loss)
        + k_epo * epo_norm * iron_frac
        + k_prod
        - _CRP_PENALTY * crp_val
    )
    return float(np.clip(next_hb, 6.0, 18.0))


def ode_simulate(
    hb0:    float,
    inputs: List[Dict],          # list of dicts: epo_norm, iron_frac, crp
    params: Tuple[float, float, float],
) -> List[float]:
    """
    Simulate Hb trajectory from hb0 over len(inputs) monthly steps.
    Returns list of predicted Hb values [Hb(t+1), Hb(t+2), ...].
    Single-compartment; kept for reference — use ode_simulate_2c for all new code.
    """
    trajectory = []
    hb = hb0
    for inp in inputs:
        hb = ode_step(
            hb_t      = hb,
            epo_norm  = inp.get("epo_norm", 0.0),
            iron_frac = inp.get("iron_frac", 0.75),
            crp       = inp.get("crp", 5.0),
            params    = params,
        )
        trajectory.append(hb)
    return trajectory


# ── Two-compartment erythropoiesis (reticulocyte + RBC) ──────────────────────

def _r_steady_state(k_epo: float, epo_norm: float, iron_frac: float) -> float:
    """
    Steady-state reticulocyte pool (g/dL equiv) for constant ESA input.

    At steady state: R_ss = k_epo × EPO_norm × iron_frac / K_MAT
    Used to initialise the reticulocyte compartment from the most-recent
    observation so predictions start on the correct operating curve.
    """
    if K_MAT <= 0:
        return 0.0
    return float(np.clip(k_epo * epo_norm * iron_frac / K_MAT, 0.0, 10.0))


def _r_init(
    k_epo: float,
    epo_norm: float,
    iron_frac: float,
    hb: float,
    retic_pct: Optional[float] = None,
) -> float:
    """
    R initialisation: blend steady-state estimate with observed reticulocyte %.

    When retic_pct is available it directly constrains R, making k_epo far more
    identifiable in the optimisation. The blend weight (0.5/0.5) is conservative;
    neither source alone is definitive — the SS estimate assumes static inputs,
    while the retic lab has pre-analytical variability.

    Conversion (from RETIC_BLOOD_DAYS constant):
        R_obs = (retic_pct/100) × hb × 30 / (K_MAT × RETIC_BLOOD_DAYS)
    """
    r_ss = _r_steady_state(k_epo, epo_norm, iron_frac)
    if retic_pct is None or math.isnan(retic_pct) or hb <= 0:
        return r_ss
    r_obs = float(np.clip(
        (retic_pct / 100.0) * hb * 30.0 / (K_MAT * RETIC_BLOOD_DAYS),
        0.0, 10.0,
    ))
    return 0.5 * r_ss + 0.5 * r_obs


def ode_step_2c(
    hb_t:       float,
    r_t:        float,
    epo_norm:   float,
    iron_frac:  float,
    crp:        float,
    params:     Tuple[float, float, float],
    step_days:  float = 30.0,
) -> Tuple[float, float]:
    """
    Single step of the two-compartment erythropoiesis ODE.

    step_days (default 30) allows variable-interval observations — interim
    Hb entries recorded mid-month are handled without changing k_epo units.
    All monthly rates (k_epo, k_prod, k_loss, _CRP_PENALTY) are scaled by
    frac = step_days/30.  K_MAT uses a geometric interpolation so it reduces
    exactly to K_MAT at step_days=30 and approaches 0 for short intervals:

        k_mat_step = 1 − (1 − K_MAT)^(step_days/30)

    Reticulocyte pool:
        R(t+d) = (1 − k_mat_step) × R(t)  +  k_epo × EPO_norm × iron_frac × frac

    Hemoglobin:
        Hb(t+d) = Hb(t) × (1 − k_loss×frac)
               + k_mat_step × R(t)
               + k_prod × frac
               − CRP_PENALTY × CRP × frac

    At step_days=30 this is algebraically identical to the previous fixed-step
    version, so all calibrated per-patient parameters remain valid.

    Returns (hb_next, r_next), both clipped to physiologic bounds.
    """
    k_epo, k_prod, k_loss = params
    crp_val = crp if (not math.isnan(crp) and crp >= 0) else 5.0
    frac = step_days / 30.0
    k_mat_step = 1.0 - (1.0 - K_MAT) ** frac   # geometric: exact at 30, ~linear for short steps

    r_next = float(np.clip(
        (1.0 - k_mat_step) * r_t + k_epo * epo_norm * iron_frac * frac,
        0.0, 10.0,
    ))
    hb_next = float(np.clip(
        hb_t * (1.0 - k_loss * frac)
        + k_mat_step * r_t
        + k_prod * frac
        - _CRP_PENALTY * crp_val * frac,
        6.0, 18.0,
    ))
    return hb_next, r_next


def ode_simulate_2c(
    hb0:    float,
    r0:     float,
    inputs: List[Dict],
    params: Tuple[float, float, float],
) -> List[float]:
    """
    Simulate Hb trajectory from (hb0, r0) over len(inputs) monthly steps.

    The reticulocyte state is propagated internally.
    Returns Hb values only — [Hb(t+1), Hb(t+2), ...] — matching the shape of
    ode_simulate() so callers can switch without changing their result handling.
    """
    trajectory = []
    hb, r = hb0, r0
    for inp in inputs:
        hb, r = ode_step_2c(
            hb_t      = hb,
            r_t       = r,
            epo_norm  = inp.get("epo_norm", 0.0),
            iron_frac = inp.get("iron_frac", 0.75),
            crp       = inp.get("crp", 5.0),
            params    = params,
            step_days = inp.get("step_days", 30.0),   # variable-step support
        )
        trajectory.append(hb)
    return trajectory


# ── Patient-specific parameter fitting ───────────────────────────────────────

def _build_inputs_from_records(records: List[Dict]) -> List[Dict]:
    """
    Convert monthly records (newest-first) to ODE input sequence (oldest-first).
    Each entry: {epo_norm, iron_frac, crp}.

    epo_norm uses the PK-corrected IU so Mircera patients (factor≈5.45) have a
    proportionally higher epo_norm; their per-patient k_epo is then fitted lower,
    correctly separating Mircera's flat-exposure receptor pharmacology from
    pulsatile epoetin's pulsed stimulation.
    """
    from ml_esa import _resolve_pk_corrected_iu
    from services.interim_hb_service import _record_date

    records_asc = list(reversed(records))   # oldest-first
    inputs = []
    for i, rec in enumerate(records_asc):
        weight   = _safe(rec.get("last_prehd_weight") or rec.get("weight"), 70.0)
        iu_sc    = _resolve_pk_corrected_iu(rec) or 0.0
        epo_norm = (iu_sc / weight) if weight > 0 else 0.0
        tsat     = _safe(rec.get("tsat"))
        ferritin = _safe(rec.get("serum_ferritin"))
        crp      = _safe(rec.get("crp"), 5.0)

        # step_days: duration of the transition FROM this observation TO the next.
        # Use pre-computed value from merge_hb_sequence when present; otherwise
        # derive from adjacent record dates (monthly-only records → ~30 days).
        if i + 1 < len(records_asc):
            next_rec = records_asc[i + 1]
            step_days = float(next_rec.get("step_days") or 30.0)
            if step_days < 1.0:
                # Not set by merge — compute from dates
                d0 = _record_date(rec)
                d1 = _record_date(next_rec)
                if d0 is not None and d1 is not None:
                    step_days = max(1.0, float((d1 - d0).days))
                else:
                    step_days = 30.0
        else:
            step_days = 30.0  # last record: no successor

        inputs.append({
            "epo_norm":  epo_norm,
            "iron_frac": _iron_factor(tsat, ferritin),
            "crp":       crp if not math.isnan(crp) else 5.0,
            "step_days": step_days,
        })
    return inputs


def fit_patient_ode_params(
    records:    List[Dict],
    n_restarts: int = 5,
) -> Dict:
    """
    Fit patient-specific ODE parameters [k_epo, k_prod, k_loss] using scipy
    L-BFGS-B to minimise MSE(Hb_ODE_predicted, Hb_observed).

    Requires at least 3 monthly records with Hb. With fewer records returns
    population-mean parameters with calibrated=False.

    Returns:
        {
            k_epo, k_prod, k_loss,
            calibrated: bool,
            n_points:   int,
            mse:        float,
            mae:        float,
        }
    """
    hb_records = [r for r in records if _safe(r.get("hb")) is not None
                  and not math.isnan(_safe(r.get("hb")))]

    if len(hb_records) < 3 or not _SCIPY_AVAILABLE:
        return {
            "k_epo":      _POP_K_EPO,
            "k_prod":     _POP_K_PROD,
            "k_loss":     _POP_K_LOSS,
            "calibrated": False,
            "n_points":   len(hb_records),
            "mse":        float("nan"),
            "mae":        float("nan"),
        }

    # Oldest-to-newest
    hb_records_asc = list(reversed(hb_records))
    hb_obs = [_safe(r.get("hb")) for r in hb_records_asc]
    inputs_asc = _build_inputs_from_records(list(reversed(hb_records_asc)))

    # We predict Hb[1:] from Hb[0] using ODE — so n_points = len-1
    hb0       = hb_obs[0]
    hb_targets = np.array(hb_obs[1:])
    inputs_for_fit = inputs_asc[:-1]   # inputs driving steps 1..n-1

    # Use observed reticulocyte % at the oldest step to anchor R0 during fitting.
    # Falls back to steady-state inside _r_init when the field is absent.
    retic_pct_fit = _safe(hb_records_asc[0].get("reticulocyte_count"))

    if len(hb_targets) < 2:
        return {
            "k_epo":      _POP_K_EPO,
            "k_prod":     _POP_K_PROD,
            "k_loss":     _POP_K_LOSS,
            "calibrated": False,
            "n_points":   len(hb_records),
            "mse":        float("nan"),
            "mae":        float("nan"),
        }

    def objective(params):
        k_epo, k_prod, k_loss = params
        r0 = _r_init(k_epo, inputs_for_fit[0]["epo_norm"], inputs_for_fit[0]["iron_frac"],
                     hb0, retic_pct_fit)
        pred = ode_simulate_2c(hb0, r0, inputs_for_fit, (k_epo, k_prod, k_loss))
        mse_val = float(np.mean((np.array(pred) - hb_targets) ** 2))
        prior_penalty = (
            ((k_epo - _POP_K_EPO) / 0.02) ** 2 +   # widened from 0.01 → allows data to pull k_epo
            ((k_prod - _POP_K_PROD) / 0.15) ** 2 +
            ((k_loss - _POP_K_LOSS) / 0.05) ** 2
        )
        return mse_val + 0.01 * prior_penalty

    bounds = Bounds(
        lb=[0.0,  0.0,  0.10],
        ub=[0.15, 1.50, 0.50],
    )

    best_result = None
    # Multiple random restarts to escape local minima
    rng = np.random.default_rng(42)
    for _ in range(n_restarts):
        x0 = [
            rng.uniform(0.001, 0.08),
            rng.uniform(0.1,   0.8),
            rng.uniform(0.15,  0.40),
        ]
        try:
            res = minimize(objective, x0, method="L-BFGS-B", bounds=bounds,
                           options={"maxiter": 200, "ftol": 1e-9})
            if best_result is None or res.fun < best_result.fun:
                best_result = res
        except Exception:
            continue

    if best_result is None or best_result.fun > 100:
        # Fitting diverged — fall back to population priors
        return {
            "k_epo":      _POP_K_EPO,
            "k_prod":     _POP_K_PROD,
            "k_loss":     _POP_K_LOSS,
            "calibrated": False,
            "n_points":   len(hb_records),
            "mse":        float("nan"),
            "mae":        float("nan"),
        }

    k_epo, k_prod, k_loss = best_result.x
    r0_final = _r_init(k_epo, inputs_for_fit[0]["epo_norm"], inputs_for_fit[0]["iron_frac"],
                       hb0, retic_pct_fit)
    pred_final = ode_simulate_2c(hb0, r0_final, inputs_for_fit, (k_epo, k_prod, k_loss))
    mae = float(np.mean(np.abs(np.array(pred_final) - hb_targets)))
    mse = float(np.mean((np.array(pred_final) - hb_targets) ** 2))

    # ── k_epo=0 detection ─────────────────────────────────────────────────────
    # When the optimiser converges to k_epo≈0 it means:
    #   (a) ESA doses are all zero/unknown, OR
    #   (b) ESA changes in the history are too small to separate signal from noise
    # The ODE will still run but Hb trajectory will ignore ESA — flag prominently.
    k_epo_near_zero = float(k_epo) < 1e-4
    if k_epo_near_zero:
        logger.warning(
            "ODE fit: k_epo≈0 for patient — ESA history too sparse/uniform to calibrate. "
            "Hb predictions will use basal production only and will not respond to ESA changes."
        )

    # ── Parameter uncertainty (spread across restarts) ────────────────────────
    # Collect all successful restart endpoints to estimate parameter spread
    all_results = []
    rng2 = np.random.default_rng(123)
    for _ in range(max(n_restarts, 10)):
        x0 = [rng2.uniform(0.001, 0.08), rng2.uniform(0.1, 0.8), rng2.uniform(0.15, 0.40)]
        try:
            r2 = minimize(objective, x0, method="L-BFGS-B", bounds=bounds,
                          options={"maxiter": 100, "ftol": 1e-6})
            if r2.success and r2.fun < best_result.fun * 5:
                all_results.append(r2.x)
        except Exception:
            continue

    param_spread = float("nan")
    if len(all_results) >= 3:
        arr = np.array(all_results)
        # Spread = mean std across all 3 parameters, normalised to their range
        k_epo_std  = float(np.std(arr[:, 0])) / 0.15
        k_prod_std = float(np.std(arr[:, 1])) / 1.50
        k_loss_std = float(np.std(arr[:, 2])) / 0.50
        param_spread = round(float(np.mean([k_epo_std, k_prod_std, k_loss_std])), 4)

    # Confidence level: "high" if well-identified, "moderate" if spread, "low" if k_epo≈0
    if k_epo_near_zero:
        param_confidence = "low"
    elif not math.isnan(param_spread) and param_spread < 0.15:
        param_confidence = "high"
    elif not math.isnan(param_spread) and param_spread < 0.35:
        param_confidence = "moderate"
    else:
        param_confidence = "low"

    return {
        "k_epo":             round(float(k_epo), 6),
        "k_prod":            round(float(k_prod), 4),
        "k_loss":            round(float(k_loss), 4),
        "calibrated":        True,
        "k_epo_near_zero":   k_epo_near_zero,
        "param_spread":      param_spread,
        "param_confidence":  param_confidence,
        "n_points":          len(hb_records),
        "mse":        round(mse, 4),
        "mae":        round(mae, 4),
    }



# ── Parameter persistence (per-patient JSON) ─────────────────────────────────

def save_patient_params(patient_id: int, params: Dict) -> None:
    os.makedirs(ODE_PARAMS_DIR, exist_ok=True)
    path = os.path.join(ODE_PARAMS_DIR, f"patient_{patient_id}.json")
    with open(path, "w") as f:
        json.dump({**params, "patient_id": patient_id,
                   "saved_at": __import__("datetime").datetime.utcnow().isoformat()}, f)


def load_patient_params(patient_id: int) -> Optional[Dict]:
    path = os.path.join(ODE_PARAMS_DIR, f"patient_{patient_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def get_or_fit_patient_params(patient_id: int, records: List[Dict]) -> Dict:
    """Load cached params if fresh, else refit and save."""
    cached = load_patient_params(patient_id)
    n_current = len([r for r in records if r.get("hb") is not None])
    if cached and cached.get("n_points", 0) >= n_current and cached.get("calibrated"):
        return cached
    params = fit_patient_ode_params(records)
    save_patient_params(patient_id, params)
    return params


# ── ODE forward prediction ────────────────────────────────────────────────────

def ode_predict_trajectory(
    patient_id:    int,
    records:       List[Dict],
    esa_scenario:  Optional[float] = None,
    iron_scenario: Optional[float] = None,
    horizon:       int = 3,
) -> Dict:
    """
    Predict Hb trajectory using the patient-specific ODE.

    Args:
        patient_id:    Patient PK (for parameter cache).
        records:       Monthly records newest-first.
        esa_scenario:  Proposed weekly IU SC dose. None = keep current.
        iron_scenario: Proposed TSAT %. None = keep current.
        horizon:       Months ahead.

    Returns ODE prediction dict with calibration metadata.
    """
    from ml_esa import _resolve_pk_corrected_iu

    if not records or _safe(records[0].get("hb")) != _safe(records[0].get("hb")):
        return {"available": False, "error": "No baseline Hb"}

    params     = get_or_fit_patient_params(patient_id, records)
    ode_params = (params["k_epo"], params["k_prod"], params["k_loss"])

    rec    = records[0]
    hb0    = _safe(rec.get("hb"))
    weight = _safe(rec.get("last_prehd_weight") or rec.get("weight"), 70.0)

    # Scenario inputs — use PK-corrected IU so the ODE trajectory correctly
    # reflects the drug's actual monthly AUC, not a flat weekly-IU proxy.
    # esa_scenario is a raw weekly IU change; the PK factor from the current
    # drug type is preserved when computing the scenario norm.
    curr_iu   = _resolve_pk_corrected_iu(rec) or 0.0
    scen_iu   = esa_scenario if esa_scenario is not None else curr_iu
    scen_norm = (scen_iu / weight) if weight > 0 else 0.0

    tsat     = _safe(rec.get("tsat"))
    ferritin = _safe(rec.get("serum_ferritin"))
    scen_tsat = iron_scenario if iron_scenario is not None else tsat
    iron_frac = _iron_factor(scen_tsat, ferritin)
    crp       = _safe(rec.get("crp"), 5.0)

    # Also simulate baseline (no change) for comparison
    base_norm  = (curr_iu / weight) if weight > 0 else 0.0
    base_ifrac = _iron_factor(tsat, ferritin)

    future_inputs_scen = [
        {"epo_norm": scen_norm, "iron_frac": iron_frac,  "crp": crp}
        for _ in range(horizon)
    ]
    future_inputs_base = [
        {"epo_norm": base_norm, "iron_frac": base_ifrac, "crp": crp}
        for _ in range(horizon)
    ]

    # Initialise reticulocyte pool.  When reticulocyte_count (%) is available it
    # is blended with the steady-state estimate via _r_init, making k_epo better
    # identified.  Scenario and baseline differ only in their epo_norm/iron_frac.
    retic_pct = _safe(rec.get("reticulocyte_count"))
    r0_scen = _r_init(ode_params[0], scen_norm, iron_frac, hb0, retic_pct)
    r0_base = _r_init(ode_params[0], base_norm, base_ifrac, hb0, retic_pct)

    traj_scen = ode_simulate_2c(hb0, r0_scen, future_inputs_scen, ode_params)
    traj_base = ode_simulate_2c(hb0, r0_base, future_inputs_base, ode_params)

    # ── Prediction intervals ───────────────────────────────────────────────────
    # Use ODE fitting MAE as the 1-σ uncertainty estimate, widened proportionally
    # with forecast horizon (uncertainty accumulates over time: σ(t) = MAE × √t).
    # 80% interval ≈ ±1.28σ.  Falls back to population-derived MAE when not calibrated.
    ode_mae = params.get("mae")
    if ode_mae is None or math.isnan(ode_mae):
        ode_mae = 0.8   # population-level MAE for HD patients without calibration

    # Additional uncertainty for k_epo≈0 case
    if params.get("k_epo_near_zero"):
        ode_mae = max(ode_mae, 1.2)

    # Confidence multiplier from parameter spread
    conf_mult = {"high": 1.0, "moderate": 1.3, "low": 1.8}.get(
        params.get("param_confidence", "moderate"), 1.3
    )
    sigma_base = ode_mae * conf_mult

    pi_lower_scen, pi_upper_scen = [], []
    pi_lower_base, pi_upper_base = [], []
    for t, (hbs, hbb) in enumerate(zip(traj_scen, traj_base), 1):
        sigma_t = sigma_base * math.sqrt(t)  # uncertainty widens with horizon
        k = 1.28   # 80% prediction interval
        pi_lower_scen.append(round(max(4.0, hbs - k * sigma_t), 2))
        pi_upper_scen.append(round(min(18.0, hbs + k * sigma_t), 2))
        pi_lower_base.append(round(max(4.0, hbb - k * sigma_t), 2))
        pi_upper_base.append(round(min(18.0, hbb + k * sigma_t), 2))

    warnings_list = []
    if params.get("k_epo_near_zero"):
        warnings_list.append(
            "k_epo≈0: ESA dose history too sparse to calibrate — "
            "Hb predictions do NOT respond to ESA changes. Needs ≥3 months with varying ESA doses."
        )
    if params.get("param_confidence") == "low":
        warnings_list.append("Low parameter confidence — prediction intervals are wide. More history needed.")

    return {
        "available":          True,
        "hb_current":         round(hb0, 2),
        "months":             list(range(1, horizon + 1)),
        "hb_ode_scenario":    [round(v, 2) for v in traj_scen],
        "hb_ode_baseline":    [round(v, 2) for v in traj_base],
        "pi_lower_scenario":  pi_lower_scen,
        "pi_upper_scenario":  pi_upper_scen,
        "pi_lower_baseline":  pi_lower_base,
        "pi_upper_baseline":  pi_upper_base,
        "uncertainty_band_gd": round(sigma_base, 3),
        "params":             params,
        "confidence":         params.get("param_confidence", "moderate") if params["calibrated"] else "population-prior",
        "n_points":           params["n_points"],
        "ode_mae":            params.get("mae"),
        "warnings":           warnings_list,
    }


# ── Residual MLP (population-level correction) ───────────────────────────────

def train_residual_mlp(
    db,
    patient_records_map: Optional[Dict[int, List[Dict]]] = None,
) -> Dict:
    """
    Train the residual MLP on [ODE_error = Hb_observed - Hb_ODE] across all patients.

    The residual captures what the ODE misses:
        - Inflammation spikes (CRP)
        - Transfusion boluses
        - Iron status transitions
        - Individual lab variation

    Args:
        db: SQLAlchemy session.
        patient_records_map: {patient_id: [records]} — pre-loaded to avoid N+1.
                             If None, loads from DB.
    Returns metric dict.
    """
    if not _SKLEARN_AVAILABLE:
        return {"success": False, "error": "scikit-learn unavailable"}

    global _residual_pipeline, _residual_trained_at, _residual_metrics

    from database import MonthlyRecord, Patient
    from ml_acm import _extract_acm_features, _row_to_dict

    patients = db.query(Patient).all()
    X_rows, y_residuals = [], []

    for patient in patients:
        if patient_records_map and patient.id in patient_records_map:
            recs_orm = patient_records_map[patient.id]
        else:
            recs_orm = (
                db.query(MonthlyRecord)
                .filter(MonthlyRecord.patient_id == patient.id)
                .order_by(MonthlyRecord.record_month.desc())
                .all()
            )
        if len(recs_orm) < 4:
            continue

        pm = {
            "age":    getattr(patient, "age", None),
            "sex":    getattr(patient, "sex", None) or getattr(patient, "gender", None),
            "height": getattr(patient, "height", None),
        }
        dicts = [_row_to_dict(r) for r in recs_orm]

        # Walk-forward ODE params cache for this patient.
        # Key = start index into dicts (newest-first); value = (k_epo, k_prod, k_loss).
        # For step t we fit on dicts[t:] — records that do NOT include the target
        # dicts[t-1] — so the ODE is never calibrated on the point it must predict.
        # Fits are cached by start index to avoid re-running the scipy optimiser for
        # identical record slices within the same patient loop.
        _wf_cache: dict = {}

        def _wf_ode_params(start: int) -> tuple:
            if start not in _wf_cache:
                p = fit_patient_ode_params(dicts[start:])
                _wf_cache[start] = (p["k_epo"], p["k_prod"], p["k_loss"])
            return _wf_cache[start]

        for t in range(1, len(dicts)):
            if dicts[t - 1].get("hb") is None:
                continue

            # Interim records lack full clinical features — skip MLP residual for
            # them.  They DO contribute to ODE fitting via fit_patient_ode_params
            # (which sees the full merged sequence) so they improve k_epo even
            # though we don't generate MLP training rows here.
            if dicts[t].get("is_interim"):
                continue

            feats = _extract_acm_features(dicts[t:], patient_meta=pm)
            if feats is None:
                continue

            # ODE prediction for step t → t-1 using walk-forward params.
            # step_days: duration of the transition from dicts[t] (older) to
            # dicts[t-1] (newer). Pre-computed by merge_hb_sequence; defaults
            # to 30 days for monthly-only records.
            step_d = float(dicts[t - 1].get("step_days") or 30.0)

            hb_t = _safe(dicts[t].get("hb"))
            if math.isnan(hb_t):
                continue
            ode_params_t = _wf_ode_params(t)
            inp  = _build_inputs_from_records([dicts[t]])[0]
            retic_t = _safe(dicts[t].get("reticulocyte_count"))
            r_ss = _r_init(ode_params_t[0], inp["epo_norm"], inp["iron_frac"], hb_t, retic_t)
            hb_ode, _ = ode_step_2c(
                hb_t, r_ss, inp["epo_norm"], inp["iron_frac"], inp["crp"],
                ode_params_t, step_days=step_d,
            )
            hb_actual = _safe(dicts[t - 1].get("hb"))
            if math.isnan(hb_actual):
                continue
            residual = hb_actual - hb_ode

            X_rows.append(feats)
            y_residuals.append(residual)

    if len(X_rows) < 10:
        return {"success": False, "error": f"Insufficient training data (n={len(X_rows)})"}

    X = np.array(X_rows)
    y = np.array(y_residuals)

    pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler",  StandardScaler()),
        ("mlp",     MLPRegressor(
            hidden_layer_sizes=(64, 32),
            activation="relu",
            solver="adam",
            alpha=1e-3,
            max_iter=500,
            early_stopping=True,
            validation_fraction=0.15,
            random_state=42,
        )),
    ])

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cv = KFold(n_splits=min(5, len(X)), shuffle=True, random_state=42)
        y_cv = cross_val_predict(pipeline, X, y, cv=cv)

    mae = mean_absolute_error(y, y_cv)
    r2  = r2_score(y, y_cv)
    pipeline.fit(X, y)

    _residual_pipeline   = pipeline
    _residual_trained_at = __import__("datetime").datetime.utcnow().isoformat()
    _residual_metrics    = {"mae_cv": round(mae, 3), "r2_cv": round(r2, 3), "n_samples": len(X)}

    if _JOBLIB_AVAILABLE:
        os.makedirs("models", exist_ok=True)
        joblib.dump(pipeline, RESIDUAL_MLP_PATH)
        
        try:
            import hashlib
            import json
            from database import SessionLocal, ModelArtifact
            from ml_acm import ACM_FEATURE_NAMES
            import datetime as dt_pkg
            
            with open(RESIDUAL_MLP_PATH, "rb") as f_bin:
                model_bin_data = f_bin.read()
                
            _art_db = SessionLocal()
            try:
                training_data_hash = hashlib.sha256(
                    json.dumps(X_rows, sort_keys=True).encode()
                ).hexdigest()
                
                art = ModelArtifact(
                    model_name          = "acm_v1",
                    version             = _residual_trained_at,
                    trained_at          = dt_pkg.datetime.utcnow(),
                    training_data_hash  = training_data_hash,
                    metrics_json        = json.dumps(_residual_metrics),
                    feature_schema_json = json.dumps(ACM_FEATURE_NAMES),
                    artifact_path       = RESIDUAL_MLP_PATH,
                    model_binary        = model_bin_data,
                )
                _art_db.add(art)
                _art_db.commit()
            finally:
                _art_db.close()
        except Exception as _art_exc:
            logger.warning("Failed to register acm_v1 ModelArtifact: %s", _art_exc)

    logger.info(f"Residual MLP trained: n={len(X)}, residual MAE={mae:.3f}, R²={r2:.3f}")
    return {"success": True, "n_samples": len(X), "residual_mae_cv": mae, "r2_cv": r2}


def _load_residual_mlp() -> bool:
    global _residual_pipeline, _residual_trained_at
    if _residual_pipeline is not None:
        return True
    if not _JOBLIB_AVAILABLE or not os.path.exists(RESIDUAL_MLP_PATH):
        return False
    try:
        _residual_pipeline   = joblib.load(RESIDUAL_MLP_PATH)
        _residual_trained_at = __import__("datetime").datetime.utcfromtimestamp(
            os.path.getmtime(RESIDUAL_MLP_PATH)).isoformat()
        return True
    except Exception:
        return False


def residual_correction(feats: np.ndarray) -> float:
    """Return MLP residual correction for a feature vector. 0.0 if model unavailable."""
    if not _load_residual_mlp() or _residual_pipeline is None:
        return 0.0
    try:
        return float(_residual_pipeline.predict(feats.reshape(1, -1))[0])
    except Exception:
        return 0.0


# ── Hybrid ODE + residual MLP prediction ─────────────────────────────────────

def hybrid_predict_trajectory(
    patient_id:    int,
    records:       List[Dict],
    patient_meta:  Optional[Dict] = None,
    esa_scenario:  Optional[float] = None,
    iron_scenario: Optional[float] = None,
    horizon:       int = 3,
) -> Dict:
    """
    Full hybrid prediction: ODE(patient-specific) + residual MLP(population).

    Returns the same shape as ml_acm.predict_hb_trajectory for drop-in replacement.
    """
    from ml_acm import _extract_acm_features

    # 1. ODE trajectory
    ode_result = ode_predict_trajectory(
        patient_id    = patient_id,
        records       = records,
        esa_scenario  = esa_scenario,
        iron_scenario = iron_scenario,
        horizon       = horizon,
    )

    if not ode_result.get("available"):
        return {"available": False, "error": ode_result.get("error", "ODE failed")}

    # 2. Residual MLP correction (one step ahead only; assume correction constant over horizon)
    feats = _extract_acm_features(records, patient_meta=patient_meta)
    correction = residual_correction(feats) if feats is not None else 0.0
    # Decay correction over horizon (it's based on current state, less reliable further out)
    decay = [1.0, 0.7, 0.4]

    ode_scen  = ode_result["hb_ode_scenario"]
    ode_base  = ode_result["hb_ode_baseline"]

    hybrid_scen = [
        round(float(np.clip(ode_scen[i] + correction * decay[min(i, 2)], 6.0, 18.0)), 2)
        for i in range(horizon)
    ]
    hybrid_base = [
        round(float(np.clip(ode_base[i] + correction * decay[min(i, 2)], 6.0, 18.0)), 2)
        for i in range(horizon)
    ]

    confidence = (
        "hybrid-calibrated" if ode_result["params"]["calibrated"] and _load_residual_mlp()
        else "ode-calibrated" if ode_result["params"]["calibrated"]
        else "population-prior"
    )

    # Pass prediction intervals through from ODE result
    return {
        "available":            True,
        "predictions": [
            {"month_offset": i + 1, "predicted_hb": hybrid_scen[i]}
            for i in range(horizon)
        ],
        "hb_ode_scenario":      ode_scen,
        "hb_ode_baseline":      ode_base,
        "hb_hybrid_scenario":   hybrid_scen,
        "hb_hybrid_baseline":   hybrid_base,
        "pi_lower_scenario":    ode_result.get("pi_lower_scenario"),
        "pi_upper_scenario":    ode_result.get("pi_upper_scenario"),
        "pi_lower_baseline":    ode_result.get("pi_lower_baseline"),
        "pi_upper_baseline":    ode_result.get("pi_upper_baseline"),
        "uncertainty_band_gd":  ode_result.get("uncertainty_band_gd"),
        "residual_correction":  round(correction, 3),
        "ode_params":           ode_result["params"],
        "confidence":           confidence,
        "n_points":             ode_result["n_points"],
        "ode_mae":              ode_result.get("ode_mae"),
        "residual_metrics":     _residual_metrics,
        "warnings":             ode_result.get("warnings", []),
    }


def get_ode_model_status() -> Dict:
    """Return ODE + residual MLP status for the audit dashboard."""
    residual_loaded = _load_residual_mlp()
    n_calibrated = 0
    if os.path.exists(ODE_PARAMS_DIR):
        n_calibrated = len([
            f for f in os.listdir(ODE_PARAMS_DIR)
            if f.endswith(".json")
        ])
    return {
        "ode_available":        True,
        "scipy_available":      _SCIPY_AVAILABLE,
        "n_patients_calibrated":n_calibrated,
        "residual_mlp_loaded":  residual_loaded,
        "residual_trained_at":  _residual_trained_at,
        "residual_metrics":     _residual_metrics,
    }
