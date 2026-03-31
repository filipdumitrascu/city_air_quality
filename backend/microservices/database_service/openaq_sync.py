"""
OpenAQ Data Sync Module

Background task that periodically downloads pollution data from 
OpenAQ API for fixed stations in Bucharest.
"""

import os
import logging
import asyncio
import httpx
from datetime import datetime
from typing import List, Callable

SYNC_INTERVAL = int(os.getenv('OPENAQ_SYNC_INTERVAL', '3600'))
READINGS_TO_KEEP = int(os.getenv('OPENAQ_READINGS_TO_KEEP', '5'))
API_KEY = os.getenv('OPENAQ_API_KEY', '')
BASE_URL = "https://api.openaq.org/v3"

STATIONS = {
    # Stations with 2026 data (provider: EEA, id: 70)
    2163068: {'name': 'B-8', 'code': 'B-8'},       # no2, o3, pm10, pm25, so2
    2163072: {'name': 'B-3', 'code': 'B-3'},       # co, no2, pm10
    2163078: {'name': 'B-1', 'code': 'B-1'},       # co, no2, o3, pm10, pm25, so2
    2163080: {'name': 'B-6', 'code': 'B-6'},       # co, no2, pm10
    2163084: {'name': 'B-5', 'code': 'B-5'},       # co, no2, pm10, so2
    2163086: {'name': 'B-4', 'code': 'B-4'},       # no2, pm10, so2
    2163091: {'name': 'B-2', 'code': 'B-2'},       # co, no2, pm10, so2
    2163092: {'name': 'B-7', 'code': 'B-7'},       # no2, o3, pm10, pm25, so2 (Magurele)
}

PARAM_MAP = {
    'pm10': 'pm10',
    'pm25': 'pm2_5',
    'no2': 'no2',
    'co': 'co',
    'o3': 'o3',
    'so2': 'so2',
}

sync_status = {
    'last_sync': None,
    'last_success': None,
    'inserted': 0,
    'errors': 0,
    'running': False
}


# API FUNCTIONS
async def fetch_station_sensors(location_id: int) -> List[dict]:
    """Fetch sensor info for a station."""
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

async def fetch_and_process_station(location_id: int) -> List[dict]:
    """Fetch data for a station and create a reading."""
    readings = []
    station = STATIONS.get(location_id, {})
    station_code = station.get('code', f'OAQ-{location_id}')
    
    sensors = await fetch_station_sensors(location_id)
    if not sensors:
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
    
    for sensor in sensors:
        try:
            param_info = sensor.get('parameter', {})
            param_name = param_info.get('name', '').lower()
            field_name = PARAM_MAP.get(param_name)
            
            if not field_name:
                continue
            
            latest = sensor.get('latest', {})
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
            
            reading[field_name] = value
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
    cleanup_func: Callable[[str, int], int],
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
    
    logging.info("=" * 50)
    logging.info(f"OpenAQ: Starting sync ({len(STATIONS)} stations)")
    logging.info("=" * 50)
    
    total_inserted = 0
    total_errors = 0
    
    for location_id, station_info in STATIONS.items():
        try:
            readings = await fetch_and_process_station(location_id)
            for reading in readings:
                if insert_func(reading):
                    total_inserted += 1
                else:
                    total_errors += 1
        except Exception as e:
            logging.error(f"OpenAQ: Error for {station_info.get('code')}: {e}")
            total_errors += 1
    
    total_cleaned = 0
    for location_id, station_info in STATIONS.items():
        cleaned = cleanup_func(station_info.get('code'), READINGS_TO_KEEP)
        total_cleaned += cleaned
    
    if total_inserted > 0:
        clear_cache_func()
    
    sync_status['running'] = False
    sync_status['inserted'] = total_inserted
    sync_status['errors'] = total_errors
    
    if total_errors == 0 and total_inserted > 0:
        sync_status['last_success'] = datetime.now().isoformat()
    
    logging.info("=" * 50)
    logging.info(f"OpenAQ: Done - {total_inserted} inserted, {total_errors} errors, {total_cleaned} cleaned")
    logging.info("=" * 50)

async def sync_loop(
    insert_func: Callable[[dict], bool],
    cleanup_func: Callable[[str, int], int],
    clear_cache_func: Callable[[], int]
):
    """Background task that syncs data periodically."""
    await asyncio.sleep(30)
    
    while True:
        try:
            await run_sync(insert_func, cleanup_func, clear_cache_func)
        except Exception as e:
            logging.error(f"OpenAQ: Sync loop error: {e}")
        
        logging.info(f"OpenAQ: Next sync in {SYNC_INTERVAL} seconds")
        await asyncio.sleep(SYNC_INTERVAL)

def get_status() -> dict:
    """Get current sync status."""
    return {
        "sync_interval_seconds": SYNC_INTERVAL,
        "readings_per_station": READINGS_TO_KEEP,
        "stations": [info['code'] for info in STATIONS.values()],
        "api_key_configured": bool(API_KEY),
        "status": sync_status
    }
