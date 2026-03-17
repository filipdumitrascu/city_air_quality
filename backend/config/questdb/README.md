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
| pm10        | DOUBLE    | PM10 concentration (µg/m³)            |
| pm25        | DOUBLE    | PM2.5 concentration (µg/m³)           |
| no2         | DOUBLE    | NO2 concentration (µg/m³)             |
| timestamp   | TIMESTAMP | Measurement time (partitioned by day) |

## Quick Start

### 1. Start QuestDB

```bash
cd ~/city_air_quality/backend
docker compose up -d questdb

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

## Sensors
### Fixed

| Sensor ID | Location | Lat | Lon | Measures |
|-----------|----------|-----|-----|----------|
| F_RO0065A | Cercetari | 44.4419 | 26.0294 | NO2, CO |
| F_RO0066A | Mihai Bravu | 44.4286 | 26.1302 | PM10, NO2, CO |
| F_RO0067A | Drumul Taberei | 44.4244 | 26.0331 | PM10, NO2, CO |
| F_RO0068A | Lacul Morii | 44.4489 | 26.0256 | PM10, NO2 |
| F_RO0069A | Titan | 44.4106 | 26.1456 | PM10, NO2, CO |
| F_RO0070A | Militari | 44.4350 | 26.0006 | PM10, NO2, CO |
| F_RO0229A | Obor | 44.4500 | 26.1200 | PM10, PM2.5, NO2 |

## Troubleshooting

### QuestDB not responding

```bash
docker compose restart questdb
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
docker compose config | grep -A 5 questdb
```

---

## Resources

- [QuestDB Documentation](https://questdb.io/docs/)
- [QuestDB SQL Reference](https://questdb.io/docs/reference/sql/)
- [Time Series Functions](https://questdb.io/docs/reference/function/time-series/)
- [Python Client Guide](https://questdb.io/docs/clients/python/)
