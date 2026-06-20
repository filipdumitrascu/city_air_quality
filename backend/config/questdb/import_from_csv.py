import sys
import csv
import psycopg2
from datetime import datetime

# QuestDB connection
conn = psycopg2.connect(
    host='localhost',
    port=8812,
    user='admin',
    password='quest',
    dbname='qdb'
)

def parse_timestamp(ts_str):
    """Parse timestamp from various formats."""
    if not ts_str:
        return None
    
    ts_str = ts_str.strip()
    
    # Handle Z suffix (UTC)
    if ts_str.endswith('Z'):
        ts_str = ts_str[:-1]
    
    formats = [
        '%Y-%m-%dT%H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S.%f',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d',
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            continue
    
    # Try parsing as Unix timestamp (milliseconds)
    try:
        ts_int = int(ts_str)

        if ts_int > 1e12:
            ts_int = ts_int / 1000

        return datetime.fromtimestamp(ts_int)

    except:
        pass

    return None

def get_float(row, col, default=-1.0):
    """Get float value from row, return default if missing or invalid."""
    val = row.get(col, '').strip()

    if not val or val.lower() in ('', 'nan', 'null', 'none', '-'):
        return default
    try:
        return float(val)

    except ValueError:
        return default

def import_csv(filename):
    """Import CSV file to QuestDB pollution_data table."""

    print(f"Loading {filename}...")

    with open(filename, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Loaded {len(rows)} rows")
    print(f"Columns: {list(rows[0].keys()) if rows else 'none'}")

    required = ['sensor_type', 'sensor_id', 'timestamp', 'latitude', 'longitude']
    if rows:
        missing = [c for c in required if c not in rows[0]]
        if missing:
            print(f"ERROR: Missing required columns: {missing}")
            sys.exit(1)

    print("\nInserting to QuestDB...")
    cur = conn.cursor()

    inserted = 0
    errors = 0

    for i, row in enumerate(rows):
        try:
            ts = parse_timestamp(row['timestamp'])
            if not ts:
                errors += 1
                if errors <= 5:
                    print(f"  Error row {i}: Invalid timestamp '{row['timestamp']}'")
                continue

            cur.execute("""
                INSERT INTO pollution_data 
                (sensor_type, sensor_id, timestamp, latitude, longitude, altitude,
                 humidity, pressure, temperature, co, co2, no2, nh3, pm1_0, pm2_5, pm10, vocs)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                row['sensor_type'].strip(),
                row['sensor_id'].strip(),
                ts,
                float(row['latitude']),
                float(row['longitude']),
                get_float(row, 'altitude'),
                get_float(row, 'humidity'),
                get_float(row, 'pressure'),
                get_float(row, 'temperature'),
                get_float(row, 'co'),
                get_float(row, 'co2'),
                get_float(row, 'no2'),
                get_float(row, 'nh3'),
                get_float(row, 'pm1_0'),
                get_float(row, 'pm2_5'),
                get_float(row, 'pm10'),
                get_float(row, 'vocs')
            ))
            inserted += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  Error row {i}: {e}")

        if (i + 1) % 100 == 0:
            conn.commit()
            print(f"  {i+1}/{len(rows)} rows... ({inserted} inserted, {errors} errors)", end='\r')

    conn.commit()

    cur.execute("SELECT COUNT(*) FROM pollution_data")
    total = cur.fetchone()[0]
    print(f"\n\nInserted {inserted} rows (errors: {errors}). Total in DB: {total}")

    cur.execute("SELECT * FROM pollution_data LIMIT 3")
    sample_rows = cur.fetchall()
    print("\nSample from DB:")

    for r in sample_rows:
        print(f"  {r}")

    cur.close()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 import_csv.py <csv_file>")
        print("\nExpected CSV columns:")
        print("  sensor_type, sensor_id, timestamp, latitude, longitude,")
        print("  altitude, humidity, pressure, temperature,")
        print("  co, co2, no2, nh3, pm1_0, pm2_5, pm10, vocs")
        print("\nExample:")
        print("  python3 import_csv.py initial_data.csv")
        sys.exit(1)

    import_csv(sys.argv[1])
    conn.close()
