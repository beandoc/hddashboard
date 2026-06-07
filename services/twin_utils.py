"""
services/twin_utils.py
======================
Shared constants and micro-utilities for the Digital Dialysis Twin service modules.
"""
from __future__ import annotations

# ── Population-level Bayesian priors ─────────────────────────────────────────
# Derived from published HD cohort data (Locatelli et al., Nephrol Dial Trans;
# Fishbane & Spinowitz, AJKD 2018; Macdougall et al., NDT 2010).
#
# Gaussian conjugate prior: θ ~ N(μ₀, σ₀²)
# Posterior after n observations: μₙ = (μ₀/σ₀² + Σxᵢyᵢ/σ_ε²) / (1/σ₀² + Σxᵢ²/σ_ε²)
#
# k_gain  [g/dL per (IU/kg/wk × 1000)]
# Formula: ΔHb = k_gain × (iu_norm × 1000) + ...
# At 100 IU/kg/wk: iu_norm×1000 = 100,000 → ΔHb = 1.0 g/dL/month (clinical literature)
# Therefore: k_gain = 1.0 / 100,000 = 1e-5
_PRIOR_K_GAIN_MU    = 1.0e-5  # population mean  (was 0.018 — 1000× too large, caused ceiling bug)
_PRIOR_K_GAIN_VAR   = (4.0e-6) ** 2  # SD ≈ 4e-6 (wide prior, ≈40% of mean)
_PRIOR_K_GAIN_MIN   = 2.0e-6  # poor responder
_PRIOR_K_GAIN_MAX   = 5.0e-5  # excellent responder

# k_iron  [g/dL per 1% TSAT increase per month]
_PRIOR_K_IRON_MU    = 0.015
_PRIOR_K_IRON_VAR   = 0.006 ** 2
_PRIOR_K_IRON_MIN   = 0.0
_PRIOR_K_IRON_MAX   = 0.05

# Observation noise: month-to-month Hb variability unexplained by ESA/iron
_OBS_NOISE_VAR      = 0.25 ** 2  # SD ≈ 0.25 g/dL (measurement + biological)

# Legacy scalar constants (kept for backward compatibility)
_POP_HB_GAIN_PER_1000IU  = _PRIOR_K_GAIN_MU
_POP_HB_DECAY_RATE        = 0.04
_POP_HB_IRON_BOOST        = 0.003
_POP_HB_TSAT_BOOST        = _PRIOR_K_IRON_MU
_POP_HB_NADIR             = 8.0     # g/dL — physiologic minimum modelled

# Session physics
_UF_IDH_THRESHOLD_ML_KG_H = 10.0   # mL/kg/h — above this IDH risk rises steeply

# Unit conversion — clinics record serum urea (mg/dL total urea); Daugirdas
# formula expects BUN (blood urea nitrogen).  BUN = urea × (28 / 60).
# NOTE: since Daugirdas uses only the ratio R = post/pre, both pre and post must
# use the *same* units — so the factor always cancels in Kt/V.  The conversion
# is applied for correctness of the BUN values themselves (e.g. display, audit).
_UREA_MG_DL_TO_BUN = 28.0 / 60.0   # ≈ 0.4667

# ── Helper utilities ──────────────────────────────────────────────────────────


def _safe_float(v, default: float = float("nan")) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


