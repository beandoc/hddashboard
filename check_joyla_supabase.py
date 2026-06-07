import os
import sys
import psycopg2

print("Checking Supabase PostgreSQL database...")
postgres_url = "postgresql://postgres.skuuvwjsotlqpyobjbsw:Hddashboard%402026@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"

try:
    conn = psycopg2.connect(postgres_url)
    cursor = conn.cursor()
    
    # 1. Search for Joyla
    cursor.execute("SELECT id, name, hid_no, is_active FROM patients WHERE name LIKE '%Joyla%' OR hid_no = '202939012216';")
    rows = cursor.fetchall()
    print("Found patients in Supabase:")
    for r in rows:
        pid, name, hid, active = r
        print(f"  Patient: {name} (ID: {pid}, HID: {hid}, Active: {active})")
        
        # 2. Get latest hemoglobin from monthly records
        cursor.execute(f"SELECT record_month, hb FROM monthly_records WHERE patient_id = {pid} ORDER BY record_month DESC LIMIT 5;")
        m_recs = cursor.fetchall()
        print("  Monthly records:")
        for mr in m_recs:
            print(f"    Month: {mr[0]}, Hb: {mr[1]}")
            
        # 3. Get latest hemoglobin from interim lab records
        cursor.execute(f"SELECT record_month, lab_date, parameter, value FROM interim_lab_records WHERE patient_id = {pid} AND parameter = 'hb' ORDER BY lab_date DESC LIMIT 5;")
        i_recs = cursor.fetchall()
        print("  Interim records:")
        for ir in i_recs:
            print(f"    Month: {ir[0]}, Date: {ir[1]}, Param: {ir[2]}, Val: {ir[3]}")
            
    conn.close()
except Exception as e:
    print("Error connecting to Supabase:", e)
