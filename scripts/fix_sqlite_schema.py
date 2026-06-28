import sqlite3
import sqlalchemy as sa
from database import Base, engine

def fix_schema():
    # Connect to the SQLite database
    db_path = 'hd_dashboard.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get a list of all tables in SQLite
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    sqlite_tables = [row[0] for row in cursor.fetchall()]

    bind = engine
    inspector = sa.inspect(bind)

    for table_name, table in Base.metadata.tables.items():
        if table_name not in sqlite_tables:
            print(f"Table {table_name} is missing in SQLite, skipping (create_all will handle it)")
            continue
        
        # Get existing columns in SQLite for this table
        cursor.execute(f"PRAGMA table_info({table_name});")
        existing_cols = {row[1]: row[2] for row in cursor.fetchall()}

        # Check each column in the SQLAlchemy table definition
        for col in table.columns:
            if col.name not in existing_cols:
                # Get SQLite type name
                type_name = str(col.type.compile(dialect=bind.dialect))
                # Map dialect specific types if needed
                if "VARCHAR" in type_name or "String" in type_name:
                    type_name = "VARCHAR"
                elif "DATETIME" in type_name or "DateTime" in type_name:
                    type_name = "DATETIME"
                elif "BOOLEAN" in type_name or "Boolean" in type_name:
                    type_name = "BOOLEAN"
                
                alter_query = f"ALTER TABLE {table_name} ADD COLUMN {col.name} {type_name}"
                print(f"Executing: {alter_query}")
                try:
                    cursor.execute(alter_query)
                    conn.commit()
                except Exception as e:
                    print(f"Error adding column {col.name} to {table_name}: {e}")

    conn.close()
    print("Schema alignment check complete.")

if __name__ == "__main__":
    fix_schema()
