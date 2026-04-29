
import statistics
import logging
from sqlalchemy.orm import Session
from database import SessionLocal, Patient, MonthlyRecord
from ml_analytics import predict_hb_trajectory, assess_albumin_decline

# Disable info logging to keep output clean
logging.getLogger("ml_analytics").setLevel(logging.ERROR)

def validate_hb_predictions(db: Session, patient_id: int):
    # Fetch records oldest-first
    records = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id).order_by(MonthlyRecord.record_month.asc()).all()
    
    if len(records) < 5:
        return []
        
    errors = []
    # Start validation from the 5th record onwards
    for i in range(4, len(records)):
        train_records = records[:i]
        actual = records[i].hb
        
        if actual is None:
            continue
            
        # Convert to List[Dict] and sort newest-first as expected by the prediction engine
        train_df = [{"month": r.record_month, "hb": r.hb} for r in train_records]
        train_df_newest_first = train_df[::-1]
        
        pred_obj = predict_hb_trajectory(train_df_newest_first)
        predicted = pred_obj.get("next_predicted")
        
        if predicted is not None:
            errors.append(abs(actual - predicted))
            
    return errors

def validate_albumin_predictions(db: Session, patient_id: int):
    # Fetch records oldest-first
    records = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id).order_by(MonthlyRecord.record_month.asc()).all()
    
    if len(records) < 5:
        return []
        
    errors = []
    # Start validation from the 5th record onwards
    for i in range(4, len(records)):
        train_records = records[:i]
        actual = records[i].albumin
        
        if actual is None:
            continue
            
        # Convert to List[Dict] and sort newest-first as expected by the prediction engine
        train_df = [{"month": r.record_month, "albumin": r.albumin} for r in train_records]
        train_df_newest_first = train_df[::-1]
        
        pred_obj = assess_albumin_decline(train_df_newest_first)
        predicted = pred_obj.get("predicted")
        
        if predicted is not None:
            errors.append(abs(actual - predicted))
            
    return errors

def validate_mortality_model(db: Session):
    patients = db.query(Patient).all()
    y_pred, y_true = [], []
    
    print("\n--- Mortality Calibration (1-Year) ---")
    
    for p in patients:
        # Fetch all records to get the baseline (first prediction) month
        records = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == p.id).order_by(MonthlyRecord.record_month.asc()).all()
        if not records:
            continue
            
        first_month_str = records[0].record_month
        try:
            first_date = datetime.strptime(first_month_str, "%Y-%m").date()
        except:
            continue
            
        # Get the prediction based on the first month's data
        # We need the format expected by predict_mortality_risk: List[Dict] with newest first
        # But for calibration, we use the baseline (first) record to see if it predicts 1-year outcome.
        baseline_df = [{"month": r.record_month, "hb": r.hb, "albumin": r.albumin, "wbc_count": r.wbc_count, "crp": r.crp, "hospitalization_this_month": r.hospitalization_this_month} for r in records[:1]]
        
        # Build patient info
        pt_info = {
            "age": p.age,
            "cad_status": p.cad_status,
            "dm_status": p.dm_status,
            "chf_status": p.chf_status,
            "ef": p.ejection_fraction
        }
        
        prob_obj = predict_mortality_risk(baseline_df, pt_info)
        prob = prob_obj.get("risk_probability")
        
        # Determine ground truth (1-year mortality)
        died_within_1yr = False
        if p.current_survival_status == "Deceased" and p.date_of_death:
            days_to_death = (p.date_of_death - first_date).days
            if 0 <= days_to_death <= 365:
                died_within_1yr = True
        
        # For a fair calibration, we only include patients who either:
        # 1. Died within 1 year
        # 2. Survived for at least 1 year (last record or transfer date is > 1yr from first record)
        
        is_valid_sample = False
        if died_within_1yr:
            is_valid_sample = True
        else:
            # Check if we have at least 1 year of follow-up
            last_record_month = records[-1].record_month
            try:
                last_date = datetime.strptime(last_record_month, "%Y-%m").date()
                if (last_date - first_date).days >= 330: # ~11-12 months
                    is_valid_sample = True
            except:
                pass
            
            if not is_valid_sample and p.date_facility_transfer:
                if (p.date_facility_transfer - first_date).days >= 330:
                    is_valid_sample = True

        if is_valid_sample and prob is not None:
            y_pred.append(prob)
            y_true.append(1 if died_within_1yr else 0)

    if not y_true:
        print("No patients with sufficient 1-year follow-up or recorded outcomes for calibration.")
        return
        
    brier = sum((t - p)**2 for t, p in zip(y_true, y_pred)) / len(y_true)
    
    # Simple C-index (AUC)
    from sklearn.metrics import roc_auc_score
    try:
        c_index = roc_auc_score(y_true, y_pred)
    except:
        c_index = 0.5 # Default if only one class present
        
    print(f"Brier Score:        {brier:.4f} (Lower is better)")
    print(f"Harrell's C-index:  {c_index:.3f} (Target > 0.70)")
    print(f"Sample Size:        n={len(y_true)} patients with outcomes")
    
    if c_index > 0.7:
        print("  ✅ Status: VALIDATED (Good discrimination)")
    else:
        print("  ⚠️ Status: NEEDS CALIBRATION (Poor discrimination)")

def main():
    db = SessionLocal()
    patients = db.query(Patient).filter(Patient.is_active == True).all()
    
    all_hb_errors = []
    all_alb_errors = []
    
    print("="*60)
    print(" UNIT ANALYTICS VALIDATION REPORT")
    print("="*60)
    print(f"Total Active Patients: {len(patients)}")
    
    for p in patients:
        hb_errs = validate_hb_predictions(db, p.id)
        if hb_errs:
            all_hb_errors.extend(hb_errs)
            
        alb_errs = validate_albumin_predictions(db, p.id)
        if alb_errs:
            all_alb_errors.extend(alb_errs)
            
    print("\n--- Prediction Accuracy (MAE) ---")
    
    if all_hb_errors:
        mae_hb = statistics.mean(all_hb_errors)
        print(f"Hb Trajectory MAE:     {mae_hb:.3f} g/dL (n={len(all_hb_errors)})")
    else:
        print("Hb Trajectory: No sufficient data.")
        
    if all_alb_errors:
        mae_alb = statistics.mean(all_alb_errors)
        print(f"Albumin Decline MAE:   {mae_alb:.3f} g/dL (n={len(all_alb_errors)})")
    else:
        print("Albumin Decline: No sufficient data.")
        
    validate_mortality_model(db)
    
    print("="*60)
    db.close()

if __name__ == "__main__":
    main()
