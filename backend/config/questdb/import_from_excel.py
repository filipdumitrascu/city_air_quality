"""Import sensor data from Excel to QuestDB."""

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
    """Import Excel file to QuestDB."""
    
    # Load Excel
    print(f"Loading {filename}...")
    df = pd.read_excel(filename)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    print(f"Loaded {len(df)} rows")
    
    # Insert to QuestDB
    print("Inserting to QuestDB...")
    cur = conn.cursor()
    
    for i, row in df.iterrows():
        cur.execute("""
            INSERT INTO sensor_readings 
            (sensor_id, sensor_type, latitude, longitude, pm10, pm25, no2, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            row['sensor_id'],
            row['sensor_type'],
            float(row['latitude']),
            float(row['longitude']),
            float(row['pm10']),
            float(row['pm25']),
            float(row['no2']),
            row['timestamp']
        ))
        
        if (i + 1) % 100 == 0:
            conn.commit()
            print(f"  {i+1}/{len(df)} rows...", end='\r')
    
    conn.commit()
    
    # Verify
    cur.execute("SELECT COUNT(*) FROM sensor_readings")
    total = cur.fetchone()[0]
    print(f"\nInserted {len(df)} rows. Total in DB: {total}")
    
    cur.close()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 import_from_excel.py <excel_file>")
        sys.exit(1)
    
    import_excel(sys.argv[1])
    conn.close()
