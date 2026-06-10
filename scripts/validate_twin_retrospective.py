#!/usr/bin/env python3
"""
scripts/validate_twin_retrospective.py
=======================================
Retrospective validation of the Digital Dialysis Twin against real patient data.

Usage:
    python scripts/validate_twin_retrospective.py
    python scripts/validate_twin_retrospective.py --patients 12 45 78 --cutoff 2026-03-01
    python scripts/validate_twin_retrospective.py --all-patients --cutoff 2026-01-01 --out reports/twin_validation.csv

What it does:
  For each patient, at the cutoff date:
    1. Fetches only records available AT that point (no data leakage)
    2. Runs the twin with an empty scenario (pure baseline)
    3. Fetches the ACTUAL outcomes from the month AFTER the cutoff
    4. Compares predicted vs actual across all 4 domains
    5. Prints a per-patient table and overall accuracy summary
    6. Optionally writes a CSV for further analysis

Accuracy targets (published DDT literature):
    Hb:         ±1.0 g/dL at 3 months    (≥70% of patients)
    Kt/V:       ±0.15                     (≥80% of patients)
    IDH risk:   correct high/low direction (≥70% of sessions)
    Phosphorus: ±0.8 mg/dL               (≥70% of patients)
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import os
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

# ── Project root on sys.path ──────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("twin_validate")

# ── Imports after path fix ────────────────────────────────────────────────────
from database import SessionLocal, Patient, MonthlyRecord, SessionRecord  # noqa: E402
from ml_twin import run_scenario                                            # noqa: E402
from routers.twin import (                                                  # noqa: E402
    _monthly_records_dicts,
    _past_sessions_dicts,
    _build_patient_info,
    _build_baseline_session,
)


# ─────────────────────────────────────────────────────────────────────────────
# Accuracy thresholds
# ─────────────────────────────────────────────────────────────────────────────

THRESHOLDS = {
    "hb":       1.0,    # g/dL
    "sp_ktv":   0.15,   # Kt/V units
    "phosphorus": 0.8,  # mg/dL
}

IDH_HIGH_THRESHOLD = 40.0   # % — above this = "high risk"


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers (time-sliced, no leakage)
# ─────────────────────────────────────────────────────────────────────────────

def _cutoff_ym(cutoff: date) -> str:
    """Return YYYY-MM string for the cutoff month."""
    return cutoff.strftime("%Y-%m")


def _next_ym(cutoff: date) -> str:
    """Return YYYY-MM of the month immediately after cutoff."""
    if cutoff.month == 12:
        return f"{cutoff.year + 1}-01"
    return f"{cutoff.year}-{cutoff.month + 1:02d}"


def _plus3_ym(cutoff: date) -> str:
    """Return YYYY-MM of the month 3 months after cutoff."""
    m = cutoff.month + 3
    y = cutoff.year + (m - 1) // 12
    m = ((m - 1) % 12) + 1
    return f"{y}-{m:02d}"


def _monthly_records_at_cutoff(db, patient_id: int, cutoff: date) -> list:
    """Monthly records available AT the cutoff (≤ cutoff month), newest first."""
    cutoff_str = _cutoff_ym(cutoff)
    recs = (
        db.query(MonthlyRecord)
        .filter(
            MonthlyRecord.patient_id == patient_id,
            MonthlyRecord.record_month <= cutoff_str,
        )
        .order_by(MonthlyRecord.record_month.desc())
        .limit(12)
        .all()
    )
    return [
        {
            "hb":                  rec.hb,
            "serum_ferritin":      rec.serum_ferritin,
            "tsat":                rec.tsat,
            "albumin":             getattr(rec, "albumin", None),
            "single_pool_ktv":     rec.single_pool_ktv,
            "crp":                 getattr(rec, "crp", None),
            "last_prehd_weight":   rec.last_prehd_weight,
            "weight":              rec.last_prehd_weight,
            "epo_mircera_dose":    rec.epo_mircera_dose,
            "epo_weekly_units":    rec.epo_weekly_units,
            "iv_iron_dose":        rec.iv_iron_dose,
            "pre_dialysis_urea":   rec.pre_dialysis_urea,
            "post_dialysis_urea":  rec.post_dialysis_urea,
            "phosphorus":          rec.phosphorus,
            "ufr":                 rec.ufr,
            "record_month":        rec.record_month,
            "phosphate_binder_type":    rec.phosphate_binder_type,
            "phosphate_binder_dose_mg": rec.phosphate_binder_dose_mg,
            "phosphate_binder_details": getattr(rec, "phosphate_binder_details", None),
            "antihypertensive_count":   getattr(rec, "antihypertensive_count", None),
        }
        for rec in recs
    ]


def _past_sessions_at_cutoff(db, patient_id: int, cutoff: date) -> list:
    """Sessions recorded AT or BEFORE the cutoff date, newest first."""
    sessions = (
        db.query(SessionRecord)
        .filter(
            SessionRecord.patient_id == patient_id,
            SessionRecord.session_date <= cutoff,
        )
        .order_by(SessionRecord.session_date.desc())
        .limit(10)
        .all()
    )
    return [
        {
            "session_date":           str(s.session_date) if s.session_date else None,
            "pre_hd_sbp":             getattr(s, "bp_pre_sys", None),
            "pre_hd_dbp":             getattr(s, "bp_pre_dia", None),
            "bp_nadir_sys":           getattr(s, "bp_nadir_sys", None),
            "idh_episode":            getattr(s, "idh_episode", None),
            "uf_volume":              getattr(s, "uf_volume", None),
            "actual_session_time":    (getattr(s, "duration_hours", None) or 0) * 60
                                      + (getattr(s, "duration_minutes", None) or 0)
                                      or None,
            "idwg_kg":                getattr(s, "idwg_kg", None),
            "weight_pre":             getattr(s, "weight_pre", None),
            "weight_post":            getattr(s, "weight_post", None),
            "dialysate_temp":         getattr(s, "dialysate_temp", None),
            "dialysate_sodium":       getattr(s, "dialysate_sodium", None),
            "antihypertensive_prehd": getattr(s, "antihypertensive_prehd", None),
            "intradialytic_meals":    getattr(s, "intradialytic_meals", None),
            "blood_flow_rate":        getattr(s, "blood_flow_rate", None),
            "dialysate_flow":         getattr(s, "dialysate_flow", None),
            "arterial_line_pressure": getattr(s, "arterial_line_pressure", None),
            "venous_line_pressure":   getattr(s, "venous_line_pressure", None),
        }
        for s in sessions
    ]


def _actual_record(db, patient_id: int, cutoff: date, months_ahead: int = 1):
    """Fetch the MonthlyRecord `months_ahead` months after the cutoff."""
    target_date = cutoff
    for _ in range(months_ahead):
        if target_date.month == 12:
            target_date = date(target_date.year + 1, 1, 1)
        else:
            target_date = date(target_date.year, target_date.month + 1, 1)
    target_str = target_date.strftime("%Y-%m")
    return (
        db.query(MonthlyRecord)
        .filter(
            MonthlyRecord.patient_id == patient_id,
            MonthlyRecord.record_month.like(f"{target_str}%"),
        )
        .order_by(MonthlyRecord.record_month.desc())
        .first()
    )


def _idh_sessions_after_cutoff(db, patient_id: int, cutoff: date, window_days: int = 90) -> Tuple[int, int]:
    """Return (n_idh_episodes, n_sessions) in the window after cutoff."""
    end_date = cutoff + timedelta(days=window_days)
    sessions = (
        db.query(SessionRecord)
        .filter(
            SessionRecord.patient_id == patient_id,
            SessionRecord.session_date > cutoff,
            SessionRecord.session_date <= end_date,
        )
        .all()
    )
    n_idh = sum(1 for s in sessions if getattr(s, "idh_episode", False))
    return n_idh, len(sessions)


# ─────────────────────────────────────────────────────────────────────────────
# Validation runner for one patient
# ─────────────────────────────────────────────────────────────────────────────

def validate_patient(db, patient: Patient, cutoff: date) -> Optional[Dict]:
    pid = patient.id
    pname = getattr(patient, "name", f"Patient {pid}")

    records_at_cutoff = _monthly_records_at_cutoff(db, pid, cutoff)
    if len(records_at_cutoff) < 2:
        logger.warning("  %s — skipped: fewer than 2 monthly records at cutoff", pname)
        return None

    sessions_at_cutoff = _past_sessions_at_cutoff(db, pid, cutoff)
    if not sessions_at_cutoff:
        logger.warning("  %s — skipped: no session records at cutoff", pname)
        return None

    actual_1mo  = _actual_record(db, pid, cutoff, months_ahead=1)
    actual_3mo  = _actual_record(db, pid, cutoff, months_ahead=3)

    if actual_1mo is None and actual_3mo is None:
        logger.warning("  %s — skipped: no actual records after cutoff", pname)
        return None

    # Build patient_info exactly as the router does, then run the twin
    patient_info  = _build_patient_info(patient, records_at_cutoff, db)
    baseline      = _build_baseline_session(sessions_at_cutoff)

    try:
        result = run_scenario(
            patient_id          = pid,
            records             = records_at_cutoff,
            patient_info        = patient_info,
            baseline_session    = baseline,
            past_sessions       = sessions_at_cutoff,
            monthly_data        = records_at_cutoff[0],
            monthly_records_3mo = records_at_cutoff[:3],
            scenario            = {},           # baseline — no changes
            db                  = db,
        )
    except Exception as exc:
        logger.error("  %s — twin run failed: %s", pname, exc)
        return None

    # ── Extract predictions ───────────────────────────────────────────────────
    hb_traj = (result.get("hb_sim") or {}).get("hb_simulated") or []
    pred_hb_1mo = hb_traj[0] if len(hb_traj) >= 1 else None
    pred_hb_3mo = hb_traj[2] if len(hb_traj) >= 3 else None

    ktv_ext    = result.get("ktv_extended") or {}
    pred_ktv   = (ktv_ext.get("scenario") or {}).get("sp_ktv")

    idh_sim    = result.get("idh_sim") or {}
    pred_idh   = idh_sim.get("baseline_risk_pct")  # baseline (no change) risk

    phos       = result.get("phosphate") or {}
    pred_phos  = phos.get("baseline_p")  # baseline phosphorus

    # ── Extract actuals ───────────────────────────────────────────────────────
    act_hb_1mo   = getattr(actual_1mo,  "hb",             None) if actual_1mo  else None
    act_hb_3mo   = getattr(actual_3mo,  "hb",             None) if actual_3mo  else None
    act_ktv_1mo  = getattr(actual_1mo,  "single_pool_ktv",None) if actual_1mo  else None
    act_phos_1mo = getattr(actual_1mo,  "phosphorus",     None) if actual_1mo  else None

    n_idh, n_sess = _idh_sessions_after_cutoff(db, pid, cutoff, window_days=90)
    actual_idh_pct = (n_idh / n_sess * 100) if n_sess > 0 else None

    # ── Compute errors ────────────────────────────────────────────────────────
    def _err(pred, actual):
        if pred is None or actual is None:
            return None
        return abs(float(pred) - float(actual))

    err_hb_1mo  = _err(pred_hb_1mo, act_hb_1mo)
    err_hb_3mo  = _err(pred_hb_3mo, act_hb_3mo)
    err_ktv     = _err(pred_ktv, act_ktv_1mo)
    err_phos    = _err(pred_phos, act_phos_1mo)

    # IDH direction: were both above/below the high-risk threshold?
    idh_direction_correct = None
    if pred_idh is not None and actual_idh_pct is not None:
        pred_high   = pred_idh  >= IDH_HIGH_THRESHOLD
        actual_high = actual_idh_pct >= IDH_HIGH_THRESHOLD
        idh_direction_correct = pred_high == actual_high

    return {
        "patient_id":           pid,
        "patient_name":         pname,
        "cutoff_month":         _cutoff_ym(cutoff),
        # Predictions
        "pred_hb_1mo":          pred_hb_1mo,
        "pred_hb_3mo":          pred_hb_3mo,
        "pred_sp_ktv":          pred_ktv,
        "pred_idh_pct":         pred_idh,
        "pred_phosphorus":      pred_phos,
        # Actuals
        "act_hb_1mo":           act_hb_1mo,
        "act_hb_3mo":           act_hb_3mo,
        "act_sp_ktv":           act_ktv_1mo,
        "act_idh_pct":          actual_idh_pct,
        "act_phosphorus":       act_phos_1mo,
        "idh_n_sessions":       n_sess,
        "idh_n_episodes":       n_idh,
        # Absolute errors
        "err_hb_1mo":           err_hb_1mo,
        "err_hb_3mo":           err_hb_3mo,
        "err_sp_ktv":           err_ktv,
        "err_phosphorus":       err_phos,
        # Pass/fail
        "hb_1mo_pass":          (err_hb_1mo  is not None and err_hb_1mo  <= THRESHOLDS["hb"]),
        "hb_3mo_pass":          (err_hb_3mo  is not None and err_hb_3mo  <= THRESHOLDS["hb"]),
        "ktv_pass":             (err_ktv     is not None and err_ktv     <= THRESHOLDS["sp_ktv"]),
        "phos_pass":            (err_phos    is not None and err_phos    <= THRESHOLDS["phosphorus"]),
        "idh_direction_correct": idh_direction_correct,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────────

_FMT = lambda v, dp=2: f"{float(v):.{dp}f}" if v is not None else "—"
_PASS = lambda v: "✓" if v else ("✗" if v is False else "—")


def _print_row(r: Dict) -> None:
    print(
        f"  {r['patient_name']:<25}"
        f"  Hb1m {_FMT(r['pred_hb_1mo'])}→{_FMT(r['act_hb_1mo'])} err={_FMT(r['err_hb_1mo'])} {_PASS(r['hb_1mo_pass'])}"
        f"  Hb3m err={_FMT(r['err_hb_3mo'])} {_PASS(r['hb_3mo_pass'])}"
        f"  Kt/V {_FMT(r['pred_sp_ktv'],3)}→{_FMT(r['act_sp_ktv'],3)} err={_FMT(r['err_sp_ktv'],3)} {_PASS(r['ktv_pass'])}"
        f"  Phos {_FMT(r['pred_phosphorus'])}→{_FMT(r['act_phosphorus'])} err={_FMT(r['err_phosphorus'])} {_PASS(r['phos_pass'])}"
        f"  IDH dir={_PASS(r['idh_direction_correct'])}"
    )


def _summary(results: List[Dict]) -> None:
    def _pct(key, total):
        n = sum(1 for r in results if r.get(key) is True)
        avail = sum(1 for r in results if r.get(key) is not None)
        if avail == 0:
            return "—"
        return f"{n}/{avail} ({100*n/avail:.0f}%)"

    def _mae(key):
        vals = [r[key] for r in results if r.get(key) is not None]
        if not vals:
            return "—"
        return f"{sum(vals)/len(vals):.3f}"

    n = len(results)
    print()
    print("═" * 72)
    print(f"  SUMMARY  ({n} patient{'s' if n != 1 else ''} evaluated)")
    print("═" * 72)
    print(f"  Hb accuracy (1-month):   {_pct('hb_1mo_pass', n)}  MAE={_mae('err_hb_1mo')} g/dL   (target ≥70%)")
    print(f"  Hb accuracy (3-month):   {_pct('hb_3mo_pass', n)}  MAE={_mae('err_hb_3mo')} g/dL   (target ≥70%)")
    print(f"  Kt/V accuracy:           {_pct('ktv_pass', n)}  MAE={_mae('err_sp_ktv')}        (target ≥80%)")
    print(f"  Phosphorus accuracy:     {_pct('phos_pass', n)}  MAE={_mae('err_phosphorus')} mg/dL (target ≥70%)")
    print(f"  IDH direction correct:   {_pct('idh_direction_correct', n)}                          (target ≥70%)")
    print()

    # Systematic bias check
    ktv_errors = [r["err_sp_ktv"] for r in results if r.get("err_sp_ktv") is not None]
    if ktv_errors:
        avg_ktv_err = sum(ktv_errors) / len(ktv_errors)
        if avg_ktv_err > 0.2:
            print(
                f"  ⚠  Kt/V MAE {avg_ktv_err:.3f} > 0.20 threshold.\n"
                "     Possible causes: missing Qb or session duration in session records.\n"
                "     Run: SELECT patient_id, COUNT(*) n, AVG(blood_flow_rate) avg_qb,\n"
                "                AVG(duration_hours) avg_h\n"
                "          FROM session_records GROUP BY patient_id;"
            )

    hb_1_errors = [r["err_hb_1mo"] for r in results if r.get("err_hb_1mo") is not None]
    if hb_1_errors:
        avg_hb_err = sum(hb_1_errors) / len(hb_1_errors)
        if avg_hb_err > 1.5:
            print(
                f"  ⚠  Hb MAE {avg_hb_err:.2f} > 1.5 g/dL.\n"
                "     Check ESA dose units (epo_weekly_units should be IU/week SC).\n"
                "     Also verify TSAT and ferritin entries are current."
            )


def _write_csv(results: List[Dict], path: str) -> None:
    if not results:
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        for r in results:
            writer.writerow({
                k: (f"{v:.4f}" if isinstance(v, float) else v)
                for k, v in r.items()
            })
    print(f"  CSV written → {path}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retrospective Digital Twin validation against real patient data"
    )
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--patients",     nargs="+", type=int, metavar="ID",
                   help="Patient IDs to validate (e.g. --patients 12 45 78)")
    g.add_argument("--all-patients", action="store_true",
                   help="Run on all patients with ≥3 monthly records")
    parser.add_argument("--cutoff", default=None,
                        help="Cutoff date YYYY-MM-DD (default: 3 months ago)")
    parser.add_argument("--out", default=None,
                        help="Path for CSV output (optional)")
    parser.add_argument("--verbose", action="store_true",
                        help="Print per-patient prediction details")
    args = parser.parse_args()

    # Determine cutoff date
    if args.cutoff:
        cutoff = datetime.strptime(args.cutoff, "%Y-%m-%d").date()
    else:
        today = date.today()
        # 3 months back
        m = today.month - 3
        y = today.year
        if m <= 0:
            m += 12; y -= 1
        cutoff = date(y, m, 1)

    logger.info("Cutoff date: %s  (predicting from records ≤ this date)", cutoff)
    logger.info("Looking for actual outcomes in months: +1 (%s) and +3 (%s)",
                _next_ym(cutoff), _plus3_ym(cutoff))

    db = SessionLocal()
    try:
        # Resolve patient list
        if args.all_patients:
            from sqlalchemy import func
            subq = (
                db.query(MonthlyRecord.patient_id)
                .filter(MonthlyRecord.record_month <= _cutoff_ym(cutoff))
                .group_by(MonthlyRecord.patient_id)
                .having(func.count(MonthlyRecord.id) >= 3)
                .subquery()
            )
            patients = (
                db.query(Patient)
                .filter(Patient.id.in_(subq))
                .order_by(Patient.id)
                .all()
            )
        else:
            patients = (
                db.query(Patient)
                .filter(Patient.id.in_(args.patients))
                .order_by(Patient.id)
                .all()
            )

        if not patients:
            print("No matching patients found. Check patient IDs or --cutoff date.")
            return

        logger.info("Evaluating %d patient(s)…", len(patients))
        print()
        print("═" * 72)
        print(f"  Digital Twin Retrospective Validation  |  cutoff: {cutoff}")
        print("═" * 72)
        print(f"  {'Patient':<25}  {'Hb 1m pred→act (err)':22}  Hb3m  Kt/V pred→act (err)  Phos  IDH")
        print("─" * 72)

        results = []
        for patient in patients:
            logger.debug("  Processing patient %s (%s)…", patient.id, getattr(patient, "name", ""))
            r = validate_patient(db, patient, cutoff)
            if r is None:
                continue
            results.append(r)
            _print_row(r)
            if args.verbose:
                print(f"    IDH: predicted {_FMT(r['pred_idh_pct'])}%  "
                      f"actual {r['idh_n_episodes']}/{r['idh_n_sessions']} sessions "
                      f"({_FMT(r['act_idh_pct'])}%)")

        if not results:
            print("  No patients had sufficient data for validation.")
            return

        _summary(results)

        if args.out:
            _write_csv(results, args.out)

    finally:
        db.close()


if __name__ == "__main__":
    main()
