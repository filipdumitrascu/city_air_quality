-- QuestDB Schema for CityAirQ Sensor Readings

-- Drop table if exists (for clean reinstall)
DROP TABLE IF EXISTS pollution_data;

-- sensors:
-- SPO-RO                             (fixed)
-- CityAirQ: bme680, mhz19, mics, pm  (mobile)
-- WearAware: bmv080, stcc4           (mobile)
-- Forecast                           (predicted)
CREATE TABLE IF NOT EXISTS pollution_data (
    sensor_type SYMBOL,            -- CityAirQ | WearAware | SPO-RO | Forecast
    sensor_id SYMBOL,              -- unique sensor identifier
    timestamp TIMESTAMP,
    latitude DOUBLE,
    longitude DOUBLE,
    altitude DOUBLE,               -- bme680
    humidity DOUBLE,               -- bme680
    pressure DOUBLE,               -- bme680
    temperature DOUBLE,            -- bme680
    co DOUBLE,                     -- mics
    co2 DOUBLE,                    -- mhz19, stcc44
    no2 DOUBLE,                    -- mics
    nh3 DOUBLE,                    -- mics
    pm1_0 DOUBLE,                  -- pm, bmv080
    pm2_5 DOUBLE,                  -- pm, bmv080
    pm10 DOUBLE,                   -- pm, bmv080
    vocs DOUBLE                    -- bme680
) timestamp(timestamp) PARTITION BY DAY;
