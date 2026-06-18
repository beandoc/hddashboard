"""
ml_twin.py
==========
Digital Dialysis Twin (DDT) — integrated scenario runner.

Domain modules live in services/:
  twin_utils.py       — shared constants & utilities
  twin_hb.py          — Module 1: Hb kinetics
  twin_adequacy.py    — Modules 2 + 4: Kt/V & urea kinetics
  twin_idh_sim.py     — Module 3: IDH risk simulation
  twin_phosphate.py   — Module 5: phosphate kinetics
  twin_cascade.py     — cross-domain cascade summary

This file contains only the integrated runner (run_scenario) and the
Plotly data builder (build_twin_plotly_data), plus re-exports of the
public API names consumed by routers and tests.
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

# ── Domain service imports ────────────────────────────────────────────────────

from services.twin_utils import _safe_float, _UREA_MG_DL_TO_BUN
from services.twin_hb import simulate_hb_trajectory
from services.twin_adequacy import (
    calculate_ktv_daugirdas,
    simulate_ktv,
    simulate_urea_kinetics,
    _estimate_cardiac_output,
)
from services.twin_idh_sim import simulate_idh_risk, simulate_uf_rate_idh_curve
from services.twin_phosphate import simulate_phosphate
from services.twin_cascade import _cascade_summary

logger = logging.getLogger(__name__)

# ── Integrated Scenario Runner ────────────────────────────────────────────────


def run_scenario(
    patient_id:          int,
    records:             List[Dict],
    patient_info:        dict,
    baseline_session:    dict,
    past_sessions:       list,
    monthly_data:        dict,
    monthly_records_3mo: list,
    scenario:            dict,
    current_ktv:         Optional[float] = None,
    db:                  Optional[Session] = None,
) -> Dict:
    """
    Phase 1 integrated scenario runner — all five modules with cross-domain cascade.

    A single prescription change propagates across Hb, Kt/V, phosphate, and IDH.

    scenario keys (all optional):
        esa_weekly_iu         — ESA dose IU/week SC (set 0 to simulate stopping ESA)
        desidustat_weekly_iu  — Desidustat IU equivalent/week (set 0 to simulate stopping Desidustat)
        iron_tsat_target — target TSAT % after iron repletion
        session_h        — session duration hours
        qb_ml_min        — blood flow rate mL/min
        qd_ml_min        — dialysate flow rate mL/min
        uf_volume_L      — UF volume litres
        uf_rate_ml_kg_h  — UF rate mL/kg/h
        dialysate_temp   — °C
        dialysate_sodium — mEq/L
        p_binder_pbe     — phosphate binder dose PBE units/day
        p_intake_mg_day  — dietary phosphate mg/day
        koa_urea         — dialyser KoA (urea)
    """
    from services.nutrition_service import get_7day_rolling_mean_phosphate

    # Normalise the scenario once at the boundary: drop explicit nulls
    # (null ⇒ "not specified") and coerce values to float so no downstream
    # module can hit None-arithmetic TypeErrors.  Unparseable values are
    # dropped rather than crashing — the API layer rejects them with 422.
    scenario = {
        k: _safe_float(v) for k, v in (scenario or {}).items() if v is not None
    }
    scenario = {k: v for k, v in scenario.items() if not math.isnan(v)}

    # Query rolling mean dietary phosphate
    phosphate_data = {"value": 1200.0, "source": "default_1200mg"}
    if db is not None:
        try:
            from sqlalchemy.orm import Session
            phosphate_data = get_7day_rolling_mean_phosphate(db, patient_id)
        except Exception as e:
            logger.warning(f"Error querying dietary phosphate: {e}")
            
    latest = records[0] if records else {}
    from phosphate_model import calculate_record_pbe
    baseline_pbe = calculate_record_pbe(latest)
    if baseline_pbe <= 0.0:
        baseline_pbe = 3.0

    baseline_p_intake = phosphate_data.get("value") or 1200.0
    source = phosphate_data.get("source", "default_1200mg")
    
    if "p_intake_mg_day" in scenario:
        source = "manual_entry"
        
    baseline_session = {**baseline_session, "p_intake_mg_day": baseline_p_intake, "p_binder_pbe": baseline_pbe}
    pre_bun  = _safe_float(latest.get("pre_dialysis_urea"))
    post_bun = _safe_float(latest.get("post_dialysis_urea"))
    # Convert from total urea (mg/dL) to BUN (mg/dL) — factor cancels in Kt/V ratio
    if not math.isnan(pre_bun):  pre_bun  *= _UREA_MG_DL_TO_BUN
    if not math.isnan(post_bun): post_bun *= _UREA_MG_DL_TO_BUN

    # Working weight: use the value the assembly layer already resolved
    # (monthly pre-HD weight → recent session pre-weight → dry weight).  No
    # 70 kg fabrication — pre_wt stays NaN when genuinely unknown so the
    # weight-dependent domains can blank out with a hint.
    pre_wt   = _safe_float(patient_info.get("weight"))
    if math.isnan(pre_wt):
        pre_wt = _safe_float(latest.get("last_prehd_weight") or latest.get("weight"))
    weight_missing = math.isnan(pre_wt)

    base_h   = _safe_float(
        baseline_session.get("session_duration_h") or baseline_session.get("session_h")
    )
    duration_missing = math.isnan(base_h)
    if duration_missing:
        base_h = 4.0  # neutral value for any arithmetic; adequacy/fluid are gated separately
    base_uf_L = _safe_float(baseline_session.get("uf_volume"), 2500) / 1000

    # ── Data-availability gate ────────────────────────────────────────────────
    # Each domain declares the inputs it cannot compute without.  When a hard
    # input is missing the domain returns a blank result carrying `missing` and
    # `hint` instead of a number built on a fabricated default.
    albumin_present  = (latest.get("albumin") is not None) or (patient_info.get("albumin") is not None)
    tsat_present     = latest.get("tsat") is not None
    phos_present     = latest.get("phosphorus") is not None
    sbp_present      = baseline_session.get("pre_hd_sbp") is not None
    ufvol_present    = baseline_session.get("uf_volume") is not None
    height_present   = (patient_info.get("height") or patient_info.get("height_cm")) is not None
    ktv_present      = (current_ktv is not None) or (not math.isnan(pre_bun) and not math.isnan(post_bun))

    def _blank(missing: list, hint: str) -> dict:
        return {"available": False, "missing": missing, "hint": hint}

    data_availability: Dict[str, dict] = {}

    # ── 1. Hb kinetics ────────────────────────────────────────────────────────
    # Iron axis requires a real baseline TSAT.  When TSAT is unrecorded the iron
    # slider is neutralised (iron_boost_tsat=None ⇒ no fabricated repletion
    # effect off an assumed 25%) and the card carries a hint.
    hb_sim = simulate_hb_trajectory(
        records                = records,
        esa_scenario_iu        = scenario.get("esa_weekly_iu"),
        desidustat_scenario_iu = scenario.get("desidustat_weekly_iu"),
        iron_boost_tsat        = scenario.get("iron_tsat_target") if tsat_present else None,
        horizon_months         = 3,
    )
    if isinstance(hb_sim, dict) and hb_sim.get("available"):
        hb_sim["iron_axis_available"] = tsat_present
        if not tsat_present:
            hb_sim.setdefault("hints", []).append(
                "TSAT not recorded — iron-repletion simulation disabled; showing ESA-only "
                "trajectory. Enter a TSAT value to enable the iron axis."
            )
    data_availability["anemia"] = {
        "available": bool(isinstance(hb_sim, dict) and hb_sim.get("available")),
        "missing":   [] if (isinstance(hb_sim, dict) and hb_sim.get("available")) else ["baseline Hb"],
        "iron_axis": tsat_present,
    }

    # ── 2. Daugirdas spKt/V (simple, requires a measured anchor or pre/post urea)
    if ktv_present and not weight_missing:
        ktv_sim = simulate_ktv(
            pre_bun            = pre_bun if not math.isnan(pre_bun) else None,
            post_bun           = post_bun if not math.isnan(post_bun) else None,
            baseline_session_h = base_h,
            baseline_uf_L      = base_uf_L,
            pre_weight_kg      = pre_wt,
            scenario_session_h = scenario.get("session_h"),
            scenario_uf_L      = scenario.get("uf_volume_L"),
            current_ktv        = current_ktv,
        )
    else:
        _miss = (["recorded spKt/V or pre+post-dialysis urea"] if not ktv_present else []) \
              + (["pre-HD weight"] if weight_missing else [])
        ktv_sim = _blank(_miss,
            "Adequacy needs a recorded spKt/V (or pre & post-dialysis urea) and a pre-HD weight.")
    data_availability["adequacy"] = {"available": bool(ktv_present and not weight_missing),
                                     "missing": [] if (ktv_present and not weight_missing) else ktv_sim.get("missing", [])}

    # ── 3. IDH risk — cascade: longer session → lower effective UF rate ───────
    # If session_h changes but UF volume is the same, effective UF rate decreases.
    scen_session_h  = scenario.get("session_h", base_h)
    scen_uf_volume  = scenario.get("uf_volume_L", base_uf_L) * 1000  # to mL
    weight_for_rate = pre_wt or 70.0
    # Compute implied UF rate from volume + session duration
    implied_uf_rate = (scen_uf_volume / scen_session_h / weight_for_rate) if scen_session_h > 0 else None

    # weight_pre so IDH extractor uses the same weight as the twin (not just dry_weight)
    session_overrides: dict = {"weight_pre": weight_for_rate}
    if scenario.get("uf_rate_ml_kg_h") is not None:
        session_overrides["uf_rate_ml_kg_h"] = scenario["uf_rate_ml_kg_h"]
    elif implied_uf_rate is not None and ("session_h" in scenario or "uf_volume_L" in scenario):
        # Changed session duration OR UF volume → different effective rate → cascade into IDH
        session_overrides["uf_rate_ml_kg_h"] = round(implied_uf_rate, 2)
    if "session_h" in scenario:
        # IDH extractor reads duration_hours; keep in sync
        session_overrides["duration_hours"] = scen_session_h
    if scenario.get("dialysate_temp") is not None:
        session_overrides["dialysate_temp"] = scenario["dialysate_temp"]
    if scenario.get("dialysate_sodium") is not None:
        session_overrides["dialysate_sodium"] = scenario["dialysate_sodium"]
    if scenario.get("uf_volume_L") is not None:
        session_overrides["uf_volume"] = scenario["uf_volume_L"] * 1000

    idh_inputs_ok = (not weight_missing) and sbp_present
    if idh_inputs_ok:
        idh_sim = simulate_idh_risk(
            patient_info        = patient_info,
            baseline_session    = baseline_session,
            past_sessions       = past_sessions,
            monthly_data        = monthly_data,
            monthly_records_3mo = monthly_records_3mo,
            scenario_overrides  = session_overrides,
        )
        # ── 4. UF rate sweep (IDH heatmap) ────────────────────────────────────
        uf_curve = simulate_uf_rate_idh_curve(
            patient_info        = patient_info,
            baseline_session    = baseline_session,
            past_sessions       = past_sessions,
            monthly_data        = monthly_data,
            monthly_records_3mo = monthly_records_3mo,
        )
    else:
        _miss = (["pre-HD weight"] if weight_missing else []) + (["pre-HD SBP"] if not sbp_present else [])
        idh_sim  = _blank(_miss, "IDH risk needs a pre-HD weight and a recorded pre-HD systolic BP.")
        uf_curve = _blank(_miss, "UF-rate sweep needs a pre-HD weight and a recorded pre-HD systolic BP.")
    data_availability["idh"] = {"available": bool(idh_inputs_ok),
                                "missing": [] if idh_inputs_ok else idh_sim.get("missing", [])}

    # ── 5. Extended urea kinetics (Module 4) ──────────────────────────────────
    if ktv_present and not weight_missing:
        ktv_extended = simulate_urea_kinetics(
            baseline     = baseline_session,
            scenario     = scenario,
            patient_info = patient_info,
            records      = records,
            current_ktv  = current_ktv,
        )
    else:
        ktv_extended = _blank(
            ktv_sim.get("missing", []),
            "Urea kinetics need a recorded spKt/V (or pre & post-dialysis urea) and a pre-HD weight.")

    # ── 6. Phosphate kinetics (Module 5) ──────────────────────────────────────
    # Requires a measured serum phosphorus to anchor the 2-pool steady state;
    # without it the RK4 would run off an assumed 5.0 mg/dL.
    if phos_present:
        phosphate = simulate_phosphate(
            baseline     = baseline_session,
            scenario     = scenario,
            patient_info = patient_info,
            records      = records,
        )
    else:
        phosphate = _blank(["measured serum phosphorus"],
            "Phosphate kinetics need a measured serum phosphorus to anchor the model.")
    data_availability["phosphate"] = {"available": bool(phos_present),
                                      "missing": [] if phos_present else ["measured serum phosphorus"]}

    # ── 7. Two-compartment fluid/volume model (Abohtyra 2018) ─────────────────
    # If the patient has a DiaSense optical-sensor calibration on record, use
    # the measured k_r (diasense_k_r) instead of the population estimate
    # (weight × 0.006 mL/min/mmHg/kg).  This closes the sensor → twin loop:
    # every session's RBV curve refines the patient-specific refill coefficient
    # used by the next simulation.
    fluid_inputs_ok = (not weight_missing) and albumin_present and ufvol_present and (not duration_missing)
    fluid_volume = {}
    if not fluid_inputs_ok:
        _miss = (["pre-HD weight"] if weight_missing else []) \
              + (["serum albumin"] if not albumin_present else []) \
              + (["prescribed UF volume"] if not ufvol_present else []) \
              + (["session duration"] if duration_missing else [])
        fluid_volume = _blank(_miss,
            "The plasma-refilling (RBV) model needs pre-HD weight, serum albumin, "
            "prescribed UF volume and session duration.")
    try:
        if not fluid_inputs_ok:
            raise RuntimeError("fluid inputs unavailable")
        from fluid_volume_model import simulate_fluid_volume, build_fluid_volume_plotly

        scen_uf_vol_ml = scenario.get("uf_volume_L", base_uf_L) * 1000
        scen_h         = scenario.get("session_h", base_h)
        latest_albumin = (monthly_data.get("albumin") if monthly_data else None) or patient_info.get("albumin")

        # Fetch most-recent DiaSense k_r for this patient
        diasense_k_r: Optional[float] = None
        diasense_meta: dict = {}
        if db is not None:
            try:
                from database import DiaSenseCalibration
                cal = (
                    db.query(DiaSenseCalibration)
                    .filter(
                        DiaSenseCalibration.patient_id == patient_id,
                        DiaSenseCalibration.diasense_k_r.isnot(None),
                    )
                    .order_by(DiaSenseCalibration.session_date.desc())
                    .first()
                )
                if cal is not None:
                    diasense_k_r = cal.diasense_k_r
                    diasense_meta = {
                        "session_date":           str(cal.session_date),
                        "diasense_session_id":    cal.diasense_session_id,
                        "k_r_measured":           round(cal.diasense_k_r, 5),
                        "k_r_estimated":          round(cal.k_r_estimated, 5) if cal.k_r_estimated else None,
                        "rbv_nadir_pct":          cal.rbv_nadir_pct,
                        "rbv_nadir_time_min":     cal.rbv_nadir_time_min,
                        "rbv_breach":             cal.rbv_breach,
                        "uf_target_ml":           cal.uf_target_ml,
                        "uf_actual_ml":           cal.uf_actual_ml,
                        "uf_achievement_pct":     cal.uf_achievement_pct,
                        "uf_rate_ml_kg_h":        cal.uf_rate_ml_kg_h,
                        "plasma_refill_rate_ml_min": cal.plasma_refill_rate_ml_min,
                        "post_hd_cramps":         cal.post_hd_cramps,
                        "post_hd_nausea":         cal.post_hd_nausea,
                        "post_hd_dyspnea_likert": cal.post_hd_dyspnea_likert,
                        "post_hd_fatigue_likert": cal.post_hd_fatigue_likert,
                        "bcm_post_fluid_overload_l": cal.bcm_post_fluid_overload_l,
                        "bcm_delta_overhydration_l": cal.bcm_delta_overhydration_l,
                        "idh_observed":           cal.idh_observed,
                        "grade2plus_count":       cal.grade2plus_count,
                    }
            except Exception as _cal_exc:
                logger.debug("DiaSense calibration lookup skipped: %s", _cal_exc)

        fluid_sim = simulate_fluid_volume(
            weight_kg    = pre_wt,
            session_h    = scen_h,
            uf_volume_ml = scen_uf_vol_ml,
            albumin_g_dl = float(latest_albumin) if latest_albumin else 3.8,
            k_r_override = diasense_k_r,
        )
        fluid_volume = build_fluid_volume_plotly(fluid_sim)
        fluid_volume["raw"] = fluid_sim
        fluid_volume["diasense"] = diasense_meta
    except Exception as _fv_exc:
        logger.debug("Fluid volume model skipped: %s", _fv_exc)

    # ── 8. Cross-domain cascade summary ───────────────────────────────────────
    cascade = _cascade_summary(
        scenario  = scenario,
        baseline  = baseline_session,
        results   = {
            "ktv_extended": ktv_extended,
            "phosphate":    phosphate,
            "idh_sim":      idh_sim,
        },
    )

    # ── 8. Doppler Shunt & Hemodynamics ──────────────────────────────────────
    doppler = patient_info.get("doppler")
    qa = doppler.get("qa") if doppler else None
    
    # Baseline Cardiac Output (CO): measured if available, else estimated from
    # BSA — which needs real weight AND height (no 70 kg / 170 cm fabrication).
    co_measured = patient_info.get("cardiac_output")
    hemo_inputs_ok = (not weight_missing) and height_present
    co = co_measured
    if co is None and hemo_inputs_ok:
        sex_co    = str(patient_info.get("sex") or "m")
        age_co    = _safe_float(patient_info.get("age"), 50.0)
        height_co = _safe_float(patient_info.get("height") or patient_info.get("height_cm"))
        co = _estimate_cardiac_output(sex_co, age_co, height_co, pre_wt)

    shunt_ratio = None
    cardiac_strain = "unknown"
    if qa is not None and co:
        qa_l_min = qa / 1000.0
        shunt_ratio = qa_l_min / co
        if qa > 1500.0 or shunt_ratio > 0.30:
            cardiac_strain = "high"
        elif qa < 600.0 or shunt_ratio < 0.20:
            cardiac_strain = "low"
        else:
            cardiac_strain = "moderate"

    hemodynamics = {
        "available":      co is not None,
        "estimated_co":   round(co, 2) if co is not None else None,
        "co_is_measured": co_measured is not None,
        "shunt_ratio":    round(shunt_ratio, 3) if shunt_ratio is not None else None,
        "cardiac_strain": cardiac_strain,
        "qa":             qa,
        "hint": (None if co is not None else
                 "Cardiac output estimate needs pre-HD weight and height (or a measured value)."),
    }
    data_availability["hemodynamics"] = {"available": co is not None,
                                         "missing": [] if co is not None else (
                                             (["pre-HD weight"] if weight_missing else []) +
                                             (["height"] if not height_present else []))}

    return {
        "patient_id":   patient_id,
        "scenario":     scenario,
        "hb_sim":       hb_sim,
        "ktv_sim":      ktv_sim,
        "ktv_extended": ktv_extended,
        "phosphate":    phosphate,
        "idh_sim":      idh_sim,
        "uf_curve":     uf_curve,
        "cascade":      cascade,
        "hemodynamics": hemodynamics,
        "fluid_volume": fluid_volume,
        "bia":          patient_info.get("bia"),
        "doppler":      patient_info.get("doppler"),
        "dietary_phosphate_source": source,
        "weight_used_kg":    None if weight_missing else round(pre_wt, 1),
        "weight_source":     patient_info.get("weight_source"),
        "data_availability": data_availability,
    }


def build_twin_plotly_data(twin_result: Dict) -> Dict:
    """
    Convert run_scenario() output into Plotly chart traces (JSON-serialisable).
    Keys: hb_traces, ktv_bar_data, idh_gauge, uf_curve_traces,
          phosphate_bar_data, std_ktv_bar_data, cascade.
    """
    hb_sim      = twin_result.get("hb_sim", {})
    ktv_sim     = twin_result.get("ktv_sim", {})
    ktv_ext     = twin_result.get("ktv_extended", {})
    idh_sim     = twin_result.get("idh_sim", {})
    uf_curve    = twin_result.get("uf_curve", {})
    phosphate   = twin_result.get("phosphate", {})
    cascade     = twin_result.get("cascade", [])
    fluid_volume= twin_result.get("fluid_volume", {})

    # ── Hb trajectory + 80% prediction interval ──────────────────────────────
    months_labels = [f"Month +{m}" for m in hb_sim.get("months", [])]
    hb_traces = []
    if hb_sim.get("available"):
        # Baseline line
        hb_traces.append({
            "x": months_labels,
            "y": hb_sim.get("hb_baseline", []),
            "name": "Current Protocol",
            "mode": "lines+markers",
            "line": {"dash": "dash", "color": "#6c757d"},
            "marker": {"size": 6},
        })
        # Scenario upper PI bound (filled area)
        pi_upper = hb_sim.get("pi_upper_scenario")
        pi_lower = hb_sim.get("pi_lower_scenario")
        if pi_upper and pi_lower:
            hb_traces.append({
                "x": months_labels + list(reversed(months_labels)),
                "y": pi_upper + list(reversed(pi_lower)),
                "fill": "toself",
                "fillcolor": "rgba(13,110,253,0.10)",
                "line": {"color": "rgba(0,0,0,0)"},
                "name": "80% Prediction Interval",
                "showlegend": True,
                "hoverinfo": "skip",
            })
        # Scenario point estimate
        hb_traces.append({
            "x": months_labels,
            "y": hb_sim.get("hb_simulated", []),
            "name": "Proposed Scenario",
            "mode": "lines+markers",
            "line": {"color": "#0d6efd"},
            "marker": {"size": 8},
        })

    # ── spKt/V bar (Daugirdas) ────────────────────────────────────────────────
    ktv_bar_data = {}
    if ktv_sim.get("available"):
        scen_ktv = ktv_sim.get("scenario_ktv") or 0
        ktv_bar_data = {
            "categories": ["Baseline spKt/V", "Scenario spKt/V", "Target (≥1.2)"],
            "values":     [ktv_sim.get("baseline_ktv") or 0, scen_ktv, 1.2],
            "colors":     [
                "#6c757d",
                "#0d6efd" if scen_ktv >= 1.2 else "#dc3545",
                "#198754",
            ],
        }

    # ── Std Kt/V + eKt/V (extended urea kinetics) ────────────────────────────
    std_ktv_bar_data = {}
    if ktv_ext.get("available"):
        base = ktv_ext.get("baseline", {})
        scen = ktv_ext.get("scenario", {})
        std_ktv_bar_data = {
            "categories": [
                "Base eKt/V", "Scen eKt/V",
                "Base Std Kt/V", "Scen Std Kt/V",
                "Base Kd", "Scen Kd",
            ],
            "values": [
                base.get("e_ktv") or 0,
                scen.get("e_ktv") or 0,
                base.get("std_ktv") or 0,
                scen.get("std_ktv") or 0,
                (base.get("kd") or 0) / 100,   # scale for display alongside Kt/V
                (scen.get("kd") or 0) / 100,
            ],
            "base_sp":      base.get("sp_ktv"),
            "scen_sp":      scen.get("sp_ktv"),
            "base_kd":      base.get("kd"),
            "scenario_kd":  scen.get("kd"),
            "base_ektv":    base.get("e_ktv"),
            "scenario_ektv":scen.get("e_ktv"),
            "base_std":     base.get("std_ktv"),
            "scenario_std": scen.get("std_ktv"),
            "delta_sp_ktv": ktv_ext.get("delta_sp_ktv"),
            "delta_kd":     ktv_ext.get("delta_kd"),
        }

    # ── IDH gauge ─────────────────────────────────────────────────────────────
    idh_gauge = {}
    if idh_sim.get("available"):
        idh_gauge = {
            "baseline_pct":  idh_sim.get("baseline_risk_pct"),
            "scenario_pct":  idh_sim.get("scenario_risk_pct"),
            "delta":         idh_sim.get("delta_risk_pct"),
            "scenario_level":idh_sim.get("scenario_level"),
            "baseline_level":idh_sim.get("baseline_level"),
            "model_is_heuristic": idh_sim.get("model_is_heuristic", True),
            # Indicative uncertainty band (heuristic widths from MAPIE prediction set — not a rigorous PI)
            "pi_lower_pct":  round(idh_sim.get("scenario_pi_lower", 0) * 100, 1) if idh_sim.get("scenario_pi_lower") is not None else None,
            "pi_upper_pct":  round(idh_sim.get("scenario_pi_upper", 0) * 100, 1) if idh_sim.get("scenario_pi_upper") is not None else None,
        }

    # ── UF rate sweep ─────────────────────────────────────────────────────────
    uf_curve_traces = []
    if uf_curve.get("available"):
        risks = uf_curve.get("risks", [])
        mortality_thresh = uf_curve.get("mortality_threshold_ml_kg_h", 4.0)
        uf_curve_traces = [
            {
                "x":    [r["uf_rate"] for r in risks],
                "y":    [r["risk_pct"] for r in risks],
                "name": "IDH Risk vs UF Rate",
                "mode": "lines+markers",
                "line": {"color": "#dc3545"},
                "marker": {"size": 6},
            },
            {
                # Vertical reference line at the Castro & Wu NDT 2024 mortality threshold
                "x":    [mortality_thresh, mortality_thresh],
                "y":    [0, 100],
                "name": f"Mortality threshold {mortality_thresh} mL/kg/h (Castro & Wu NDT 2024)",
                "mode": "lines",
                "line": {"color": "#6f42c1", "dash": "dash", "width": 2},
                "hovertemplate": f"UF ≤{mortality_thresh} mL/kg/h associated with lower mortality risk<extra></extra>",
            },
        ]

    # ── Phosphate comparison ──────────────────────────────────────────────────
    phosphate_bar_data = {}
    if phosphate.get("available"):
        base_p = phosphate.get("baseline_p") or 0
        scen_p = phosphate.get("scenario_p") or 0
        def _p_color(v):
            if v > 5.5: return "#dc3545"
            if v < 3.5: return "#f59e0b"
            return "#198754"
        phosphate_bar_data = {
            "categories":       ["Baseline pre-P", "Scenario pre-P", "Upper target (5.5)", "Lower target (3.5)"],
            "values":           [base_p, scen_p, 5.5, 3.5],
            "colors":           [_p_color(base_p), _p_color(scen_p), "#dc3545", "#f59e0b"],
            "baseline_p":       base_p,
            "scenario_p":       scen_p,
            "delta_p":          phosphate.get("delta_p"),
            "baseline_status":  phosphate.get("baseline_status"),
            "scenario_status":  phosphate.get("scenario_status"),
            "measured_p":       phosphate.get("p_measured"),
            "mcmc_posterior":   phosphate.get("mcmc_posterior"),
        }

    return {
        "hb_traces":         hb_traces,
        "ktv_bar_data":      ktv_bar_data,
        "std_ktv_bar_data":  std_ktv_bar_data,
        "idh_gauge":         idh_gauge,
        "uf_curve_traces":   uf_curve_traces,
        "phosphate_bar_data":phosphate_bar_data,
        "cascade":           cascade,
        "mortality_threshold_ml_kg_h": twin_result.get("uf_curve", {}).get("mortality_threshold_ml_kg_h", 4.0),
        "fluid_volume":      fluid_volume,
    }
