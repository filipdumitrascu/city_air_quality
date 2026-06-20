"""
- fetch_station_pollutants() function  returns all the pollutants measured by a station

- process_station() function  returns all data about a station

- run_sync() function  inserts all the data about all the stations into the database and clear the cache
It also calls the `trigger_gap_fill` function every 6 hours

- trigger_gap_fill() sends HTTP POST request to Forecast_Service
"""

import os
import logging
import asyncio
import httpx
from datetime import datetime
from typing import List, Callable

# ENV variables
BASE_URL = "https://api.openaq.org/v3"
API_KEY = os.getenv('OPENAQ_API_KEY', '')
SYNC_INTERVAL = int(os.getenv('OPENAQ_SYNC_INTERVAL', '3600'))
FORECAST_SERVICE_URL = os.getenv('FORECAST_SERVICE_URL', 'http://forecast-service:8000')
ENABLE_GAP_FILL = os.getenv('ENABLE_GAP_FILL', 'true').lower() == 'true'


# Active Bucharest stations with 2026 data (provider: EEA, id: 70)
# B-9 to B-30 are offline since 2024-07-30
STATIONS = {
    2163078: {'name': 'B-1', 'code': 'B-1'},   # co, no2, o3, pm10, pm25, so2
    2163091: {'name': 'B-2', 'code': 'B-2'},   # co, no2, pm10, so2
    2163072: {'name': 'B-3', 'code': 'B-3'},   # co, no2, pm10
    2163086: {'name': 'B-4', 'code': 'B-4'},   # no2, pm10, so2
    2163084: {'name': 'B-5', 'code': 'B-5'},   # co, no2, pm10, so2
    2163080: {'name': 'B-6', 'code': 'B-6'},   # co, no2, pm10
    2163092: {'name': 'B-7', 'code': 'B-7'},   # no2, o3, pm10, pm25, so2
    2163068: {'name': 'B-8', 'code': 'B-8'},   # no2, o3, pm10, pm25, so2
}

sync_status = {
    'last_sync': None,
    'last_success': None,
    'inserted': 0,
    'errors': 0,
    'running': False,
    'last_gap_fill': None,
    'gaps_filled': 0
}


# API FUNCTIONS
async def fetch_station_pollutants(location_id: int) -> List[dict]:
    """Fetch the pollutants for a station."""
    if not API_KEY:
        return []

    url = f"{BASE_URL}/locations/{location_id}/sensors"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers={"X-API-Key": API_KEY})
            response.raise_for_status()
            return response.json().get('results', [])

    except httpx.HTTPStatusError as e:
        logging.warning(f"OpenAQ: HTTP {e.response.status_code} for location {location_id}")
        return []

    except Exception as e:
        logging.error(f"OpenAQ: Error fetching location {location_id}: {e}")
        return []


async def process_station(location_id: int) -> List[dict]:
    """Return all the readings for a station."""
    readings = []
    station = STATIONS.get(location_id, {})
    station_code = station.get('code', f'OAQ-{location_id}')

    pollutants = await fetch_station_pollutants(location_id)
    if not pollutants:
        return readings

    reading = {
        'sensor_type': 'SPO-RO',
        'sensor_id': station_code,
        'timestamp': None,
        'latitude': None,
        'longitude': None,
    }

    latest_timestamp = None
    pollutant_count = 0

    # Max age for data (7 days in milliseconds)
    max_age_ms = 7 * 24 * 60 * 60 * 1000
    now_ms = int(datetime.now().timestamp() * 1000)

    # Romania timezone offset (GMT+3 in summer)
    ROMANIA_OFFSET_MS = 3 * 60 * 60 * 1000

    for pollutant in pollutants:
        try:
            param_info = pollutant.get('parameter', {})
            param_name = param_info.get('name', '').lower()

            if not param_name:
                continue

            if param_name == "pm25":
                param_name = "pm2_5"

            latest = pollutant.get('latest', {})
            if not latest:
                continue

            value = latest.get('value')
            if value is None:
                continue

            dt_info = latest.get('datetime', {})
            dt_utc = dt_info.get('utc')
            if dt_utc:
                dt = datetime.fromisoformat(dt_utc.replace('Z', '+00:00'))
                timestamp_ms = int(dt.timestamp() * 1000)

                # Skip data older than max_age
                if now_ms - timestamp_ms > max_age_ms:
                    continue

                # Add Romania timezone offset (GMT+3)
                timestamp_ms += ROMANIA_OFFSET_MS

                if latest_timestamp is None or timestamp_ms > latest_timestamp:
                    latest_timestamp = timestamp_ms

            coords = latest.get('coordinates', {})
            if coords:
                reading['latitude'] = coords.get('latitude')
                reading['longitude'] = coords.get('longitude')

            reading[param_name] = value
            pollutant_count += 1

        except Exception as e:
            logging.warning(f"OpenAQ: Error processing sensor: {e}")

    if latest_timestamp and reading.get('latitude') and pollutant_count > 0:
        reading['timestamp'] = latest_timestamp
        readings.append(reading)
        logging.info(f"OpenAQ: {station_code} - {pollutant_count} pollutants")
    else:
        logging.info(f"OpenAQ: {station_code} - skipped (no fresh data)")

    return readings


# SYNC FUNCTIONS
async def run_sync(
    insert_func: Callable[[dict], bool],
    clear_cache_func: Callable[[], int]
):
    """Main sync function."""
    global sync_status

    if sync_status['running']:
        logging.warning("OpenAQ: Sync already running")
        return

    if not API_KEY:
        logging.error("OpenAQ: No API key! Set OPENAQ_API_KEY env var.")
        return

    sync_status['running'] = True
    sync_status['last_sync'] = datetime.now().isoformat()

    logging.info(f"OpenAQ: Starting sync ({len(STATIONS)} stations)")

    total_inserted = 0
    total_errors = 0

    for location_id, station_info in STATIONS.items():
        try:
            readings = await process_station(location_id)
            for reading in readings:
                if insert_func(reading):
                    total_inserted += 1
                else:
                    total_errors += 1
        except Exception as e:
            logging.error(f"OpenAQ: Error for {station_info.get('code')}: {e}")
            total_errors += 1

    if total_inserted > 0:
        clear_cache_func()

    sync_status['inserted'] = total_inserted
    sync_status['errors'] = total_errors

    if total_errors == 0 and total_inserted > 0:
        sync_status['last_success'] = datetime.now().isoformat()

    logging.info(f"OpenAQ: Done - {total_inserted} inserted, {total_errors} errors")


    # FORECAST SERVICE SYNC (at 00:00, 06:00, 12:00, 18:00 GMT)
    current_hour = datetime.utcnow().hour
    should_fill_gaps = ENABLE_GAP_FILL and total_inserted > 0 and (current_hour % 6 == 0)

    if should_fill_gaps:
        logging.info(f"Forecast: Gap fill triggered (hour={current_hour}, every 6h)")
        gaps_filled = await trigger_gap_fill()

        sync_status['gaps_filled'] = gaps_filled
        if gaps_filled > 0:
            clear_cache_func()

    elif ENABLE_GAP_FILL and total_inserted > 0:
        logging.info(f"Forecast: Skipping gap fill (hour={current_hour}, next at hour divisible by 6)")

    sync_status['running'] = False

async def trigger_gap_fill() -> int:
    """
    Call forecast_service to fill gaps near existing sensors.
    Returns number of gaps filled.
    """
    global sync_status

    logging.info("OpenAQ: Triggering gap fill for visualization...")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{FORECAST_SERVICE_URL}/predict/fill-gaps",
                params={
                    "max_neighbor_distance_km": 1.0,
                    "resolution": 0.005  # ~500m grid for visualization
                }
            )

            if response.status_code == 200:
                data = response.json()
                gaps_filled = data.get('gaps_filled', 0)

                sync_status['last_gap_fill'] = datetime.now().isoformat()
                logging.info(f"OpenAQ: Gap fill complete - {gaps_filled} points filled")

                return gaps_filled

            logging.warning(f"OpenAQ: Gap fill failed with status {response.status_code}")
            return 0

    except httpx.ConnectError:
        logging.info("OpenAQ: Forecast service not available - skipping gap fill")
        return 0

    except Exception as e:
        logging.warning(f"OpenAQ: Gap fill error: {e}")
        return 0

async def sync_loop(
    insert_func: Callable[[dict], bool],
    clear_cache_func: Callable[[], int]
):
    """Background task that syncs data periodically."""
    await asyncio.sleep(30)

    while True:
        try:
            await run_sync(insert_func, clear_cache_func)
        except Exception as e:
            logging.error(f"OpenAQ: Sync loop error: {e}")

        logging.info(f"OpenAQ: Next sync in {SYNC_INTERVAL} seconds")
        await asyncio.sleep(SYNC_INTERVAL)

def get_status() -> dict:
    """Get current sync status."""
    return {
        "sync_interval_seconds": SYNC_INTERVAL,
        "stations": [info['code'] for info in STATIONS.values()],
        "api_key_configured": bool(API_KEY),
        "gap_fill_enabled": ENABLE_GAP_FILL,
        "forecast_service_url": FORECAST_SERVICE_URL,
        "status": sync_status
    }
