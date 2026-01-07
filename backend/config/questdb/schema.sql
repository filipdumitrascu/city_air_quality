-- QuestDB Schema for CityAirQ Sensor Readings
-- Purpose: Store pollution measurements from fixed and mobile sensors

-- Drop table if exists (for clean reinstall)
DROP TABLE IF EXISTS sensor_readings;

-- Main sensor readings table
CREATE TABLE IF NOT EXISTS sensor_readings (
    sensor_id SYMBOL,              -- Unique sensor identifier (e.g., 'F001', 'M042')
    sensor_type SYMBOL,            -- 'fixed' or 'mobile'
    latitude DOUBLE,               -- GPS latitude (WGS84)
    longitude DOUBLE,              -- GPS longitude (WGS84)
    pm10 DOUBLE,                   -- PM10 concentration (µg/m³)
    pm25 DOUBLE,                   -- PM2.5 concentration (µg/m³)
    no2 DOUBLE,                    -- NO2 concentration (µg/m³)
    timestamp TIMESTAMP            -- Measurement time (designated timestamp)
) timestamp(timestamp) PARTITION BY DAY;

-- Indexes for fast queries
-- Note: QuestDB creates indexes automatically on SYMBOL columns

-- Verify table creation
SELECT 
    'sensor_readings table created successfully' as status,
    COUNT(*) as row_count 
FROM sensor_readings;
