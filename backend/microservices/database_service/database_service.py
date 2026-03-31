from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from schemas import InsertPollutionDataRequest
from db import insert_data, fetch_data, init_db, close_db, get_db_connection, release_db_connection
from prometheus_fastapi_instrumentator import Instrumentator
from typing import List, Optional
import logging
import os
import math
import redis
import json
import hashlib
import asyncio
import time
import openaq_sync


# Redis connection
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'redis-service'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    db=int(os.getenv('REDIS_DB', 0)),
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

AVAILABLE_LAYERS = [
    "pm10", "pm2_5", "pm1_0",
    "no2", "co", "co2", "nh3", "vocs",
    "temperature", "humidity", "pressure", "altitude"
]


# HELPER FUNCTIONS
def generate_cache_key(latitude: float, longitude: float, radius: float, 
                       layers: List[str], sensor_types: List[str] = None) -> str:
    """Generate unique cache key for query."""
    sensor_types_sorted = sorted(sensor_types) if sensor_types else ['SPO-RO', 'CityAirQ', 'WearAware']
    layers_sorted = sorted(layers) if layers else 'all'
    
    key_data = json.dumps({
        'lat': round(latitude, 4),
        'lon': round(longitude, 4),
        'radius': radius,
        'layers': layers_sorted,
        'sensor_types': sensor_types_sorted
    }, sort_keys=True)
    
    return f"db_query:{hashlib.md5(key_data.encode()).hexdigest()}"

def get_coordinate_deltas(radius_km: float, latitude_deg: float):
    delta_lat = radius_km / 111.32
    lat_rad = math.radians(latitude_deg)
    km_per_deg_lng = 111.32 * math.cos(lat_rad)
    delta_lng = radius_km / km_per_deg_lng if km_per_deg_lng > 0 else radius_km / 111.32
    return delta_lat, delta_lng

def clear_all_caches() -> int:
    cache_prefixes = ["db_query:*", "provider_query:*", "client_query:*", "route:*"]
    total_cleared = 0
    
    try:
        for prefix in cache_prefixes:
            keys = redis_client.keys(prefix)
            if keys:
                redis_client.delete(*keys)
                total_cleared += len(keys)
        if total_cleared > 0:
            logging.info(f"Cleared {total_cleared} cached queries")
    except Exception as e:
        logging.warning(f"Failed to clear cache: {e}")
    
    return total_cleared


# OPENAQ HELPER FUNCTIONS
def insert_openaq_reading(reading: dict) -> bool:
    """Insert a reading from OpenAQ."""
    try:
        timestamp_us = reading['timestamp'] * 1000
        
        params = (
            reading.get('sensor_type', 'SPO-RO'),
            reading.get('sensor_id'),
            timestamp_us,
            reading.get('latitude'),
            reading.get('longitude'),
            reading.get('altitude', -1),
            reading.get('humidity', -1),
            reading.get('pressure', -1),
            reading.get('temperature', -1),
            reading.get('co', -1),
            reading.get('co2', -1),
            reading.get('no2', -1),
            reading.get('nh3', -1),
            reading.get('pm1_0', -1),
            reading.get('pm2_5', -1),
            reading.get('pm10', -1),
            reading.get('vocs', -1)
        )
        
        insert_data(params)
        return True
    except Exception as e:
        logging.error(f"OpenAQ insert error: {e}")
        return False

def cleanup_old_readings(station_id: str, keep_count: int = 5) -> int:
    """Delete old readings, keeping only latest N."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT timestamp FROM pollution_data
            WHERE sensor_type = 'SPO-RO' AND sensor_id = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """
        cursor.execute(query, (station_id, keep_count))
        rows = cursor.fetchall()
        
        if len(rows) < keep_count:
            cursor.close()
            return 0
        
        cutoff_timestamp = rows[-1][0]
        
        count_query = """
            SELECT COUNT(*) FROM pollution_data
            WHERE sensor_type = 'SPO-RO' AND sensor_id = %s AND timestamp < %s
        """
        cursor.execute(count_query, (station_id, cutoff_timestamp))
        count = cursor.fetchone()[0]
        
        if count == 0:
            cursor.close()
            return 0
        
        delete_query = """
            DELETE FROM pollution_data
            WHERE sensor_type = 'SPO-RO' AND sensor_id = %s AND timestamp < %s
        """
        cursor.execute(delete_query, (station_id, cutoff_timestamp))
        conn.commit()
        cursor.close()
        
        logging.info(f"Cleaned {count} old readings for {station_id}")
        return count
    except Exception as e:
        logging.error(f"Cleanup error for {station_id}: {e}")
        return 0
    finally:
        if conn:
            release_db_connection(conn)


# FASTAPI APPLICATION
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
        logging.info("Database connection pool initialized")
    except Exception as e:
        logging.error(f"Database NOT available at startup: {e}")
    
    try:
        redis_client.ping()
        logging.info(f"Redis connected at {os.getenv('REDIS_HOST', 'redis-service')}:6379")
    except Exception as e:
        logging.warning(f"Redis unavailable: {e}")
    
    # Start OpenAQ sync background task
    sync_task = asyncio.create_task(
        openaq_sync.sync_loop(insert_openaq_reading, cleanup_old_readings, clear_all_caches)
    )
    logging.info(f"OpenAQ sync started (interval: {openaq_sync.SYNC_INTERVAL}s)")
    
    yield
    
    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass
    
    try:
        close_db()
    except:
        pass

app = FastAPI(
    title="Database Service",
    description="QuestDB interface with OpenAQ sync",
    version="2.1.0",
    lifespan=lifespan
)

Instrumentator().instrument(app).expose(app)


# HEALTH ENDPOINTS
@app.get("/")
async def root():
    return {
        "service": "database_service",
        "version": "2.1.0",
        "status": "running",
        "openaq": {
            "interval": openaq_sync.SYNC_INTERVAL,
            "stations": len(openaq_sync.STATIONS)
        }
    }

@app.get("/health")
async def health_check():
    redis_ok = False
    try:
        redis_ok = redis_client.ping()
    except:
        pass
    
    return {
        "status": "healthy",
        "service": "database_service",
        "redis": "connected" if redis_ok else "disconnected",
        "openaq": openaq_sync.sync_status
    }


# OPENAQ ENDPOINTS (for fixed sensors)
@app.post("/openaq/sync")
async def trigger_sync():
    """Manually trigger OpenAQ sync."""
    if openaq_sync.sync_status['running']:
        raise HTTPException(status_code=409, detail="Sync already running")
    
    asyncio.create_task(
        openaq_sync.run_sync(insert_openaq_reading, cleanup_old_readings, clear_all_caches)
    )
    return {"message": "Sync started", "status": openaq_sync.sync_status}

@app.get("/openaq/status")
async def get_sync_status():
    return openaq_sync.get_status()


# DATA INSERTION ENDPOINT
@app.post("/add_data/")
async def add_data(payload: InsertPollutionDataRequest):
    try:
        timestamp_ms = payload.timestamp
        if timestamp_ms is None:
            ROMANIA_OFFSET_MS = 3 * 60 * 60 * 1000
            timestamp_ms = int(time.time() * 1000) + ROMANIA_OFFSET_MS
            logging.info(f"Using current timestamp (GMT+3): {timestamp_ms}")
        
        timestamp_us = timestamp_ms * 1000
        
        params = (
            payload.sensor_type,
            payload.sensor_id,
            timestamp_us,
            payload.latitude,
            payload.longitude,
            payload.altitude,
            payload.humidity,
            payload.pressure,
            payload.temperature,
            payload.co,
            payload.co2,
            payload.no2,
            payload.nh3,
            payload.pm1_0,
            payload.pm2_5,
            payload.pm10,
            payload.vocs
        )

        insert_data(params)
        logging.info(f"Inserted data for {payload.sensor_type}/{payload.sensor_id}")
        clear_all_caches()
        
        return {
            "sensor_type": payload.sensor_type,
            "sensor_id": payload.sensor_id,
            "cache_cleared": True
        }
    except Exception as e:
        logging.error(f"Error adding data: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error adding data: {str(e)}")


# DATA RETRIEVAL ENDPOINT
@app.get("/get_data/")
async def get_data(
    latitude: float = Query(...),
    longitude: float = Query(...),
    radius: float = Query(..., ge=0),
    layers: Optional[List[str]] = Query(None),
    sensor_types: Optional[List[str]] = Query(None)
):
    if not layers:
        layers = AVAILABLE_LAYERS
    if not sensor_types:
        sensor_types = ['CityAirQ', 'WearAware']

    cache_key = generate_cache_key(latitude, longitude, radius, layers, sensor_types)
    
    try:
        cached = redis_client.get(cache_key)
        if cached:
            logging.info(f"Cache HIT: {cache_key}")
            return json.loads(cached)
        logging.info(f"Cache MISS: {cache_key}")
    except Exception as e:
        logging.warning(f"Redis error: {e}")

    try:
        delta_lat, delta_lng = get_coordinate_deltas(radius, latitude)
        params = (layers, latitude, delta_lat, longitude, delta_lng, sensor_types)
        results = fetch_data(params)
        
        try:
            redis_client.setex(cache_key, 300, json.dumps(results))
        except:
            pass
        
        return results
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# CACHE MANAGEMENT
@app.get("/cache/stats")
async def cache_stats():
    try:
        info = redis_client.info("stats")
        memory = redis_client.info("memory")
        db_keys = len(redis_client.keys("db_query:*"))
        
        return {
            "connected": True,
            "hits": info.get("keyspace_hits", 0),
            "misses": info.get("keyspace_misses", 0),
            "cached_queries": db_keys,
            "memory_mb": round(memory.get("used_memory", 0) / 1024 / 1024, 2)
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}

@app.delete("/cache/clear")
async def clear_cache():
    try:
        cleared = clear_all_caches()
        return {"cleared": cleared}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
