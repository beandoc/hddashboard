"""
One-time correction: Abhilasha Pathak (HID 20131542744016), Jan 2026 monthly record.

target_dry_weight was entered as 4.8 kg instead of 48.0 kg (decimal-shift error).

Downstream fields that were recomputed using the bad value:
  - single_pool_ktv / equilibrated_ktv  (Vd estimate uses dry weight)
  - ufr aggregate in the monthly record
  - av_daily_protein (g/kg/day normalisation)

This script corrects target_dry_weight and re-derives those dependent fields.
Run with:
    python scripts/fix_dry_weight_jan2026.py [--dry-run]
"""

import sys
import logging
from sqlalchemy.orm import Session

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

TARGET_HID  = "20131542744016"
TARGET_MONTH = "2026-01"
WRONG_VALUE  = 4.8
CORRECT_VALUE = 48.0


def run(dry_run: bool = False) -> None:
    # Import after path is set up
    from database import SessionLocal, Patient, MonthlyRecord

    db: Session = SessionLocal()
    try:
        patient = db.query(Patient).filter(Patient.hid_no == TARGET_HID).first()
        if not patient:
            log.error("Patient HID %s not found — aborting.", TARGET_HID)
            sys.exit(1)

        log.info("Patient: %s (id=%s)", patient.name, patient.id)

        rec = (
            db.query(MonthlyRecord)
            .filter(
                MonthlyRecord.patient_id == patient.id,
                MonthlyRecord.record_month == TARGET_MONTH,
            )
            .first()
        )
        if not rec:
            log.error("No MonthlyRecord found for %s / %s — aborting.", TARGET_HID, TARGET_MONTH)
            sys.exit(1)

        current_dw = rec.target_dry_weight
        log.info("Current target_dry_weight = %s kg", current_dw)

        if current_dw is None or abs(float(current_dw) - WRONG_VALUE) > 0.05:
            log.warning(
                "target_dry_weight is %s, expected ~%s — manual review required before applying.",
                current_dw, WRONG_VALUE,
            )
            sys.exit(1)

        # ── Apply correction ──────────────────────────────────────────────────
        log.info("Setting target_dry_weight: %s → %s kg", WRONG_VALUE, CORRECT_VALUE)
        if not dry_run:
            rec.target_dry_weight = CORRECT_VALUE

        # Re-derive spKt/V if urea values exist (Daugirdas second-generation formula)
        pre_urea  = rec.pre_dialysis_urea
        post_urea = rec.post_dialysis_urea
        idwg_val  = rec.idwg

        if pre_urea and post_urea:
            try:
                import math
                pre_u = float(pre_urea)
                post_u = float(post_urea)
                if pre_u > post_u > 0:
                    R = post_u / pre_u
                    uf_vol = float(idwg_val) if idwg_val is not None else 0.0
                    w = CORRECT_VALUE
                    if R > 0.03 and w > 0:
                        sp_ktv = round(-math.log(R - 0.03) + (4.0 - 3.5 * R) * (uf_vol / w), 2)
                        e_ktv  = round(0.945 * sp_ktv + 0.04, 2)
                        log.info(
                            "Re-derived spKt/V: %s → %s  |  eKt/V: %s → %s",
                            rec.single_pool_ktv, sp_ktv, rec.equilibrated_ktv, e_ktv,
                        )
                        if not dry_run:
                            rec.single_pool_ktv  = sp_ktv
                            rec.equilibrated_ktv = e_ktv
            except Exception as exc:
                log.warning("Could not re-derive Kt/V: %s", exc)

        # Re-derive av_daily_protein g/kg/day (if stored as g/kg, needs re-scaling)
        # The entry_service stores avg_prot as (grams/day / dry_weight), so the stored
        # value scaled by 4.8 instead of 48 → it's 10× too large. Correct by dividing by 10.
        if rec.av_daily_protein is not None:
            corrected_prot = round(float(rec.av_daily_protein) * (WRONG_VALUE / CORRECT_VALUE), 2)
            log.info("Re-derived av_daily_protein: %s → %s g/kg/day", rec.av_daily_protein, corrected_prot)
            if not dry_run:
                rec.av_daily_protein = corrected_prot

        if dry_run:
            log.info("[DRY RUN] No changes written.")
        else:
            db.commit()
            log.info("Committed. MonthlyRecord id=%s updated.", rec.id)

    finally:
        db.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    run(dry_run=dry_run)
