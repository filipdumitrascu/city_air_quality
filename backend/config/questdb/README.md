# QuestDB Configuration

Configuration and setup for CityAirQ pollution monitoring database.

## Database Schema

**Table:** `pollution_datas`

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
SELECT COUNT(*) FROM pollution_datas;

-- Count by sensor type
SELECT sensor_type, COUNT(*) as count 
FROM pollution_datas 
GROUP BY sensor_type;

-- Latest readings
SELECT * FROM pollution_datas 
ORDER BY timestamp DESC 
LIMIT 10;

-- Average pollution by type (last 24 hours)
SELECT 
    sensor_type,
    AVG(pm10) as avg_pm10,
    AVG(pm25) as avg_pm25,
    MAX(pm10) as max_pm10
FROM pollution_datas
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
cur.execute("SELECT COUNT(*) FROM pollution_datas")
count = cur.fetchone()[0]
print(f"Total readings: {count}")
```

---

## Maintenance

### Clear All Data

```sql
TRUNCATE TABLE pollution_datas;
```

### Re-import Data

```bash
python3 populate_questdb.py --force  # Drops and recreates
```

### Backup Data

```bash
# Export to CSV
psql -h localhost -p 8812 -U admin -d qdb -c \
  "COPY (SELECT * FROM pollution_datas) TO STDOUT CSV HEADER" \
  > backup_$(date +%Y%m%d).csv
```

### Restore from Backup

```bash
psql -h localhost -p 8812 -U admin -d qdb -c \
  "COPY pollution_datas FROM STDIN CSV HEADER" < backup.csv
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
### Fixed Stations (SPO-RO via OpenAQ)

| Sensor ID | Location | Lat | Lon | Measures |
|-----------|----------|-----|-----|----------|
| B-1 | București | 44.4473 | 26.0367 | PM10, PM2.5, NO2, CO, O3, SO2 |
| B-2 | București | 44.4180 | 26.1608 | PM10, NO2, CO, SO2 |
| B-3 | București (Obor) | 44.4449 | 26.1273 | PM10, NO2, CO |
| B-4 | București | 44.3839 | 26.1250 | PM10, NO2, SO2 |
| B-5 | București | 44.4195 | 26.0336 | PM10, NO2, CO, SO2 |
| B-6 | București | 44.4350 | 26.0983 | PM10, NO2, CO |
| B-7 | Măgurele | 44.3492 | 26.0308 | PM10, PM2.5, NO2, O3, SO2 |
| B-8 | București | 44.6490 | 26.1445 | PM10, PM2.5, NO2, O3, SO2 |

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
