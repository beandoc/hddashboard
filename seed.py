import os
import random
from datetime import datetime, timedelta
from database import Patient, MonthlyRecord, SessionLocal, User
from main import pwd_context

def seed():
    db = SessionLocal()
    # Check if data already exists
    if db.query(Patient).count() > 0:
        print("⚠️ Database already has data. Skipping seed.")
        return

    print("🌱 Seeding clinical data...")
    
    # Create default admin if not exists
    if not db.query(User).filter(User.username == "admin").first():
        admin = User(
            username="admin", 
            full_name="System Admin", 
            hashed_password=pwd_context.hash("admin123"), 
            role="admin"
        )
        db.add(admin)
        db.commit()

    staff_names = [
        ('Rajesh Kumar', 'M'), 
        ('Sita Devi', 'F'), 
        ('Amit Sharma', 'M'), 
        ('Priya Singh', 'F'), 
        ('Vikram Sahay', 'M')
    ]
    access_options = ['AVF', 'AVF', 'AVF', 'Left IJV Permcath', 'AV Graft']
    
    for i, (name, sex) in enumerate(staff_names):
        p = Patient(
            hid_no=f'HID{100+i}', 
            name=name, 
            sex=sex, 
            contact_no='998877'+str(i)*4, 
            diagnosis='CKD Stage 5D', 
            access_type=access_options[random.randint(0, 4)], 
            is_active=True, 
            created_by='admin'
        )
        db.add(p)
        db.commit()
        
        # Add 12 months of trends
        for month_offset in range(12):
            # Sort months ascendingly
            month_date = datetime.now() - timedelta(days=335 - (month_offset * 30))
            month_str = month_date.strftime('%Y-%m')
            
            # Create semi-realistic trends (slightly random walk)
            r = MonthlyRecord(
                patient_id=p.id, 
                record_month=month_str, 
                entered_by='admin',
                hb=random.uniform(9.0, 11.5), 
                albumin=random.uniform(2.8, 3.8),
                phosphorus=random.uniform(4.0, 6.5), 
                idwg=random.uniform(1.8, 3.2),
                ipth=random.uniform(200, 450), 
                vit_d=random.uniform(15, 35),
                epo_mircera_dose=f'Mircera {random.choice([50, 75, 100])}mcg'
            )
            db.add(r)
    
    db.commit()
    print("✅ Clinical unit seeded with 5 patients and 12 months of data.")

if __name__ == "__main__":
    seed()
