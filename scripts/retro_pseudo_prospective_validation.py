#!/usr/bin/env python3
"""
retro_pseudo_prospective_validation.py
=======================================
Quick Win A: Retrospective "Pseudo-Prospective" Validation

Scientific Protocol
-------------------
For each eligible patient we repeatedly perform the following simulation,
stepping forward in time across all available monthly records:

  Given:
    - History up to Month N-2  (training / calibration window)
    - ACTUAL ESA dose used in Month N-1  (the real-world prescription)

  Predict:
    - Hb at Month N  (the verification target)

  Compare:
    - Predicted Hb(N) vs. Actual Hb(N) measured in the lab

  Compute:
    - Absolute prediction error (APE) = |predicted - actual|
    - Signed error (bias) = predicted - actual

This directly mirrors how a nephrologist would use the tool prospectively:
  "I am changing the dose THIS month — what will the Hb be NEXT month?"

Output
------
  - Per-patient table of predictions vs. actuals
  - Fleet-level metrics: MAE, RMSE, R², calibration slope
  - Scatter plot (actual vs. predicted)  →  saved as PNG
  - Reliability diagram (Hb bins)
  - Summary report printed to console

Usage
-----
  cd /path/to/HD Dashboard
  python scripts/retro_pseudo_prospective_validation.py

  Optional flags:
    --min-records N       Minimum monthly records to include a patient  [default: 4]
    --plot                Save matplotlib plots to scripts/output/
    --csv PATH            Export detailed results to CSV
    --verbose             Print per-patient predictions
"""

import argparse
import os
import sys
import math
import json
from datetime import datetime
from collections import defaultdict

# ── Ensure we can import from the project root ────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import numpy as np

# ── Project imports ───────────────────────────────────────────────────────────
try:
    from database import SessionLocal, Patient, MonthlyRecord
    from ml_acm_ode import fit_patient_ode_params, ode_simulate, _build_inputs_from_records
    from ml_esa import _resolve_weekly_iu_sc
    from ml_acm import _row_to_dict, _extract_acm_features
    from ml_acm_ode import residual_correction, _load_residual_mlp
except ImportError as exc:
    print(f"[ERROR] Cannot import project modules: {exc}")
    print("  Make sure you run this from the project root directory:")
    print("  cd /path/to/HD\\ Dashboard && python scripts/retro_pseudo_prospective_validation.py")
    sys.exit(1)

# ── ANSI colours (degrade gracefully on Windows) ─────────────────────────────
BOLD   = "\033[1m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
RESET  = "\033[0m"

def _c(text, color):
    return f"{color}{text}{RESET}"


# ── Month arithmetic helpers ───────────────────────────────────────────────────

def _month_to_int(m_str: str) -> int:
    """Convert 'YYYY-MM' → integer (months since epoch) for sorting."""
    yr, mo = int(m_str[:4]), int(m_str[5:7])
    return yr * 12 + mo


def _int_to_month(n: int) -> str:
    yr, mo = divmod(n - 1, 12)
    return f"{yr:04d}-{mo+1:02d}"


def _row_to_dict_safe(rec) -> dict:
    """ORM → dict, tolerating both SQLAlchemy rows and plain dicts."""
    if isinstance(rec, dict):
        return rec
    try:
        return _row_to_dict(rec)
    except Exception:
        # Minimal fallback using __dict__
        d = {k: v for k, v in vars(rec).items() if not k.startswith("_")}
        # Normalise common aliases
        if "hb" not in d and hasattr(rec, "hb"):
            d["hb"] = rec.hb
        return d


# ── Core simulation engine ────────────────────────────────────────────────────

def _simulate_one_step(
    patient_id: int,
    history_records: list,           # newest-first, already converted to dicts
    actual_esa_iu_sc: float,         # ESA dose actually administered in month N-1
    patient_weight_kg: float,
) -> dict:
    """
    Given history up to month N-2 and the actual ESA dose used in month N-1,
    predict the Hb at month N using the patient-specific ODE.

    Returns a dict with:
        predicted_hb_ode   — raw ODE single-step forecast
        predicted_hb_hybrid — ODE + residual MLP correction (if available)
        params             — fitted ODE parameters
        confidence         — 'high' | 'moderate' | 'low' | 'population-prior'
    """
    if not history_records:
        return {"error": "No history"}

    # Fit (or load cached) patient-specific ODE parameters from history
    params = fit_patient_ode_params(history_records)

    hb0 = float(history_records[0].get("hb") or float("nan"))
    if math.isnan(hb0):
        return {"error": "No baseline Hb in history"}

    # Build ODE input for ONE future month using the actual ESA dose applied
    epo_norm = (actual_esa_iu_sc / patient_weight_kg) if patient_weight_kg > 0 else 0.0
    latest = history_records[0]
    tsat    = float(latest.get("tsat") or float("nan"))
    ferritin = float(latest.get("serum_ferritin") or float("nan"))

    # Iron availability factor
    if not math.isnan(tsat):
        iron_frac = float(np.clip(tsat / 30.0, 0.0, 1.0))
    elif not math.isnan(ferritin):
        iron_frac = float(np.clip(ferritin / 200.0, 0.0, 1.0))
    else:
        iron_frac = 0.75  # population-median fallback

    crp_val = float(latest.get("crp") or 5.0)
    future_inputs = [{"epo_norm": epo_norm, "iron_frac": iron_frac, "crp": crp_val}]

    ode_trajectory = ode_simulate(
        hb0    = hb0,
        inputs = future_inputs,
        params = (params["k_epo"], params["k_prod"], params["k_loss"]),
    )
    predicted_ode = float(ode_trajectory[0])

    # Residual MLP correction (population-level)
    correction = 0.0
    mlp_applied = False
    try:
        if _load_residual_mlp():
            feats = _extract_acm_features(history_records)
            if feats is not None:
                correction = residual_correction(feats)
                mlp_applied = True
    except Exception:
        pass

    predicted_hybrid = float(np.clip(predicted_ode + correction, 6.0, 18.0))

    confidence = params.get("param_confidence", "moderate") if params["calibrated"] else "population-prior"

    return {
        "predicted_hb_ode":    round(predicted_ode, 2),
        "predicted_hb_hybrid": round(predicted_hybrid, 2),
        "hb0":                 round(hb0, 2),
        "params":              params,
        "confidence":          confidence,
        "mlp_applied":         mlp_applied,
        "residual_correction": round(correction, 3),
        "epo_norm_used":       round(epo_norm, 4),
        "iron_frac_used":      round(iron_frac, 3),
    }


# ── Patient-level validation loop ─────────────────────────────────────────────

def validate_patient(patient, records_orm: list, verbose: bool = False) -> list:
    """
    Run pseudo-prospective validation for a single patient.
    Returns a list of dicts — one per validation step (month triplet N-2, N-1, N).
    """
    # Sort records oldest → newest
    records_sorted = sorted(records_orm, key=lambda r: r.record_month)
    n = len(records_sorted)
    results = []

    # We need at minimum 3 consecutive records: history(≥1), dose-month, outcome-month
    if n < 3:
        return []

    for i in range(2, n):
        # month_N     = records_sorted[i]     (target — actual Hb we verify against)
        # month_N_minus1 = records_sorted[i-1] (ESA dose we feed the simulation)
        # history       = records_sorted[:i-1] (everything before, newest-first for ODE)

        month_n_rec = records_sorted[i]
        month_nm1_rec = records_sorted[i - 1]

        actual_hb_n = month_n_rec.hb
        if actual_hb_n is None:
            continue  # Nothing to validate against

        # Extract the ESA dose that was actually administered in month N-1
        nm1_dict = _row_to_dict_safe(month_nm1_rec)
        actual_esa = _resolve_weekly_iu_sc(nm1_dict)
        if actual_esa is None:
            # No ESA recorded — use 0 (patient off ESA) and still evaluate
            actual_esa = 0.0

        # History: everything BEFORE month N-1 (i.e., up to month N-2), newest-first
        history_orm = list(reversed(records_sorted[:i - 1]))
        history_dicts = [_row_to_dict_safe(r) for r in history_orm]

        # Need at least 1 history point with Hb
        if not any(d.get("hb") is not None for d in history_dicts):
            continue

        # Weight: use N-1 record if available, fallback to patient dry weight
        weight = (
            nm1_dict.get("last_prehd_weight")
            or nm1_dict.get("target_dry_weight")
            or getattr(patient, "dry_weight", None)
            or 60.0
        )
        try:
            weight = float(weight)
        except (TypeError, ValueError):
            weight = 60.0

        sim = _simulate_one_step(
            patient_id=patient.id,
            history_records=history_dicts,
            actual_esa_iu_sc=actual_esa,
            patient_weight_kg=weight,
        )

        if "error" in sim:
            continue

        ape_ode    = abs(sim["predicted_hb_ode"]    - actual_hb_n)
        ape_hybrid = abs(sim["predicted_hb_hybrid"] - actual_hb_n)
        bias_ode   = sim["predicted_hb_ode"]    - actual_hb_n
        bias_hybrid = sim["predicted_hb_hybrid"] - actual_hb_n

        row = {
            "patient_id":          patient.id,
            "patient_name":        patient.name,
            "month_history_end":   month_nm1_rec.record_month,  # month N-1
            "month_target":        month_n_rec.record_month,    # month N
            "actual_hb":           round(float(actual_hb_n), 2),
            "actual_esa_iu_wk":    round(actual_esa, 0),
            "predicted_hb_ode":    sim["predicted_hb_ode"],
            "predicted_hb_hybrid": sim["predicted_hb_hybrid"],
            "ape_ode":             round(ape_ode, 3),
            "ape_hybrid":          round(ape_hybrid, 3),
            "bias_ode":            round(bias_ode, 3),
            "bias_hybrid":         round(bias_hybrid, 3),
            "confidence":          sim["confidence"],
            "n_history_months":    len(history_dicts),
            "k_epo":               round(sim["params"].get("k_epo", 0), 6),
            "k_prod":              round(sim["params"].get("k_prod", 0), 4),
            "k_loss":              round(sim["params"].get("k_loss", 0), 4),
            "mlp_applied":         sim["mlp_applied"],
            "residual_correction": sim["residual_correction"],
            "calibrated":          sim["params"].get("calibrated", False),
        }
        results.append(row)

        if verbose:
            flag = ""
            if ape_hybrid < 0.5:
                flag = _c("✓ GOOD", GREEN)
            elif ape_hybrid < 1.0:
                flag = _c("~ OK", YELLOW)
            else:
                flag = _c("✗ MISS", RED)

            print(
                f"  {patient.name[:18]:<20} "
                f"[{row['month_history_end']} → {row['month_target']}]  "
                f"Actual={row['actual_hb']}  "
                f"ODE={row['predicted_hb_ode']}  "
                f"Hybrid={row['predicted_hb_hybrid']}  "
                f"APE_hybrid={row['ape_hybrid']:.3f}  "
                f"conf={row['confidence']:<17} "
                f"{flag}"
            )

    return results


# ── Fleet-level metrics ───────────────────────────────────────────────────────

def compute_fleet_metrics(all_rows: list) -> dict:
    """
    Compute aggregate statistics across all validation triplets.
    Returns a dict with MAE, RMSE, R², calibration slope (ODE and hybrid).
    """
    if not all_rows:
        return {}

    actual  = np.array([r["actual_hb"]           for r in all_rows])
    pred_o  = np.array([r["predicted_hb_ode"]     for r in all_rows])
    pred_h  = np.array([r["predicted_hb_hybrid"]  for r in all_rows])

    def _metrics(pred, label):
        mae  = float(np.mean(np.abs(pred - actual)))
        rmse = float(np.sqrt(np.mean((pred - actual) ** 2)))
        ss_res = np.sum((actual - pred) ** 2)
        ss_tot = max(np.sum((actual - actual.mean()) ** 2), 1e-9)
        r2   = float(1 - ss_res / ss_tot)
        bias = float(np.mean(pred - actual))

        # Calibration slope via OLS: observed ~ α + β·predicted
        try:
            coeffs = np.polyfit(pred, actual, 1)
            slope, intercept = float(coeffs[0]), float(coeffs[1])
        except Exception:
            slope, intercept = float("nan"), float("nan")

        # % within ±0.5, ±1.0 g/dL tolerance windows
        within_05 = float(np.mean(np.abs(pred - actual) < 0.5) * 100)
        within_10 = float(np.mean(np.abs(pred - actual) < 1.0) * 100)

        return {
            "label":     label,
            "n":         len(actual),
            "mae":       round(mae, 3),
            "rmse":      round(rmse, 3),
            "r2":        round(r2, 4),
            "bias":      round(bias, 3),
            "slope":     round(slope, 4),
            "intercept": round(intercept, 4),
            "within_05_pct": round(within_05, 1),
            "within_10_pct": round(within_10, 1),
        }

    # Confidence breakdown
    conf_counts = defaultdict(int)
    for r in all_rows:
        conf_counts[r["confidence"]] += 1

    # Patient breakdown
    patient_maes = defaultdict(list)
    for r in all_rows:
        patient_maes[r["patient_name"]].append(r["ape_hybrid"])
    per_patient = {
        name: round(float(np.mean(errs)), 3)
        for name, errs in sorted(patient_maes.items(), key=lambda x: np.mean(x[1]))
    }

    return {
        "ode":    _metrics(pred_o, "ODE (patient-specific)"),
        "hybrid": _metrics(pred_h, "Hybrid ODE + MLP"),
        "confidence_breakdown": dict(conf_counts),
        "per_patient_mae_hybrid": per_patient,
    }


# ── Console report ────────────────────────────────────────────────────────────

def print_report(metrics: dict):
    """Pretty-print the validation summary to the console."""
    print()
    print(_c("=" * 72, BOLD))
    print(_c("  RETROSPECTIVE PSEUDO-PROSPECTIVE VALIDATION REPORT", BOLD))
    print(_c("  HD Dashboard — Anemia Control Model (ACM ODE + Residual MLP)", BOLD))
    print(_c(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", CYAN))
    print(_c("=" * 72, BOLD))

    for key in ("ode", "hybrid"):
        m = metrics.get(key, {})
        if not m:
            continue
        label = _c(f"\n  ► {m['label']}", BOLD)
        print(label)
        print(f"    n (validation triplets) : {m['n']}")
        print(f"    MAE                     : {m['mae']:.3f} g/dL   "
              f"{'✓ BENCHMARK MET (<0.75)' if m['mae'] < 0.75 else '⚠ Above Fresenius benchmark (0.75)' if m['mae'] < 1.0 else '✗ Needs more data'}")
        print(f"    RMSE                    : {m['rmse']:.3f} g/dL")
        print(f"    R² (coefficient of det.): {m['r2']:.4f}   "
              f"{'(good)' if m['r2'] > 0.5 else '(fair)' if m['r2'] > 0.2 else '(low — more data needed)'}")
        print(f"    Mean Bias               : {m['bias']:+.3f} g/dL "
              f"{'(slight over-prediction)' if m['bias'] > 0.1 else '(slight under-prediction)' if m['bias'] < -0.1 else '(no systematic bias)'}")
        print(f"    Calibration slope (β)   : {m['slope']:.4f}  "
              f"{'✓ Ideal (~1.0)' if 0.85 < m['slope'] < 1.15 else '⚠ Slope drift detected'}")
        print(f"    Calibration intercept   : {m['intercept']:.4f}")
        print(f"    Within ±0.5 g/dL        : {m['within_05_pct']:.1f}%")
        print(f"    Within ±1.0 g/dL        : {m['within_10_pct']:.1f}%")

    # Confidence breakdown
    conf = metrics.get("confidence_breakdown", {})
    if conf:
        print(_c("\n  ► Prediction Confidence Distribution", BOLD))
        total = sum(conf.values())
        for lvl, cnt in sorted(conf.items()):
            bar = "█" * int(cnt / total * 30)
            print(f"    {lvl:<20} : {cnt:3d} ({cnt/total*100:5.1f}%)  {bar}")

    # Per-patient MAE
    pp = metrics.get("per_patient_mae_hybrid", {})
    if pp:
        print(_c("\n  ► Per-Patient MAE (Hybrid, sorted best → worst)", BOLD))
        for name, mae_val in pp.items():
            bar_len = min(int(mae_val / 2.0 * 30), 30)
            color = GREEN if mae_val < 0.5 else YELLOW if mae_val < 1.0 else RED
            bar = _c("█" * bar_len, color)
            flag = _c("✓", GREEN) if mae_val < 0.75 else _c("⚠", YELLOW)
            print(f"    {name[:22]:<24} {mae_val:.3f} g/dL  {bar}  {flag}")

    # Clinical interpretation
    h = metrics.get("hybrid", {})
    print(_c("\n  ► Clinical Interpretation", BOLD))
    mae_val = h.get("mae", float("inf"))
    slope_val = h.get("slope", 1.0)
    if mae_val < 0.5:
        print(_c("    EXCELLENT: MAE < 0.5 g/dL. The model is ready for prospective shadow running.", GREEN))
        print(_c("    Recommend: Begin shadow predictions alongside clinical decisions.", GREEN))
    elif mae_val < 0.75:
        print(_c("    GOOD: MAE < 0.75 g/dL (Fresenius benchmark). Clinically useful.", GREEN))
        print(_c("    Recommend: Present to senior nephrologist with this validation report.", GREEN))
    elif mae_val < 1.0:
        print(_c("    FAIR: MAE < 1.0 g/dL. Adds directional signal but not yet high-precision.", YELLOW))
        print(_c("    Recommend: Collect 3 more months of data per patient before clinical use.", YELLOW))
    else:
        print(_c("    NEEDS DATA: MAE ≥ 1.0 g/dL. Insufficient history for calibration.", RED))
        print(_c("    Recommend: Run retrospectively on ≥3 more months before presenting.", RED))

    if not (0.85 < slope_val < 1.15) and not math.isnan(slope_val):
        print(_c(f"\n    ⚠ CALIBRATION DRIFT: slope={slope_val:.3f} (ideal=1.0).", YELLOW))
        if slope_val > 1.15:
            print(_c("      Model is UNDER-predicting — actual values are consistently higher.", YELLOW))
        else:
            print(_c("      Model is OVER-predicting — actual values are consistently lower.", YELLOW))
        print(_c("      Action: Add more varied ESA dose history to improve k_epo calibration.", YELLOW))

    print()
    print(_c("=" * 72, BOLD))
    print()


# ── Scatter / reliability plots ───────────────────────────────────────────────

def make_plots(all_rows: list, out_dir: str):
    """Generate matplotlib scatter and reliability diagram plots."""
    try:
        import matplotlib
        matplotlib.use("Agg")  # non-interactive backend for server use
        import matplotlib.pyplot as plt
        import matplotlib.lines as mlines
    except ImportError:
        print("[WARN] matplotlib not available — skipping plots. Install with: pip install matplotlib")
        return

    os.makedirs(out_dir, exist_ok=True)

    actual   = [r["actual_hb"]           for r in all_rows]
    pred_ode = [r["predicted_hb_ode"]    for r in all_rows]
    pred_hyb = [r["predicted_hb_hybrid"] for r in all_rows]
    apes     = [r["ape_hybrid"]          for r in all_rows]

    # ── 1. Scatter: actual vs predicted (hybrid) ──────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    for ax, pred, title, color in [
        (axes[0], pred_ode, "ODE Only (Patient-Specific)", "#0284c7"),
        (axes[1], pred_hyb, "Hybrid ODE + Residual MLP",  "#7c3aed"),
    ]:
        scatter = ax.scatter(pred, actual, alpha=0.7, c=apes, cmap="RdYlGn_r",
                             vmin=0, vmax=2.0, edgecolors="grey", linewidths=0.4, s=60)
        plt.colorbar(scatter, ax=ax, label="|Prediction Error| (g/dL)")

        lo = min(min(pred), min(actual)) - 0.5
        hi = max(max(pred), max(actual)) + 0.5
        ax.plot([lo, hi], [lo, hi], "k--", lw=1.5, label="Perfect prediction (y=x)")
        ax.fill_between([lo, hi], [lo - 1, hi - 1], [lo + 1, hi + 1],
                        alpha=0.08, color="green", label="±1.0 g/dL band")
        ax.fill_between([lo, hi], [lo - 0.5, hi - 0.5], [lo + 0.5, hi + 0.5],
                        alpha=0.12, color="blue", label="±0.5 g/dL band")

        mae_val  = float(np.mean(np.abs(np.array(pred) - np.array(actual))))
        r2_val   = float(1 - np.sum((np.array(actual) - np.array(pred))**2) /
                         max(np.sum((np.array(actual) - np.mean(actual))**2), 1e-9))
        ax.set_xlabel("Predicted Hb (g/dL)", fontsize=12)
        ax.set_ylabel("Actual Hb (g/dL)", fontsize=12)
        ax.set_title(f"{title}\nMAE={mae_val:.3f} g/dL  R²={r2_val:.3f}", fontsize=12, fontweight="bold")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(lo, hi)
        ax.set_ylim(lo, hi)
        ax.set_aspect("equal")

    fig.suptitle(
        "Retrospective Pseudo-Prospective Validation\nHD Dashboard — ACM Anemia Prediction",
        fontsize=14, fontweight="bold",
    )
    plt.tight_layout()
    scatter_path = os.path.join(out_dir, "retro_validation_scatter.png")
    plt.savefig(scatter_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  [PLOT] Saved scatter plot → {scatter_path}")

    # ── 2. Error distribution histogram ──────────────────────────────────────
    fig, ax = plt.subplots(figsize=(9, 5))
    biases = [r["bias_hybrid"] for r in all_rows]
    ax.hist(biases, bins=20, color="#7c3aed", alpha=0.7, edgecolor="white", linewidth=0.5)
    ax.axvline(0, color="black", linewidth=1.5, linestyle="--", label="Zero bias (ideal)")
    ax.axvline(np.mean(biases), color="red", linewidth=1.5, linestyle="-",
               label=f"Mean bias = {np.mean(biases):+.3f} g/dL")
    ax.axvspan(-0.5, 0.5, alpha=0.08, color="green", label="±0.5 g/dL range")
    ax.axvspan(-1.0, 1.0, alpha=0.05, color="blue", label="±1.0 g/dL range")
    ax.set_xlabel("Prediction Bias (Predicted − Actual) g/dL", fontsize=12)
    ax.set_ylabel("Count", fontsize=12)
    ax.set_title("Error Distribution — Hybrid ODE + MLP\n(Centred distribution = no systematic bias)",
                 fontsize=12, fontweight="bold")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    hist_path = os.path.join(out_dir, "retro_validation_error_hist.png")
    plt.savefig(hist_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  [PLOT] Saved error histogram → {hist_path}")

    # ── 3. Reliability / calibration diagram (Hb bins) ───────────────────────
    fig, ax = plt.subplots(figsize=(9, 5))
    bins = [7, 8, 9, 10, 11, 12, 13, 14, 15]
    bin_actual_means, bin_pred_means, bin_counts = [], [], []
    for i in range(len(bins) - 1):
        lo_b, hi_b = bins[i], bins[i + 1]
        mask = [lo_b <= r["predicted_hb_hybrid"] < hi_b for r in all_rows]
        if sum(mask) > 0:
            sub_actual = [all_rows[j]["actual_hb"] for j in range(len(all_rows)) if mask[j]]
            sub_pred   = [all_rows[j]["predicted_hb_hybrid"] for j in range(len(all_rows)) if mask[j]]
            bin_actual_means.append(np.mean(sub_actual))
            bin_pred_means.append(np.mean(sub_pred))
            bin_counts.append(sum(mask))

    if bin_actual_means:
        sizes = [max(c * 20, 40) for c in bin_counts]
        ax.scatter(bin_pred_means, bin_actual_means, s=sizes, color="#0284c7",
                   alpha=0.8, edgecolors="navy", zorder=5, label="Calibration bin means")
        for bpm, bam, bc in zip(bin_pred_means, bin_actual_means, bin_counts):
            ax.annotate(f"n={bc}", (bpm, bam), textcoords="offset points",
                        xytext=(6, 4), fontsize=8, color="grey")
        lo_c = min(min(bin_pred_means), min(bin_actual_means)) - 0.5
        hi_c = max(max(bin_pred_means), max(bin_actual_means)) + 0.5
        ax.plot([lo_c, hi_c], [lo_c, hi_c], "k--", label="Perfect calibration (y=x)")
        ax.fill_between([lo_c, hi_c], [lo_c - 0.5, hi_c - 0.5], [lo_c + 0.5, hi_c + 0.5],
                        alpha=0.1, color="green")
        ax.set_xlabel("Mean Predicted Hb per bin (g/dL)", fontsize=12)
        ax.set_ylabel("Mean Actual Hb per bin (g/dL)", fontsize=12)
        ax.set_title("Calibration Diagram — Predicted vs. Actual Hb (1 g/dL bins)\n"
                     "Points on diagonal = perfectly calibrated model", fontsize=11, fontweight="bold")
        ax.legend()
        ax.grid(True, alpha=0.3)
    plt.tight_layout()
    cal_path = os.path.join(out_dir, "retro_validation_calibration.png")
    plt.savefig(cal_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  [PLOT] Saved calibration diagram → {cal_path}")


# ── CSV export ────────────────────────────────────────────────────────────────

def export_csv(all_rows: list, csv_path: str):
    import csv
    fields = [
        "patient_id", "patient_name", "month_history_end", "month_target",
        "actual_hb", "actual_esa_iu_wk", "predicted_hb_ode", "predicted_hb_hybrid",
        "ape_ode", "ape_hybrid", "bias_ode", "bias_hybrid",
        "confidence", "n_history_months", "k_epo", "k_prod", "k_loss",
        "mlp_applied", "residual_correction", "calibrated",
    ]
    os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"  [CSV] Detailed results saved → {csv_path}")


# ── Main entry point ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Retrospective Pseudo-Prospective Validation for the ACM ODE model."
    )
    parser.add_argument("--min-records", type=int, default=4,
                        help="Minimum monthly records to include a patient (default: 4)")
    parser.add_argument("--plot", action="store_true",
                        help="Save matplotlib validation plots to scripts/output/")
    parser.add_argument("--csv", type=str, default=None,
                        help="Path to export per-row CSV results")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print per-step predictions")
    args = parser.parse_args()

    print(_c("\n  HD Dashboard — Retrospective Pseudo-Prospective Validation", BOLD))
    print(_c(f"  Protocol: Calibrate on history → Feed actual ESA → Predict next Hb", CYAN))
    print(_c(f"  min-records={args.min_records}  plot={args.plot}  verbose={args.verbose}\n", CYAN))

    db = SessionLocal()
    all_rows = []
    n_patients_eligible = 0
    n_patients_skipped  = 0

    try:
        patients = db.query(Patient).filter(Patient.is_active == True).all()
        print(f"  Found {len(patients)} active patients in database.\n")

        for patient in patients:
            records = (
                db.query(MonthlyRecord)
                .filter(MonthlyRecord.patient_id == patient.id)
                .order_by(MonthlyRecord.record_month.asc())
                .all()
            )

            if len(records) < args.min_records:
                n_patients_skipped += 1
                continue

            n_patients_eligible += 1

            if args.verbose:
                print(_c(f"\n  ─── {patient.name} (ID={patient.id}, {len(records)} months) ───", CYAN))

            patient_rows = validate_patient(patient, records, verbose=args.verbose)
            all_rows.extend(patient_rows)

        print(f"\n  Eligible patients : {n_patients_eligible}")
        print(f"  Skipped (<{args.min_records} records) : {n_patients_skipped}")
        print(f"  Total validation steps : {len(all_rows)}")

    finally:
        db.close()

    if not all_rows:
        print(_c("\n  [WARN] No validation rows produced. Possible causes:", YELLOW))
        print("    • All patients have fewer than min-records monthly records")
        print("    • None of the records have Hb AND ESA dose recorded together")
        print("    • Database is empty or contains only 1 patient-month")
        print(f"\n  Try: python scripts/retro_pseudo_prospective_validation.py --min-records 3\n")
        return

    # Compute metrics
    metrics = compute_fleet_metrics(all_rows)

    # Print console report
    print_report(metrics)

    # Optional outputs
    if args.plot:
        out_dir = os.path.join(_ROOT, "scripts", "output")
        print("  Generating plots...")
        make_plots(all_rows, out_dir)

    if args.csv:
        export_csv(all_rows, args.csv)
    else:
        # Always auto-save to scripts/output/ for convenience
        default_csv = os.path.join(_ROOT, "scripts", "output", "retro_validation_results.csv")
        export_csv(all_rows, default_csv)

    # Save JSON summary
    out_dir = os.path.join(_ROOT, "scripts", "output")
    os.makedirs(out_dir, exist_ok=True)
    summary_path = os.path.join(out_dir, "retro_validation_summary.json")
    with open(summary_path, "w") as f:
        json.dump(
            {
                "generated_at": datetime.now().isoformat(),
                "n_validation_steps": len(all_rows),
                "n_patients_eligible": n_patients_eligible,
                "metrics": metrics,
            },
            f, indent=2, default=str,
        )
    print(f"  [JSON] Summary saved → {summary_path}")
    print()


if __name__ == "__main__":
    main()
