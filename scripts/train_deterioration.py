
import pickle
import os
import logging
from sqlalchemy.orm import Session
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from database import SessionLocal, Patient, MonthlyRecord
from ml_analytics import (
    predict_hb_trajectory, assess_albumin_decline, 
    compute_target_score, detect_epo_hyporesponse
)

# Disable info logging to keep output clean
logging.getLogger("ml_analytics").setLevel(logging.ERROR)

def extract_risk_features(records_at_time_t, patient):
    """
    records_at_time_t: list of monthly records up to month T, newest first.
    """
    df = [{"month": r.record_month, "hb": r.hb, "albumin": r.albumin, "idwg": r.idwg, 
           "phosphorus": r.phosphorus, "urr": r.urr, "ipth": r.ipth, 
           "serum_ferritin": r.serum_ferritin, "tsat": r.tsat, "bp_sys": r.bp_sys,
           "epo_mircera_dose": r.epo_mircera_dose, "epo_weekly_units": r.epo_weekly_units,
           "weight": r.target_dry_weight or 60.0} for r in records_at_time_t]
    
    hb_res = predict_hb_trajectory(df)
    alb_res = assess_albumin_decline(df)
    target_res = compute_target_score(df)
    epo_res = detect_epo_hyporesponse(df)
    
    return [
        1 if hb_res.get("alert") else 0,
        1 if alb_res.get("risk") else 0,
        target_res.get("score", 0),
        1 if epo_res.get("hypo_response") else 0,
        patient.age or 60
    ]

def train_deterioration_model():
    db = SessionLocal()
    patients = db.query(Patient).all()
    
    X, y = [], []
    
    print("Collecting training data from historical records...")
    
    for p in patients:
        # Fetch all records for this patient, oldest first
        records = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == p.id).order_by(MonthlyRecord.record_month.asc()).all()
        
        # We need at least one pair (Month T and Month T+1) to see if features at T predict hospitalization at T+1
        if len(records) < 2:
            continue
            
        for i in range(len(records) - 1):
            # Features at time i
            records_up_to_i = records[:i+1][::-1] # Newest first
            features = extract_risk_features(records_up_to_i, p)
            
            # Outcome at time i+1
            # Check if patient was hospitalized in the NEXT month
            next_month = records[i+1]
            next_month_hosp = (
                next_month.hospitalization_this_month or 
                next_month.hospitalization_diagnosis is not None or
                next_month.hospitalization_icd_code is not None
            )
            
            X.append(features)
            y.append(1 if next_month_hosp else 0)
            
    if not X:
        print("❌ Error: No patient history found to extract features.")
        db.close()
        return None
        
    n_pos = sum(y)
    print(f"Dataset Size: {len(X)} samples, {n_pos} hospitalizations.")
    
    if n_pos < 2:
        print("⚠️ Warning: Too few hospitalizations recorded in the database to train a robust model.")
        print("   Defaulting to synthetic outcome generation for demonstration if requested, or stopping.")
        # For the purpose of this task, I'll stop here if no data, but I'll provide the script.
        db.close()
        return None
        
    print(f"Training calibrated Logistic Regression model...")
    
    # CalibratedClassifierCV requires at least a few samples per class
    try:
        model = CalibratedClassifierCV(LogisticRegression(max_iter=1000), cv=min(5, n_pos))
        model.fit(X, y)
    except Exception as e:
        print(f"   Calibrated CV failed ({e}), falling back to standard Logistic Regression.")
        model = LogisticRegression(max_iter=1000)
        model.fit(X, y)
        
    # Save the model
    model_path = os.path.join(os.getcwd(), "deterioration_model.pkl")
    with open(model_path, "wb") as f:
        pickle.dump(model, f)
        
    print(f"✅ Model successfully trained and saved to: {model_path}")
    db.close()
    return model

if __name__ == "__main__":
    train_deterioration_model()
