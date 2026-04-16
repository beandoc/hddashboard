"""
seed_retrospective.py
=====================
Seeds retrospective patient data from a CSV file into the HD Dashboard database.

Usage:
    python seed_retrospective.py --file your_data.csv
    python seed_retrospective.py --file your_data.csv --dry-run
"""
import sys
import os
import argparse
import csv
from datetime import datetime

# Allow running from project root
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
os.chdir(project_root)

from database import SessionLocal, create_tables, Patient, MonthlyRecord


def safe_float(val):
    """Convert string to float, return None for empty/invalid."""
    if val is None or str(val).strip() == "" or str(val).strip() == "-":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def seed_from_csv(filepath: str, dry_run: bool = False):
    create_tables()
    db = SessionLocal()

    print(f"\n{'='*60}")
    print(f"HD Dashboard — Retrospective Data Seeder")
    print(f"File: {filepath}")
    print(f"Mode: {'DRY RUN (no changes saved)' if dry_run else 'LIVE'}")
    print(f"{'='*60}\n")

    inserted = 0
    updated = 0
    skipped = 0
    errors = []

    try:
        with open(filepath, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            for row_num, row in enumerate(reader, start=2):
                hid = row.get("hid_no", "").strip()
                name = row.get("name", "").strip()
                month = row.get("record_month", "").strip()

                if not hid or not month:
                    errors.append(f"Row {row_num}: missing hid_no or record_month")
                    skipped += 1
                    continue

                # Find patient
                patient = db.query(Patient).filter(Patient.hid_no == hid).first()
                if not patient:
                    # Create patient if not exists
                    if not dry_run:
                        patient = Patient(name=name, hid_no=hid, is_active=True)
                        db.add(patient)
                        db.flush()
                        print(f"  [NEW PATIENT] Registered: {name} (HID:{hid})")
                    else:
                        errors.append(f"Row {row_num}: Patient HID '{hid}' not found (would create in live mode)")
                        skipped += 1
                        continue

                # Check for existing record
                existing = db.query(MonthlyRecord).filter(
                    MonthlyRecord.patient_id == patient.id,
                    MonthlyRecord.record_month == month
                ).first()

                # Parse numeric EPO units from dose text
                def parse_epo_units(text):
                    if not text: return 0.0
                    matches = re.findall(r"\d+", str(text))
                    return float(matches[0]) if matches else 0.0

                record_data = {
                    "idwg":              safe_float(row.get("idwg")),
                    "hb":                safe_float(row.get("hb")),
                    "serum_ferritin":    safe_float(row.get("serum_ferritin")),
                    "tsat":              safe_float(row.get("tsat")),
                    "calcium":           safe_float(row.get("calcium")),
                    "phosphorus":        safe_float(row.get("phosphorus")),
                    "albumin":           safe_float(row.get("albumin")),
                    "ipth":              safe_float(row.get("ipth")),
                    "vit_d":             safe_float(row.get("vit_d")),
                    "ast":               safe_float(row.get("ast")),
                    "alt":               safe_float(row.get("alt")),
                    "crp":               safe_float(row.get("crp")),
                    "urr":               safe_float(row.get("urr")),
                    "bp_sys":            safe_float(row.get("bp_sys")),
                    "bp_dia":            safe_float(row.get("bp_dia")),
                    "mcv":               safe_float(row.get("mcv")),
                    "hb_hematocrit":     safe_float(row.get("hb_hematocrit")),
                    "av_daily_calories": safe_float(row.get("av_daily_calories")),
                    "av_daily_protein":  safe_float(row.get("av_daily_protein")),
                    "epo_mircera_dose":  row.get("epo_mircera_dose", "").strip() or None,
                    "epo_weekly_units":  parse_epo_units(row.get("epo_mircera_dose")),
                    "entered_by":        "retrospective_seed",
                }

                if not dry_run:
                    if existing:
                        for k, v in record_data.items():
                            setattr(existing, k, v)
                        updated += 1
                    else:
                        new_rec = MonthlyRecord(patient_id=patient.id, record_month=month, **record_data)
                        db.add(new_rec)
                        inserted += 1
                else:
                    if existing: updated += 1
                    else: inserted += 1

                print(f"  [{'UPDATE' if existing else 'INSERT'}] {patient.name} — {month} | Hb:{record_data['hb']}")

        if not dry_run:
            db.commit()
            print(f"\n✅ Committed to database.")
        else:
            print(f"\n⚠️  Dry run — nothing saved.")

    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
    finally:
        db.close()

    print(f"\nResults: {inserted} inserted, {updated} updated, {skipped} skipped.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    seed_from_csv(args.file, dry_run=args.dry_run)
