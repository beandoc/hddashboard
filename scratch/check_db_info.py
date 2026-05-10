from database import SessionLocal, Patient, ResearchRecord, ResearchProject
import json

db = SessionLocal()

try:
    # 1. Count patients
    patient_count = db.query(Patient).count()
    active_patient_count = db.query(Patient).filter(Patient.is_active == True).count()
    print(f"Total patients in database: {patient_count}")
    print(f"Active patients in database: {active_patient_count}")
    
    print("\nPatients list (first 45):")
    patients = db.query(Patient).order_by(Patient.id).limit(45).all()
    for p in patients:
        print(f"ID: {p.id}, Name: {p.name}, Active: {p.is_active}")

    # 2. Check for Research Projects
    projects = db.query(ResearchProject).all()
    print(f"Research Projects found: {len(projects)}")
    for p in projects:
        print(f"  - Project: {p.title} (ID: {p.id})")

    # 3. Check for all Research records
    all_records = db.query(ResearchRecord).all()
    print(f"Total Research records found: {len(all_records)}")
    for r in all_records:
        patient = db.query(Patient).filter(Patient.id == r.patient_id).first()
        data = json.loads(r.data) if r.data else {}
        print(f"  - [{r.test_type}] for {patient.name if patient else 'Unknown'} on {r.test_date}: {data}")

    # 5. Check DryWeightAssessment table for BIA data
    from database import DryWeightAssessment
    dw_assessments = db.query(DryWeightAssessment).all()
    print(f"Dry Weight Assessments found: {len(dw_assessments)}")
    for a in dw_assessments:
        if any([a.bia_fluid_overload_litres, a.bia_overhydration_percent, a.bia_total_body_water, a.bia_phase_angle]):
            patient = db.query(Patient).filter(Patient.id == a.patient_id).first()
            print(f"  - [DryWeightAssessment] BIA Data for {patient.name if patient else 'Unknown'} on {a.assessment_date}:")
            print(f"    Fluid Overload: {a.bia_fluid_overload_litres} L, Phase Angle: {a.bia_phase_angle}")

finally:
    db.close()
