from database import SessionLocal, Patient

def test_print_active_patients():
    db = SessionLocal()
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.id).all()
    print("\n--- ACTIVE PATIENTS LIST ---")
    for p in patients:
        print(f"ID: {p.id} | Name: {p.name} | HID: {p.hid_no} | Sex: {p.sex} | Age: {p.age}")
    print("----------------------------")
    assert True
