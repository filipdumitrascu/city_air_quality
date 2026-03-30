from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from schemas import InsertPollutionDataRequest
from db import insert_data, fetch_data, init_db, close_db
from prometheus_fastapi_instrumentator import Instrumentator
from typing import List, Optional
import logging
import os
import math
import redis
import json
import hashlib


# Redis connection for caching
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'redis-service'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    db=int(os.getenv('REDIS_DB', 0)),
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5
)

# Logging to stdout only
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Available layers matching pollution_data schema
AVAILABLE_LAYERS = [
    "pm10", "pm2_5", "pm1_0",  # Particulate matter
    "no2", "co", "co2", "nh3", "vocs",  # Gases
    "temperature", "humidity", "pressure", "altitude"  # Weather
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
    
    hash_hex = hashlib.md5(key_data.encode()).hexdigest()
    return f"db_query:{hash_hex}"

def get_coordinate_deltas(radius_km: float, latitude_deg: float):
    """Calculate latitude and longitude deltas for a given radius in km."""
    delta_lat = radius_km / 111.32
    lat_rad = math.radians(latitude_deg)
    km_per_deg_lng = 111.32 * math.cos(lat_rad)
    delta_lng = radius_km / km_per_deg_lng if km_per_deg_lng > 0 else radius_km / 111.32
    return delta_lat, delta_lng


# FASTAPI APPLICATION
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database connection pool on startup."""
    try:
        init_db()
        logging.info("Database connection pool initialized")
    except Exception as e:
        logging.error(f"Database NOT available at startup: {e}")
    
    try:
        redis_client.ping()
        logging.info(f"Redis connected at {os.getenv('REDIS_HOST', 'redis-service')}:6379")
    except Exception as e:
        logging.warning(f"Redis unavailable (caching disabled): {e}")
    
    yield
    
    try:
        close_db()
        logging.info("Database connections closed")
    except Exception:
        pass


app = FastAPI(
    title="Database Service",
    description="QuestDB interface for pollution data",
    version="2.0.0",
    lifespan=lifespan
)

Instrumentator().instrument(app).expose(app)


# HEALTH ENDPOINTS
@app.get("/")
async def root():
    return {
        "service": "database_service",
        "version": "2.0.0",
        "status": "running"
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
        "redis": "connected" if redis_ok else "disconnected"
    }


# DATA INSERTION ENDPOINT
@app.post("/add_data/")
async def add_data(payload: InsertPollutionDataRequest):
    """
    Insert sensor data into pollution_data table.
    
    Accepts data from CityAirQ, WearAware, SPO-RO, and Forecast sensors.
    If timestamp is not provided, current time is used.
    Clears query cache after successful insert to ensure fresh data.
    """
    try:
        # Use current timestamp if not provided (adjusted for Romania GMT+3)
        timestamp_ms = payload.timestamp
        if timestamp_ms is None:
            import time
            ROMANIA_OFFSET_MS = 3 * 60 * 60 * 1000  # 3 hours
            timestamp_ms = int(time.time() * 1000) + ROMANIA_OFFSET_MS
            logging.info(f"Using current timestamp (GMT+3): {timestamp_ms}")
        
        # Convert timestamp from milliseconds to microseconds for QuestDB
        timestamp_us = timestamp_ms * 1000
        
        # Build params tuple matching pollution_data schema
        # Order: sensor_type, sensor_id, timestamp, latitude, longitude, ...
        params = (
            payload.sensor_type,
            payload.sensor_id,  # Can be None for Forecast
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
        
        # Clear query cache to ensure new data is visible
        try:
            keys = redis_client.keys("db_query:*")
            if keys:
                redis_client.delete(*keys)
                logging.info(f"Cleared {len(keys)} cached queries after insert")
        except Exception as e:
            logging.warning(f"Failed to clear cache: {e}")
        
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
    """
    Retrieve pollution data within a geographic radius.
    
    Args:
        latitude: Center point latitude
        longitude: Center point longitude
        radius: Search radius in kilometers
        layers: Optional list of pollution metrics to retrieve
        sensor_types: Optional list of sensor types
    
    Returns:
        List of sensor readings with requested metrics
    """
    # Default layers and sensor types
    if not layers:
        layers = AVAILABLE_LAYERS
    
    if not sensor_types:
        sensor_types = ['CityAirQ', 'WearAware']

    # Redis cache check
    cache_key = generate_cache_key(latitude, longitude, radius, layers, sensor_types)
    
    try:
        cached_result = redis_client.get(cache_key)
        if cached_result:
            logging.info(f"Cache HIT: {cache_key}")
            return json.loads(cached_result)
        logging.info(f"Cache MISS: {cache_key}")
    except Exception as e:
        logging.warning(f"Redis error: {e}")

    # Query database
    try:
        delta_lat, delta_lng = get_coordinate_deltas(radius, latitude)
        
        params = (layers, latitude, delta_lat, longitude, delta_lng, sensor_types)
        results = fetch_data(params)
        
        # Cache result (TTL: 5 minutes)
        try:
            redis_client.setex(cache_key, 300, json.dumps(results))
            logging.info(f"Cached result: {cache_key} (TTL: 300s)")
        except Exception as e:
            logging.warning(f"Failed to cache: {e}")
        
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching data: {str(e)}")


# CACHE MANAGEMENT
@app.get("/cache/stats")
async def cache_stats():
    """Get Redis cache statistics."""
    try:
        info = redis_client.info("stats")
        memory = redis_client.info("memory")
        db_keys = len(redis_client.keys("db_query:*"))
        
        return {
            "connected": True,
            "total_commands": info.get("total_commands_processed", 0),
            "hits": info.get("keyspace_hits", 0),
            "misses": info.get("keyspace_misses", 0),
            "hit_rate_percent": round(
                info.get("keyspace_hits", 0) / max(info.get("total_commands_processed", 1), 1) * 100,
                2
            ),
            "cached_queries": db_keys,
            "memory_used_mb": round(memory.get("used_memory", 0) / 1024 / 1024, 2)
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}

@app.delete("/cache/clear")
async def clear_cache():
    """Clear all cached queries."""
    try:
        keys = redis_client.keys("db_query:*")
        if keys:
            redis_client.delete(*keys)
            logging.info(f"Cleared {len(keys)} cached queries")
            return {"cleared": len(keys)}
        return {"cleared": 0, "message": "No cached queries"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cache clear error: {str(e)}")
