"""
tests/test_acm_optimizer.py
===========================
Unit tests for the model-based ACM dose optimizer (services/acm_optimizer.py)
and its integration points in ml_acm / ml_acm_ode.

These tests are pure (no DB): they build synthetic monthly-record dicts and pass
them through the ODE + optimizer directly. Per-patient ODE fits are cached to
models/ode_params/patient_<id>.json, so each test uses a unique high patient_id
and cleans up its cache file in teardown.
"""
import math
import os

import pytest

from services import acm_optimizer as opt
from ml_acm import (
    HB_CEILING, ESA_MIN_DOSE_IU, TSAT_TARGET_LOW,
    generate_acm_recommendation, _extract_acm_features, ACM_FEATURE_NAMES,
)
from ml_acm_ode import ODE_PARAMS_DIR, ode_predict_trajectory


def _mk_records(pairs, ferritin=300, tsat=28, crp=4, weight=70, retic=1.5):
    """Build newest-first monthly records from an oldest-first (hb, dose) list."""
    recs = []
    for i, (hb, dose) in enumerate(pairs):
        recs.append({
            "hb": hb, "serum_ferritin": ferritin, "tsat": tsat, "crp": crp,
            "epo_weekly_units": dose, "last_prehd_weight": weight,
            "target_dry_weight": weight - 2, "reticulocyte_count": retic,
            "record_month": f"2026-{i+1:02d}",
        })
    return list(reversed(recs))  # newest-first


def _cleanup(pid):
    path = os.path.join(ODE_PARAMS_DIR, f"patient_{pid}.json")
    if os.path.exists(path):
        os.remove(path)


# ── ERI ────────────────────────────────────────────────────────────────────────

def test_compute_eri_basic():
    # (6000/70)/10 ≈ 8.571
    assert opt.compute_eri(6000, 70, 10.0) == pytest.approx(8.571, abs=0.01)


def test_compute_eri_missing_inputs_returns_none():
    assert opt.compute_eri(None, 70, 10) is None
    assert opt.compute_eri(6000, None, 10) is None
    assert opt.compute_eri(6000, 70, 0) is None
    assert opt.compute_eri(0, 70, 10) is None


# ── target attainment probabilities ────────────────────────────────────────────

def test_target_attainment_bounds_and_center():
    ta = opt.target_attainment(10.75, 0.8)
    for k in ("p_in_target", "p_overshoot", "p_undershoot"):
        assert 0.0 <= ta[k] <= 1.0
    # Centered in band → in-target should dominate overshoot/undershoot.
    assert ta["p_in_target"] > ta["p_overshoot"]
    assert ta["p_in_target"] > ta["p_undershoot"]


def test_target_attainment_high_hb_overshoot():
    ta = opt.target_attainment(13.5, 0.8)
    assert ta["p_overshoot"] > 0.5
    assert ta["p_in_target"] < 0.2


# ── ODE monotonicity (the property the optimizer relies on) ─────────────────────

def test_hb_horizon_monotone_in_dose():
    pid = 900001
    try:
        recs = _mk_records([(9.2, 3000), (9.6, 4000), (10.0, 5000),
                            (10.3, 6000), (10.5, 6000), (10.6, 6000)])
        hbs = []
        for dose in (0, 3000, 6000, 9000, 12000):
            od = ode_predict_trajectory(patient_id=pid, records=recs,
                                        esa_scenario=dose, horizon=3)
            assert od["available"]
            hbs.append(od["hb_ode_scenario"][-1])
        # Non-decreasing in dose (k_epo >= 0).
        for a, b in zip(hbs, hbs[1:]):
            assert b >= a - 1e-6
        # Strictly responsive somewhere (calibrated k_epo > 0).
        assert hbs[-1] > hbs[0]
    finally:
        _cleanup(pid)


# ── Optimizer: lands in target on a calibrated patient ──────────────────────────

def test_optimizer_targets_band_when_calibrated():
    pid = 900002
    try:
        recs = _mk_records([(9.0, 3000), (9.5, 4000), (10.0, 5000),
                            (10.2, 5500), (10.3, 6000), (10.4, 6000)])
        rec = opt.optimize_esa(
            patient_id=pid, records=recs, current_iu_sc=6000,
            ferritin=300, tsat=28, crp=4,
            forecast_confidence="hybrid-calibrated", k_epo_near_zero=False,
        )
        assert rec["method"] == "model-optimizer"
        assert rec["recommended_iu_sc"] >= ESA_MIN_DOSE_IU
        # Projected Hb at the recommended dose should sit near the target band.
        ta = rec["target_attainment"]
        assert ta is not None
        assert 9.0 <= ta["hb_horizon"] <= 12.5
        # Dose-response curve is populated and monotone.
        curve = rec["dose_response_curve"]
        assert len(curve) >= 5
        ys = [p["hb_horizon"] for p in curve]
        assert all(b >= a - 1e-6 for a, b in zip(ys, ys[1:]))
    finally:
        _cleanup(pid)


# ── Hard safety constraints ─────────────────────────────────────────────────────

def test_hb_ceiling_forces_hold():
    pid = 900003
    try:
        recs = _mk_records([(11.0, 6000), (12.0, 6000), (12.8, 6000),
                            (13.2, 6000), (13.4, 6000), (13.6, 6000)])
        rec = opt.optimize_esa(
            patient_id=pid, records=recs, current_iu_sc=6000,
            ferritin=300, tsat=30, crp=3,
            forecast_confidence="hybrid-calibrated", k_epo_near_zero=False,
        )
        assert rec["action"] == "hold"
        assert rec["recommended_iu_sc"] == 0.0
    finally:
        _cleanup(pid)


def test_hb_above_12_enforces_reduction():
    pid = 900004
    try:
        recs = _mk_records([(10.5, 5000), (11.0, 5500), (11.5, 6000),
                            (11.8, 6000), (12.0, 6000), (12.3, 6000)])
        rec = opt.optimize_esa(
            patient_id=pid, records=recs, current_iu_sc=6000,
            ferritin=300, tsat=30, crp=3,
            forecast_confidence="hybrid-calibrated", k_epo_near_zero=False,
        )
        assert rec["recommended_iu_sc"] < 6000
    finally:
        _cleanup(pid)


def test_iron_deficient_caps_escalation():
    pid = 900005
    try:
        # Low Hb (would normally escalate) but iron-deficient (TSAT < 20).
        recs = _mk_records([(9.5, 5000), (9.3, 5000), (9.1, 5000),
                            (9.0, 5000), (8.9, 5000), (8.8, 5000)],
                           tsat=15, ferritin=80)
        rec = opt.optimize_esa(
            patient_id=pid, records=recs, current_iu_sc=5000,
            ferritin=80, tsat=15, crp=4,
            forecast_confidence="hybrid-calibrated", k_epo_near_zero=False,
        )
        # Must not escalate above the current dose while iron-deficient.
        assert rec["recommended_iu_sc"] <= 5000
        assert any("Iron-deficient" in f for f in rec["safety_flags"])
    finally:
        _cleanup(pid)


def test_min_dose_floor_respected():
    pid = 900006
    try:
        recs = _mk_records([(12.5, 2000), (12.6, 1500), (12.7, 1200),
                            (12.8, 1000), (12.9, 800), (12.8, 600)])
        rec = opt.optimize_esa(
            patient_id=pid, records=recs, current_iu_sc=600,
            ferritin=400, tsat=35, crp=3,
            forecast_confidence="hybrid-calibrated", k_epo_near_zero=False,
        )
        # Non-hold recommendations never fall below the minimum meaningful dose.
        if rec["action"] != "hold":
            assert rec["recommended_iu_sc"] >= ESA_MIN_DOSE_IU
    finally:
        _cleanup(pid)


# ── Confidence gating → heuristic fallback ──────────────────────────────────────

def test_low_confidence_falls_back_to_heuristic():
    pid = 900007
    try:
        recs = _mk_records([(9.5, 5000), (9.6, 5000), (9.7, 5000)])
        rec = opt.optimize_esa(
            patient_id=pid, records=recs, current_iu_sc=5000,
            ferritin=300, tsat=28, crp=4,
            forecast_confidence="population-prior", k_epo_near_zero=False,
        )
        assert rec["method"] == "heuristic-fallback"
    finally:
        _cleanup(pid)


def test_k_epo_near_zero_falls_back():
    pid = 900008
    try:
        recs = _mk_records([(10.0, 5000), (10.1, 5000), (10.0, 5000)])
        rec = opt.optimize_esa(
            patient_id=pid, records=recs, current_iu_sc=5000,
            ferritin=300, tsat=28, crp=4,
            forecast_confidence="hybrid-calibrated", k_epo_near_zero=True,
        )
        assert rec["method"] == "heuristic-fallback"
    finally:
        _cleanup(pid)


# ── Iron optimizer: quantified dose ─────────────────────────────────────────────

def test_iron_optimizer_quantifies_repletion():
    r = opt.optimize_iron(ferritin=80, tsat=15, crp=4)
    assert r["action"] == "supplement"
    assert r["recommended_mg"] == 1000


def test_iron_optimizer_overload_holds_no_dose():
    r = opt.optimize_iron(ferritin=900, tsat=40, crp=4)
    assert r["action"] == "hold"
    assert r["recommended_mg"] is None


def test_iron_optimizer_missing_labs_is_graceful():
    r = opt.optimize_iron(ferritin=None, tsat=None, crp=None)
    assert r["action"] == "check"
    assert r["recommended_mg"] is None


# ── CRP fully optional (per user data reality) ──────────────────────────────────

def test_recommendation_without_any_inflammation_labs():
    pid = 900009
    try:
        recs = _mk_records([(9.0, 3000), (9.5, 4000), (10.0, 5000),
                            (10.2, 5500), (10.3, 6000), (10.4, 6000)], crp=None)
        for r in recs:
            r.pop("crp", None)  # no CRP at all
        rec = generate_acm_recommendation(pid, recs, patient_meta={"age": 60, "sex": "M", "height": 170})
        assert rec["available"]
        # No CRP-driven "check CRP" or sequestration flag should appear.
        joined = " ".join(rec["safety_flags"]).lower()
        assert "check ferritin and tsat" not in joined or rec["iron_recommendation"]["action"] != "check"
    finally:
        _cleanup(pid)


# ── HIF-PHI switch suggestion ──────────────────────────────────────────────────

def test_hifphi_switch_on_resistance_high_esa():
    recs = _mk_records([(9.5, 12000), (9.4, 12000), (9.3, 12000)])
    s = opt.hifphi_switch(records=recs, eri=12.0, resistance_flag=True,
                          current_esa_iu=12000, ferritin=300, tsat=28)
    assert s is not None and s["suggested"] and s["kind"] == "switch"


def test_hifphi_no_switch_when_responsive():
    recs = _mk_records([(10.5, 4000), (10.6, 4000), (10.7, 4000)])
    s = opt.hifphi_switch(records=recs, eri=5.0, resistance_flag=False,
                          current_esa_iu=4000, ferritin=300, tsat=28)
    assert s is None


def test_hifphi_continue_when_already_on_desidustat():
    recs = _mk_records([(10.0, 0), (10.1, 0), (10.2, 0)])
    recs[0]["desidustat_dose"] = "100 mg TIW"
    s = opt.hifphi_switch(records=recs, eri=None, resistance_flag=False,
                          current_esa_iu=0, ferritin=300, tsat=28)
    assert s is not None and s["kind"] == "continue"


# ── Feature-schema extension ────────────────────────────────────────────────────

def test_feature_vector_length_matches_schema():
    recs = _mk_records([(10.0, 5000), (10.1, 5000), (10.2, 5000)])
    feats = _extract_acm_features(recs, patient_meta={"age": 60, "sex": "M", "height": 170})
    assert feats is not None
    assert len(feats) == len(ACM_FEATURE_NAMES) == 38


def test_new_features_impute_when_missing():
    # No il6/tnf/mis/hospitalization present → those slots are NaN (median-imputed later),
    # never raising.
    recs = _mk_records([(10.0, 5000), (10.1, 5000), (10.2, 5000)])
    feats = _extract_acm_features(recs, patient_meta={"age": 60, "sex": "M", "height": 170})
    il6_idx = ACM_FEATURE_NAMES.index("il6")
    assert math.isnan(feats[il6_idx])
    eri_idx = ACM_FEATURE_NAMES.index("eri")
    assert not math.isnan(feats[eri_idx])  # ERI computable from dose/weight/hb
