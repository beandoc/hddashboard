"""
tests/test_twin_adequacy_math.py
================================
Regression tests for the Digital Twin adequacy mathematics:

  - scenario spKt/V must scale with BOTH effective clearance and treatment
    time (Kt/V = K·t/V) — the pre-fix code re-evaluated the Daugirdas
    formula with the measured R at a different t, which barely moved
    (only the 0.008·t correction), massively underestimating
    session-duration effects;
  - the baseline arm must return exactly the measured Daugirdas anchor;
  - explicit nulls / missing UF volumes must never raise TypeError.

Pure dict-based unit tests — no database needed.
"""
import math

import pytest

from services.twin_adequacy import (
    calculate_ktv_daugirdas,
    simulate_ktv,
    simulate_urea_kinetics,
)
from services.twin_utils import _UREA_MG_DL_TO_BUN
from ml_twin import run_scenario


# ── Shared fixtures (plain dicts, mirroring routers/twin.py payloads) ─────────

PRE_UREA  = 100.0   # total urea mg/dL (converted to BUN internally)
POST_UREA = 35.0
WEIGHT    = 80.0    # pre-HD weight kg


def _records() -> list:
    return [{
        "hb":                 11.0,
        "tsat":               25.0,
        "pre_dialysis_urea":  PRE_UREA,
        "post_dialysis_urea": POST_UREA,
        "last_prehd_weight":  WEIGHT,
        "weight":             WEIGHT,
        "record_month":       "2026-05",
        "phosphorus":         5.0,
    }]


def _patient_info() -> dict:
    return {
        "id": 1, "age": 45, "sex": "Male", "height": 180.0,
        "weight": WEIGHT, "bia": None, "doppler": None,
        "dm": False, "chf": False, "cad": False,
        "cardiac_output": None, "albumin": 3.8,
    }


def _baseline_session() -> dict:
    return {
        "qb_ml_min":          300.0,
        "qd_ml_min":          500.0,
        "session_duration_h": 4.0,
        "uf_volume":          2000.0,   # mL
        "dialysate_temp":     36.5,
        "dialysate_sodium":   138,
        "pre_hd_sbp":         130.0,
        "weight_pre":         WEIGHT,
    }


# ── Module 4: simulate_urea_kinetics ──────────────────────────────────────────

def test_session_time_scales_sp_ktv():
    """Headline regression: 4h → 5h must scale spKt/V ≈ ×(5/4), not ×1.02."""
    res = simulate_urea_kinetics(
        baseline=_baseline_session(), scenario={"session_h": 5.0},
        patient_info=_patient_info(), records=_records(),
    )
    base, scen = res["baseline"]["sp_ktv"], res["scenario"]["sp_ktv"]
    assert base and scen
    ratio = scen / base
    # ≈ 5/4, modulo the small convective Kd shift (qf falls at longer td)
    assert 1.15 <= ratio <= 1.32, f"sp_ktv ratio {ratio:.3f} not ~1.25"


def test_baseline_anchor_invariance():
    """Empty scenario ⇒ scenario arm returns exactly the measured anchor."""
    res = simulate_urea_kinetics(
        baseline=_baseline_session(), scenario={},
        patient_info=_patient_info(), records=_records(),
    )
    assert res["scenario"]["sp_ktv"] == res["baseline"]["sp_ktv"]
    # baseline equals the Daugirdas anchor at baseline conditions
    anchor = calculate_ktv_daugirdas(
        PRE_UREA * _UREA_MG_DL_TO_BUN, POST_UREA * _UREA_MG_DL_TO_BUN,
        4.0, 2.0, WEIGHT - 2.0,
    )
    assert res["baseline"]["sp_ktv"] == pytest.approx(anchor, abs=0.002)


def test_qb_scaling_matches_kd_ratio():
    """Qb-only change scales spKt/V by the effective-clearance ratio."""
    res = simulate_urea_kinetics(
        baseline=_baseline_session(), scenario={"qb_ml_min": 400.0},
        patient_info=_patient_info(), records=_records(),
    )
    base, scen = res["baseline"], res["scenario"]
    assert base["sp_ktv"] and scen["sp_ktv"]
    sp_ratio = scen["sp_ktv"] / base["sp_ktv"]
    kd_ratio = scen["kd_effective"] / base["kd_effective"]
    assert sp_ratio == pytest.approx(kd_ratio, abs=0.01)
    assert scen["sp_ktv"] > base["sp_ktv"]


def test_session_without_uf_volume_does_not_crash():
    """Sessions without recorded UF (uf_volume=None) must default, not raise."""
    baseline = _baseline_session()
    baseline["uf_volume"] = None
    res = simulate_urea_kinetics(
        baseline=baseline, scenario={"session_h": 4.5},
        patient_info=_patient_info(), records=_records(),
    )
    assert res["baseline"]["kd"] is not None
    assert res["scenario"]["sp_ktv"] is not None


def test_mechanistic_fallback_without_bun_is_time_proportional():
    """Without measured BUN the Kd·t/V estimate is used and scales with t."""
    recs = _records()
    recs[0]["pre_dialysis_urea"] = None
    recs[0]["post_dialysis_urea"] = None
    res = simulate_urea_kinetics(
        baseline=_baseline_session(), scenario={"session_h": 5.0},
        patient_info=_patient_info(), records=recs,
    )
    base, scen = res["baseline"]["sp_ktv"], res["scenario"]["sp_ktv"]
    assert base and scen
    assert 1.15 <= scen / base <= 1.32


# ── Module 2: simulate_ktv ────────────────────────────────────────────────────

def test_module2_baseline_is_standard_daugirdas():
    pre_bun  = PRE_UREA * _UREA_MG_DL_TO_BUN
    post_bun = POST_UREA * _UREA_MG_DL_TO_BUN
    res = simulate_ktv(
        pre_bun=pre_bun, post_bun=post_bun,
        baseline_session_h=4.0, baseline_uf_L=2.0, pre_weight_kg=WEIGHT,
    )
    expected = calculate_ktv_daugirdas(pre_bun, post_bun, 4.0, 2.0, WEIGHT - 2.0)
    assert res["baseline_ktv"] == expected
    # no overrides ⇒ scenario equals baseline
    assert res["scenario_ktv"] == pytest.approx(res["baseline_ktv"], abs=0.002)


def test_module2_session_time_scales_diffusive_component():
    pre_bun  = PRE_UREA * _UREA_MG_DL_TO_BUN
    post_bun = POST_UREA * _UREA_MG_DL_TO_BUN
    res = simulate_ktv(
        pre_bun=pre_bun, post_bun=post_bun,
        baseline_session_h=4.0, baseline_uf_L=2.0, pre_weight_kg=WEIGHT,
        scenario_session_h=5.0,
    )
    R         = post_bun / pre_bun
    diffusive = -math.log(R - 0.008 * 4.0)
    expected_delta = diffusive * 0.25  # 25% more treatment time
    assert res["delta_ktv"] == pytest.approx(expected_delta, abs=0.02)
    assert res["delta_ktv"] > 0.2  # pre-fix code produced ≈ 0.025


def test_module2_invalid_inputs_return_none():
    res = simulate_ktv(
        pre_bun=None, post_bun=None,
        baseline_session_h=4.0, baseline_uf_L=2.0, pre_weight_kg=WEIGHT,
        scenario_session_h=5.0,
    )
    assert res["available"] is False
    assert res["baseline_ktv"] is None
    assert res["scenario_ktv"] is None


# ── run_scenario boundary: explicit nulls / junk must never raise ─────────────

def test_run_scenario_tolerates_explicit_nulls():
    result = run_scenario(
        patient_id=1,
        records=_records(),
        patient_info=_patient_info(),
        baseline_session=_baseline_session(),
        past_sessions=[_baseline_session()],
        monthly_data=_records()[0],
        monthly_records_3mo=_records(),
        scenario={"uf_volume_L": None, "session_h": None, "qb_ml_min": "350"},
    )
    # nulls dropped, numeric strings coerced
    assert "uf_volume_L" not in result["scenario"]
    assert "session_h" not in result["scenario"]
    assert result["scenario"]["qb_ml_min"] == 350.0
    assert result["ktv_extended"]["scenario"]["sp_ktv"] is not None


def test_run_scenario_drops_unparseable_values():
    result = run_scenario(
        patient_id=1,
        records=_records(),
        patient_info=_patient_info(),
        baseline_session=_baseline_session(),
        past_sessions=[_baseline_session()],
        monthly_data=_records()[0],
        monthly_records_3mo=_records(),
        scenario={"session_h": "not-a-number"},
    )
    assert "session_h" not in result["scenario"]
