#!/usr/bin/env python3
"""
scan_missing_values.py
======================
CLI front-end for the patient data-completeness scanner. All field definitions
and scanning logic live in ``services/data_completeness.py`` (the single source
of truth shared with the /admin/missing-data page); this script just renders
that output to the terminal / JSON.

It targets whatever DATABASE_URL the app is configured with (falls back to the
local sqlite file). Read-only — it never writes to the database.

Usage:
    python scripts/scan_missing_values.py                 # console report
    python scripts/scan_missing_values.py --json out.json # also dump JSON
    python scripts/scan_missing_values.py --patient 12    # single patient
    python scripts/scan_missing_values.py --required-only # hide recommended
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime

# Ensure the project root is importable when run as `python scripts/scan_missing_values.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal, Patient  # noqa: E402
from services.data_completeness import (  # noqa: E402
    scan_cohort, scan_patient, REQUIRED,
)

RED = "\033[91m"; YEL = "\033[93m"; GRN = "\033[92m"
DIM = "\033[2m"; BOLD = "\033[1m"; RST = "\033[0m"


def _sev_color(sev):
    return RED if sev == REQUIRED else YEL


def render_patient_detail(e, required_only):
    if e["req_missing"] == 0 and (required_only or e["rec_missing"] == 0):
        print(f"  {GRN}✓{RST} #{e['id']:<4} {e['name'][:28]:<28} {DIM}complete{RST}")
        return
    flag = f"{RED}{e['req_missing']} req{RST}" if e["req_missing"] else ""
    rflag = f"{YEL}{e['rec_missing']} rec{RST}" if (e["rec_missing"] and not required_only) else ""
    dot = RED if e["req_missing"] else YEL
    print(f"  {dot}●{RST} #{e['id']:<4} {e['name'][:28]:<28} {flag} {rflag}")
    for label, sec in e["sections"].items():
        if sec.get("row_present") is False:
            sev = sec.get("row_severity")
            if required_only and sev != REQUIRED:
                continue
            print(f"       {_sev_color(sev)}✗ {label}: WHOLE SECTION MISSING ({sev}){RST}")
        miss = [m for m in sec.get("missing", [])
                if not (required_only and m["severity"] != REQUIRED)]
        if miss:
            fields = ", ".join(f"{_sev_color(m['severity'])}{m['label']}{RST}" for m in miss)
            extra = f" {DIM}[{sec['latest_month']}]{RST}" if sec.get("latest_month") else ""
            print(f"       {label}{extra}: {fields}")


def render_console(ov, required_only=False):
    total = ov["total"]
    print(f"\n{BOLD}{'='*72}{RST}")
    print(f"{BOLD} HD DASHBOARD — PATIENT DATA COMPLETENESS SCAN{RST}")
    print(f"{BOLD}{'='*72}{RST}")
    print(f" Active patients scanned : {total}")
    print(f" Fully complete          : {ov['fully_complete']}")
    print(f" With missing REQUIRED    : {ov['with_required']}")
    print(f" With missing recommended : {ov['with_recommended']}")
    print(f" Latest month scanned     : {ov['latest_month'] or '—'}")

    print(f"\n{BOLD}── Per-patient gaps (someone forgot to fill these in) ─────────{RST}")
    shown = [h for h in ov["hotspots"] if not (required_only and h["severity"] != REQUIRED)]
    if not shown:
        print(f"  {DIM}none{RST}")
    for h in shown:
        bar = "█" * min(h["n"], 40)
        c = _sev_color(h["severity"])
        print(f"  {c}{h['n']:3d}{RST}/{total}  {c}{bar}{RST} {h['label']} ({h['severity']})")

    if ov["systemic"] and not required_only:
        print(f"\n{BOLD}── Systemic gaps (missing for ALL {total} — field not captured?) ──{RST}")
        for s in ov["systemic"]:
            print(f"  {DIM}all {total} · {s['label']}{RST}")

    print(f"\n{BOLD}── Per-patient detail ────────────────────────────────────────{RST}")
    for e in ov["patients"]:
        render_patient_detail(e, required_only)
    print(f"{BOLD}{'='*72}{RST}\n")


def main():
    ap = argparse.ArgumentParser(description="Scan patients for missing/nil clinical values.")
    ap.add_argument("--json", metavar="PATH", help="write full report as JSON to PATH")
    ap.add_argument("--patient", type=int, help="scan a single patient id")
    ap.add_argument("--required-only", action="store_true", help="only show required-field gaps")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        if args.patient is not None:
            p = db.query(Patient).filter(Patient.id == args.patient).first()
            if not p:
                print(f"Patient id {args.patient} not found.")
                return
            entry = scan_patient(db, p)
            ov = {"total": 1, "fully_complete": 0 if (entry["req_missing"] or entry["rec_missing"]) else 1,
                  "with_required": 1 if entry["req_missing"] else 0,
                  "with_recommended": 1 if entry["rec_missing"] else 0,
                  "latest_month": entry["sections"].get("Monthly Labs", {}).get("latest_month"),
                  "patients": [entry], "hotspots": [], "systemic": []}
        else:
            ov = scan_cohort(db)
    finally:
        db.close()

    render_console(ov, required_only=args.required_only)

    if args.json:
        def _default(o):
            if isinstance(o, (date, datetime)):
                return o.isoformat()
            return str(o)
        with open(args.json, "w") as f:
            json.dump(ov, f, indent=2, default=_default)
        print(f"JSON report written to {args.json}")


if __name__ == "__main__":
    main()
