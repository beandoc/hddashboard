import logging
from sqlalchemy import text

from db.engine import Base, engine, SessionLocal
import db.models  # noqa: F401 — registers all models with Base.metadata
def create_tables():
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    
    def safe_execute(sql, params=None):
        try:
            db.execute(text(sql), params or {})
            db.commit()
        except Exception as e:
            db.rollback()
            logging.debug(f"Migration statement failed (expected if column/table already exists): {sql} - Error: {e}")

    # 1. Credentials
    safe_execute("ALTER TABLE patient_credentials ADD COLUMN login_username VARCHAR;")
    safe_execute("UPDATE patient_credentials pc SET login_username = p.login_username FROM patients p WHERE pc.patient_id = p.id AND pc.login_username IS NULL;")
    safe_execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_patient_credentials_login_username ON patient_credentials (login_username);")

    # 2. Meal Records
    safe_execute("ALTER TABLE patient_meal_records ADD COLUMN phosphorus DOUBLE PRECISION;")
    safe_execute("ALTER TABLE patient_meal_records ADD COLUMN potassium DOUBLE PRECISION;")
    safe_execute("ALTER TABLE patient_meal_records ADD COLUMN calcium DOUBLE PRECISION;")

    # 3. Food Database
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS food_database_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR UNIQUE NOT NULL,
                synonyms TEXT,
                calories DOUBLE PRECISION NOT NULL,
                protein DOUBLE PRECISION NOT NULL,
                phosphorus DOUBLE PRECISION NOT NULL,
                potassium DOUBLE PRECISION,
                calcium DOUBLE PRECISION,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """))
        db.commit()
    except Exception:
        db.rollback()
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS food_database_items (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR UNIQUE NOT NULL,
                    synonyms TEXT,
                    calories DOUBLE PRECISION NOT NULL,
                    protein DOUBLE PRECISION NOT NULL,
                    phosphorus DOUBLE PRECISION NOT NULL,
                    potassium DOUBLE PRECISION,
                    calcium DOUBLE PRECISION,
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now()
                );
            """))
            db.commit()
        except Exception as e:
            db.rollback()
            logging.error(f"Failed to create food_database_items: {e}")

    safe_execute("ALTER TABLE food_database_items ADD COLUMN potassium DOUBLE PRECISION;")
    safe_execute("ALTER TABLE food_database_items ADD COLUMN calcium DOUBLE PRECISION;")
    safe_execute("ALTER TABLE food_database_items ADD COLUMN serving_size VARCHAR;")

    # 4. Variable Definitions
    safe_execute("ALTER TABLE variable_definitions ADD COLUMN normal_range TEXT;")
    safe_execute("ALTER TABLE variable_definitions ADD COLUMN clinical_significance TEXT;")

    # 5. Research Projects
    safe_execute("ALTER TABLE research_projects ADD COLUMN start_date DATE;")
    safe_execute("ALTER TABLE research_projects ADD COLUMN test_types TEXT;")

    # 6. Symptom Reports
    safe_execute("ALTER TABLE patient_symptom_reports ADD COLUMN session_date DATE;")

    # 7. Monthly Records (Multiple Binders)
    safe_execute("ALTER TABLE monthly_records ADD COLUMN phosphate_binder_details TEXT;")

    # 8. Research Records project_id nullability
    safe_execute("ALTER TABLE research_records ALTER COLUMN project_id DROP NOT NULL;")
    safe_execute("ALTER TABLE research_records DROP CONSTRAINT IF EXISTS research_records_project_id_fkey;")
    safe_execute("ALTER TABLE research_records ADD CONSTRAINT research_records_project_id_fkey FOREIGN KEY (project_id) REFERENCES research_projects(id) ON DELETE SET NULL;")
    try:
        serving_backfill = [
            ("Roti / Chapati / Phulka", "1 roti (~30g)"),
            ("Rice / Chawal", "1 katori (100g)"),
            ("Dal / Sambhar", "1 katori (150ml)"),
            ("Khichdi", "1 bowl (180g)"),
            ("Bread Slices", "1 slice (25g)"),
            ("Naan / Paratha", "1 piece (~80g)"),
            ("Curd / Yogurt / Dahi", "1 katori (100g)"),
            ("Paneer", "1 piece / 30g cube"),
            ("Milk / Doodh", "1 glass (200ml)"),
            ("Cheese", "1 slice (25g)"),
            ("Whole Boiled Egg", "1 whole egg"),
            ("Egg Whites", "1 egg white"),
            ("Chicken / Murgh", "1 piece (60g)"),
            ("Fish / Machli", "1 piece (60g)"),
            ("Mutton / Meat", "1 piece (60g)"),
            ("Samosa", "1 piece (~80g)"),
            ("Poha", "1 bowl (150g)"),
            ("Upma", "1 bowl (150g)"),
            ("Idli", "1 piece (~40g)"),
            ("Dosa", "1 dosa (~60g)"),
            ("Tea / Chai", "1 cup (150ml)"),
            ("Coffee", "1 cup (150ml)"),
            ("Sabzi / Salad", "1 katori (100g)"),
            ("Fruits", "1 medium piece (~100g)"),
            ("Butter / Ghee / Oil", "1 tsp (5g)"),
        ]
        for item_name, serving in serving_backfill:
            db.execute(text(
                "UPDATE food_database_items SET serving_size = :serving WHERE name = :name AND serving_size IS NULL;"
            ), {"name": item_name, "serving": serving})
        db.commit()

        res = db.execute(text("SELECT COUNT(*) FROM food_database_items;")).scalar()
        if res == 0:
            default_foods = [
                # Grains
                ("Roti / Chapati / Phulka", "roti, rotis, chapati, chapatis, phulka", "1 roti (~30g)", 80.0, 2.5, 45.0, 60.0, 28.0),
                ("Rice / Chawal", "rice, chawal", "1 katori (100g)", 180.0, 3.5, 80.0, 55.0, 10.0),
                ("Dal / Sambhar", "dal, dals, sambhar, lentils, curry", "1 katori (150ml)", 120.0, 6.0, 150.0, 400.0, 30.0),
                ("Khichdi", "khichdi", "1 bowl (180g)", 160.0, 5.0, 110.0, 200.0, 25.0),
                ("Bread Slices", "bread, slice", "1 slice (25g)", 70.0, 2.0, 25.0, 40.0, 30.0),
                ("Naan / Paratha", "naan, paratha", "1 piece (~80g)", 220.0, 5.0, 90.0, 80.0, 35.0),
                # Dairy
                ("Curd / Yogurt / Dahi", "curd, yogurt, dahi", "1 katori (100g)", 70.0, 3.5, 95.0, 234.0, 120.0),
                ("Paneer", "paneer", "1 piece / 30g cube", 260.0, 18.0, 250.0, 150.0, 480.0),
                ("Milk / Doodh", "milk, doodh", "1 glass (200ml)", 100.0, 4.5, 140.0, 320.0, 290.0),
                ("Cheese", "cheese", "1 slice (25g)", 110.0, 6.0, 160.0, 98.0, 200.0),
                # Proteins
                ("Whole Boiled Egg", "egg, eggs, boiled egg", "1 whole egg", 75.0, 6.0, 90.0, 63.0, 28.0),
                ("Egg Whites", "egg white, eggwhites, egg-white", "1 egg white", 20.0, 4.0, 10.0, 54.0, 2.0),
                ("Chicken / Murgh", "chicken, murgh", "1 piece (60g)", 165.0, 25.0, 220.0, 220.0, 11.0),
                ("Fish / Machli", "fish, machli", "1 piece (60g)", 120.0, 20.0, 200.0, 340.0, 15.0),
                ("Mutton / Meat", "mutton, meat", "1 piece (60g)", 250.0, 22.0, 240.0, 270.0, 15.0),
                # Snacks
                ("Samosa", "samosa, samosas", "1 piece (~80g)", 250.0, 4.0, 50.0, 150.0, 20.0),
                ("Poha", "poha", "1 bowl (150g)", 200.0, 4.0, 60.0, 100.0, 15.0),
                ("Upma", "upma", "1 bowl (150g)", 200.0, 4.0, 60.0, 100.0, 20.0),
                ("Idli", "idli, idlis", "1 piece (~40g)", 60.0, 1.5, 25.0, 50.0, 15.0),
                ("Dosa", "dosa, dosas", "1 dosa (~60g)", 120.0, 2.5, 40.0, 90.0, 12.0),
                ("Tea / Chai", "tea, chai", "1 cup (150ml)", 60.0, 1.0, 30.0, 88.0, 40.0),
                ("Coffee", "coffee", "1 cup (150ml)", 70.0, 1.5, 40.0, 116.0, 12.0),
                # Veg/Fruits
                ("Sabzi / Salad", "sabzi, sabji, veg, vegetables, salad", "1 katori (100g)", 100.0, 2.0, 50.0, 300.0, 40.0),
                ("Fruits", "apple, banana, papaya, guava, fruit, fruits", "1 medium piece (~100g)", 80.0, 1.0, 15.0, 200.0, 15.0),
                ("Butter / Ghee / Oil", "butter, ghee, oil", "1 tsp (5g)", 110.0, 0.0, 1.0, 3.0, 2.0),
            ]
            for name, synonyms, serving_size, cal, prot, phos, pot, calc in default_foods:
                db.execute(text("""
                    INSERT INTO food_database_items (name, synonyms, serving_size, calories, protein, phosphorus, potassium, calcium)
                    VALUES (:name, :synonyms, :serving_size, :cal, :prot, :phos, :pot, :calc)
                    ON CONFLICT (name) DO NOTHING;
                """), {"name": name, "synonyms": synonyms, "serving_size": serving_size,
                       "cal": cal, "prot": prot, "phos": phos, "pot": pot, "calc": calc})
            db.commit()
    except Exception as e:
        db.rollback()
        logging.error(f"Error during auto-migration: {e}")
    finally:
        db.close()
