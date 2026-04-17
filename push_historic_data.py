"""
push_historic_data.py
=====================
Syncs all retrospective monthly records from local export into
the production PostgreSQL database on Render.

Run this once via: python push_historic_data.py
It is SAFE to re-run — it skips records that already exist (upsert by patient + month).
"""
import json
import logging
import os
from database import SessionLocal, Patient, MonthlyRecord

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EXPORT_FILE = "export_monthly_records.json"

def run():
    if not os.path.exists(EXPORT_FILE):
        logger.error(f"Export file not found: {EXPORT_FILE}")
        return

    with open(EXPORT_FILE, "r") as f:
        records = json.load(f)

    db = SessionLocal()

    # Build HID → DB patient_id map from production DB
    patients = db.query(Patient).filter(Patient.is_active == True).all()
    hid_to_id = {p.hid_no.strip(): p.id for p in patients}

    # Also load the patient ID map from local export to cross-reference
    patient_export_file = "export_patients.json"
    local_id_to_hid = {}
    if os.path.exists(patient_export_file):
        with open(patient_export_file, "r") as f:
            local_patients = json.load(f)
        local_id_to_hid = {p["id"]: p["hid_no"].strip() for p in local_patients}

    inserted = 0
    skipped = 0
    unmatched = 0

    for r in records:
        # Resolve the production patient_id via HID
        local_pid = r.get("patient_id")
        hid = local_id_to_hid.get(local_pid)

        if not hid or hid not in hid_to_id:
            logger.warning(f"No match for local patient_id={local_pid} (HID={hid})")
            unmatched += 1
            continue

        prod_patient_id = hid_to_id[hid]
        month = r.get("record_month")

        # Check if record already exists (upsert protection)
        existing = db.query(MonthlyRecord).filter(
            MonthlyRecord.patient_id == prod_patient_id,
            MonthlyRecord.record_month == month
        ).first()

        if existing:
            skipped += 1
            continue

        # Create the record in production
        new_record = MonthlyRecord(
            patient_id         = prod_patient_id,
            record_month       = month,
            entered_by         = r.get("entered_by"),
            idwg               = r.get("idwg"),
            hb                 = r.get("hb"),
            serum_ferritin     = r.get("serum_ferritin"),
            tsat               = r.get("tsat"),
            serum_iron         = r.get("serum_iron"),
            epo_mircera_dose   = r.get("epo_mircera_dose"),
            epo_weekly_units   = r.get("epo_weekly_units"),
            calcium            = r.get("calcium"),
            alkaline_phosphate = r.get("alkaline_phosphate"),
            phosphorus         = r.get("phosphorus"),
            vit_d              = r.get("vit_d") or r.get("vitamin_d"),
            ipth               = r.get("ipth"),
            albumin            = r.get("albumin"),
            av_daily_calories  = r.get("av_daily_calories"),
            av_daily_protein   = r.get("av_daily_protein") or r.get("protein_intake"),
            ast                = r.get("ast"),
            alt                = r.get("alt"),
            urr                = r.get("urr"),
            target_dry_weight  = r.get("target_dry_weight"),
            bp_sys             = r.get("bp_sys"),
            crp                = r.get("crp"),
            access_type        = r.get("access_type"),
            issues             = r.get("issues") or r.get("notes"),
        )
        db.add(new_record)
        inserted += 1

    db.commit()
    db.close()

    logger.info("=" * 50)
    logger.info(f"✅ SYNC COMPLETE")
    logger.info(f"   Inserted : {inserted}")
    logger.info(f"   Skipped  : {skipped} (already existed)")
    logger.info(f"   Unmatched: {unmatched} (patient not found in production)")
    logger.info("=" * 50)

if __name__ == "__main__":
    run()
