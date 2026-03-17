import sys
import pandas as pd
import psycopg2

# QuestDB connection
conn = psycopg2.connect(
    host='localhost',
    port=8812,
    user='admin',
    password='quest',
    dbname='qdb'
)

def import_excel(filename):
    """Import Excel file to QuestDB pollution_data table."""
    
    # Load Excel
    print(f"Loading {filename}...")
    df = pd.read_excel(filename)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    print(f"Loaded {len(df)} rows")
    print(f"Columns: {list(df.columns)}")
    
    # Insert to QuestDB
    print("\nInserting to QuestDB...")
    cur = conn.cursor()
    
    inserted = 0
    errors = 0
    
    for i, row in df.iterrows():
        try:
            cur.execute("""
                INSERT INTO pollution_data 
                (sensor_id, sensor_type, timestamp, latitude, longitude, altitude,
                 humidity, pressure, temperature, co, co2, no2, nh3, pm1_0, pm2_5, pm10, vocs)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                str(row['sensor_id']),
                str(row['sensor_type']),
                row['timestamp'],
                float(row['latitude']),
                float(row['longitude']),
                float(row['altitude']),
                float(row['humidity']),
                float(row['pressure']),
                float(row['temperature']),
                float(row['co']),
                float(row['co2']),
                float(row['no2']),
                float(row['nh3']),
                float(row['pm1_0']),
                float(row['pm2_5']),
                float(row['pm10']),
                float(row['vocs'])
            ))
            inserted += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  Error row {i}: {e}")
        
        if (i + 1) % 1000 == 0:
            conn.commit()
            print(f"  {i+1}/{len(df)} rows... ({inserted} inserted, {errors} errors)", end='\r')
    
    conn.commit()
    
    # Verify
    cur.execute("SELECT COUNT(*) FROM pollution_data")
    total = cur.fetchone()[0]
    print(f"\n\nInserted {inserted} rows (errors: {errors}). Total in DB: {total}")
    
    # Show sample
    cur.execute("SELECT * FROM pollution_data LIMIT 3")
    rows = cur.fetchall()

    print("\nSample from DB:")
    for row in rows:
        print(f"  {row}")
    
    cur.close()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 import_from_excel.py <excel_file>")
        print("\nExample:")
        print("  python3 import_from_excel.py fixed_sensors_eea_2025_2026.xlsx")
        sys.exit(1)
    
    import_excel(sys.argv[1])
    conn.close()
