"""
Import Excel data to QuestDB pollution_data table.

Column order matches QuestDB schema:
  sensor_type, sensor_id, timestamp, latitude, longitude, altitude,
  humidity, pressure, temperature, co, co2, no2, nh3, pm1_0, pm2_5, pm10, vocs

sensor_type values:
  - CityAirQ   (mobile)
  - WearAware  (mobile)
  - SPO-RO     (fixed, EEA stations)
  - Forecast   (predicted, ML)
"""

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
    
    # Verify required columns
    required = ['sensor_type', 'sensor_id', 'timestamp', 'latitude', 'longitude']
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"ERROR: Missing required columns: {missing}")
        sys.exit(1)
    
    # Insert to QuestDB
    print("\nInserting to QuestDB...")
    cur = conn.cursor()
    
    inserted = 0
    errors = 0
    
    for i, row in df.iterrows():
        try:
            # Handle optional columns with default -1
            def get_val(col):
                val = row.get(col, -1)
                if pd.isna(val):
                    return -1.0
                return float(val)
            
            cur.execute("""
                INSERT INTO pollution_data 
                (sensor_type, sensor_id, timestamp, latitude, longitude, altitude,
                 humidity, pressure, temperature, co, co2, no2, nh3, pm1_0, pm2_5, pm10, vocs)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                str(row['sensor_type']),
                str(row['sensor_id']),
                row['timestamp'],
                float(row['latitude']),
                float(row['longitude']),
                get_val('altitude'),
                get_val('humidity'),
                get_val('pressure'),
                get_val('temperature'),
                get_val('co'),
                get_val('co2'),
                get_val('no2'),
                get_val('nh3'),
                get_val('pm1_0'),
                get_val('pm2_5'),
                get_val('pm10'),
                get_val('vocs')
            ))
            inserted += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  Error row {i}: {e}")
        
        if (i + 1) % 100 == 0:
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
        print("\nExpected Excel columns (in order):")
        print("  sensor_type, sensor_id, timestamp, latitude, longitude,")
        print("  altitude, humidity, pressure, temperature,")
        print("  co, co2, no2, nh3, pm1_0, pm2_5, pm10, vocs")
        print("\nExamples:")
        print("  python3 import_from_excel.py fixed_sensors_2026.xlsx")
        print("  python3 import_from_excel.py mobile_sensors_2026.xlsx")
        sys.exit(1)
    
    import_excel(sys.argv[1])
    conn.close()
