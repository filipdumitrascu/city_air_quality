# QuestDB Configuration

Configuration and setup for CityAirQ pollution monitoring database.

## Database Schema

**Table:** `sensor_readings`

| Column      | Type      | Description                           |
| ----------- | --------- | ------------------------------------- |
| sensor_id   | SYMBOL    | Unique sensor ID (F001, M042, etc)    |
| sensor_type | SYMBOL    | 'fixed' or 'mobile'                   |
| latitude    | DOUBLE    | GPS latitude (WGS84)                  |
| longitude   | DOUBLE    | GPS longitude (WGS84)                 |
| pm10        | DOUBLE    | PM10 concentration (µg/m³)          |
| pm25        | DOUBLE    | PM2.5 concentration (µg/m³)         |
| no2         | DOUBLE    | NO2 concentration (µg/m³)           |
| timestamp   | TIMESTAMP | Measurement time (partitioned by day) |

## Quick Start

### 1. Start QuestDB

```bash
cd ~/city_air_quality/backend
docker-compose up -d questdb

# Verify it's running
docker ps | grep questdb
```

**Ports:**

- `9000` - Web Console (http://localhost:9000)
- `8812` - PostgreSQL wire protocol
- `9009` - InfluxDB line protocol

### 2. Create Schema

```bash
# Option A: Via web console
# Open http://localhost:9000 and paste contents of schema.sql

# Option B: Via psql
psql -h localhost -p 8812 -U admin -d qdb -f schema.sql
```

### 3. Populate with Initial Data

```bash
cd backend/config/questdb
python3 populate_questdb.py
```

**Expected output:**

```
Table created
Inserted 216 FIXED sensor readings
Inserted 792 MOBILE sensor readings
TOTAL: 1008 readings inserted
```

### 4. Import from Excel (Optional)

If you receive real sensor data in Excel format:

```bash
python3 import_from_excel.py sensor_data.xlsx
```

See section below for Excel file format requirements.

---

## Importing Data from Excel

### Excel File Format

**Required columns:**

| sensor_id | sensor_type | latitude | longitude | pm10 | pm25 | no2 | timestamp           |
| --------- | ----------- | -------- | --------- | ---- | ---- | --- | ------------------- |
| F001      | fixed       | 44.5026  | 26.0821   | 35.2 | 20.1 | 28  | 2025-01-03 10:00:00 |
| M042      | mobile      | 44.4680  | 26.0820   | 22.8 | 13.5 | 18  | 2025-01-03 10:05:00 |

**Notes:**

- `sensor_type` must be either 'fixed' or 'mobile'
- `timestamp` format: YYYY-MM-DD HH:MM:SS
- Coordinates in decimal degrees (WGS84)
- Pollution values in µg/m³

### Import Script Usage

```bash
# Import from Excel
python3 import_from_excel.py /path/to/sensor_data.xlsx

# Import with validation
python3 import_from_excel.py sensor_data.xlsx --validate

# Import to different table
python3 import_from_excel.py sensor_data.xlsx --table test_readings
```

---

## Verify Data

### Via Web Console (http://localhost:9000)

```sql
-- Check total records
SELECT COUNT(*) FROM sensor_readings;

-- Count by sensor type
SELECT sensor_type, COUNT(*) as count 
FROM sensor_readings 
GROUP BY sensor_type;

-- Latest readings
SELECT * FROM sensor_readings 
ORDER BY timestamp DESC 
LIMIT 10;

-- Average pollution by type (last 24 hours)
SELECT 
    sensor_type,
    AVG(pm10) as avg_pm10,
    AVG(pm25) as avg_pm25,
    MAX(pm10) as max_pm10
FROM sensor_readings
WHERE timestamp > dateadd('h', -24, now())
GROUP BY sensor_type;
```

### Via Python

```python
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    port=8812,
    user='admin',
    password='quest',
    dbname='qdb'
)

cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM sensor_readings")
count = cur.fetchone()[0]
print(f"Total readings: {count}")
```

---

## Data Strategy

### FIXED Sensors (9 locations)

**Purpose:** Sparse coverage at major intersections

- Băneasa Metro, Victoriei Square, Romana Square
- Unirii Square, Universitate, Obor Market
- Tineretului, Berceni, Herăstrău Park

**Coverage:** ~20% of city area
**PM10 range:** 25-85 µg/m³

### MOBILE Sensors (33 locations)

**Purpose:** Dense coverage filling gaps between fixed sensors

- West corridor (clean alternative route)
- Center corridor (polluted shortcut)
- Residential areas, secondary streets

**Coverage:** ~80% of city area
**PM10 range:** 22-84 µg/m³

### Routing Demonstration Strategy

```
Scenario: Route from Băneasa (North) to Berceni (South)

FIXED sensors only:
├─ Sparse coverage misses center pollution
├─ Chooses short route through center
└─ Result: High PM10 exposure (~75-85 µg/m³)

FIXED + MOBILE sensors:
├─ Dense coverage detects center pollution
├─ Chooses west detour (longer but cleaner)
└─ Result: Low PM10 exposure (~25-36 µg/m³)
```

This demonstrates that **mobile sensor data significantly improves routing quality**.

---

## Maintenance

### Clear All Data

```sql
TRUNCATE TABLE sensor_readings;
```

### Re-import Data

```bash
python3 populate_questdb.py --force  # Drops and recreates
```

### Backup Data

```bash
# Export to CSV
psql -h localhost -p 8812 -U admin -d qdb -c \
  "COPY (SELECT * FROM sensor_readings) TO STDOUT CSV HEADER" \
  > backup_$(date +%Y%m%d).csv
```

### Restore from Backup

```bash
psql -h localhost -p 8812 -U admin -d qdb -c \
  "COPY sensor_readings FROM STDIN CSV HEADER" < backup.csv
```

---

## Connection Details

**PostgreSQL Wire Protocol:**

```
Host: localhost
Port: 8812
User: admin
Password: quest
Database: qdb
```

**Web Console:**

```
URL: http://localhost:9000
```

**Python Connection String:**

```python
postgresql://admin:quest@localhost:8812/qdb
```

---

## Troubleshooting

### QuestDB not responding

```bash
docker-compose restart questdb
docker logs questdb
```

### Port 8812 already in use

```bash
lsof -i :8812
kill -9 <PID>
```

### Cannot connect via psql

```bash
# Check QuestDB is exposing PostgreSQL protocol
docker exec questdb netstat -tulpn | grep 8812

# Verify credentials in docker-compose.yml
docker-compose config | grep -A 5 questdb
```

---

## Resources

- [QuestDB Documentation](https://questdb.io/docs/)
- [QuestDB SQL Reference](https://questdb.io/docs/reference/sql/)
- [Time Series Functions](https://questdb.io/docs/reference/function/time-series/)
- [Python Client Guide](https://questdb.io/docs/clients/python/)
