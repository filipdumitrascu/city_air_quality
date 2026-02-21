from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from schemas import InsertPollutionDataRequest
from db import insert_data, fetch_data, init_db, close_db
import logging
import os
from typing import List, Optional
from prometheus_fastapi_instrumentator import Instrumentator
import math
import redis
import json
import hashlib


# Connect to Redis for query result caching
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'redis'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    db=int(os.getenv('REDIS_DB', 0)),
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5
)


# Configure file-based logging for Database Service
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)

log_file = os.path.join(log_dir, 'database_service.log')
if not os.path.exists(log_file):
    open(log_file, 'w').close()

logging.basicConfig(
    level=logging.INFO,
    filename=log_file,
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s'
)


# Test Redis connection at startup
try:
    redis_client.ping()
    logging.info(f"Redis connected at {os.getenv('REDIS_HOST', 'redis')}:6379")
except Exception as e:
    logging.warning(f"Redis unavailable (caching disabled): {e}")


def generate_cache_key(latitude: float, longitude: float, radius: float, layers: List[str], sensor_types: List[str] = None) -> str:
    """
    Generate unique cache key for query.
    
    Args:
        latitude: Query center latitude
        longitude: Query center longitude
        radius: Search radius in km
        layers: List of pollution layers
        sensor_types: List of sensor types to filter
    
    Returns:
        Cache key string
    """
    sensor_types_str = sorted(sensor_types) if sensor_types else ['fixed', 'mobile']
    key_data = f"{latitude:.4f},{longitude:.4f},{radius:.2f},{sorted(layers)},{sensor_types_str}"
    hash_hex = hashlib.md5(key_data.encode()).hexdigest()
    return f"query:{hash_hex}"


# Fast API
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Initialize database connection pool on startup.
    Close all connections on shutdown.
    """
    try:
        init_db()
        logging.info("Database connection initialized")
    except Exception as e:
        logging.error(f"Database NOT available at startup: {e}")
    
    yield  # App runs here
    
    try:
        close_db()
        logging.info("Database connections closed")
    except Exception:
        pass

app = FastAPI(
    title="Database Service API",
    description="Microservice that communicates with QuestDB",
    lifespan=lifespan,
    version="1.0.0"
)

# Prometheus metrics for monitoring
Instrumentator().instrument(app).expose(app)

# Helper function
def get_coordinate_deltas(radius_km: float, latitude_deg: float):
    """
    Calculate latitude and longitude deltas for a given radius in km.
    """
    delta_lat = radius_km / 111.32
    lat_rad = math.radians(latitude_deg)
    km_per_deg_lng = 111.32 * math.cos(lat_rad)
    delta_lng = radius_km / km_per_deg_lng
    return delta_lat, delta_lng


# Health check endpoints
@app.get("/")
async def root():
    """Root endpoint"""
    return {"service": "database_service", "status": "running"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "database_service"}


# Endpoint (data insertion)
@app.post("/add_data/")
async def add_data(payload: InsertPollutionDataRequest):
    try:
        pollution_data = {
            "PM10": None,
            "PM2.5": None,
            "NO2": None
        }

        for entry in payload.data:
            dimension = entry.dimension
            if dimension == "PM2_5":
                pollution_data["PM2.5"] = entry.value
            elif dimension in pollution_data:
                pollution_data[dimension] = entry.value

        params = (
            payload.clientId,
            payload.timestamp,
            payload.location.latitude,
            payload.location.longitude,
            pollution_data["PM10"],
            pollution_data["PM2.5"],
            pollution_data["NO2"]
        )

        insert_data(params)
        return {"success": True}

    except Exception as e:
        logging.error(f"Error adding data {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error adding data: {str(e)}")


# Endpoint (data retrieval) with redis caching and sensor_types filter
@app.get("/get_data/")
async def get_data(
    latitude: float = Query(...),
    longitude: float = Query(...),
    radius: float = Query(..., ge=0),
    layers: Optional[List[str]] = Query(None),
    sensor_types: Optional[List[str]] = Query(None)
):
    """
    Retrieve pollution data within a geographic radius with Redis caching.
    
    Args:
        latitude: Center point latitude
        longitude: Center point longitude
        radius: Search radius in kilometers
        layers: Optional list of pollution metrics to retrieve
        sensor_types: Optional list of sensor types to filter ('fixed', 'mobile')
    
    Returns:
        List of sensor readings
    """
    if not layers:
        layers = ["Temperature", "Humidity", "Pressure", "Altitude", "CO2", "PM1_0", "PM2_5", "PM10"]
    
    # Default to both sensor types if not specified
    if not sensor_types:
        sensor_types = ["fixed", "mobile"]

    # Redis cache check
    cache_key = generate_cache_key(latitude, longitude, radius, layers, sensor_types)
    
    try:
        cached_result = redis_client.get(cache_key)
        if cached_result:
            logging.info(f"Cache HIT: {cache_key}")
            return json.loads(cached_result)
        else:
            logging.info(f"Cache MISS: {cache_key}")
    except Exception as e:
        logging.warning(f"Redis error (continuing without cache): {e}")

    # Query database (Cache miss)
    try:
        delta_lat, delta_lng = get_coordinate_deltas(radius, latitude)
        
        # Pass sensor_types to fetch_data
        params = (layers, latitude, delta_lat, longitude, delta_lng, sensor_types)
        
        results = fetch_data(params)
        
        # Cache result
        try:
            redis_client.setex(
                cache_key,
                300,
                json.dumps(results)
            )
            logging.info(f"Cached result: {cache_key}")
        except Exception as e:
            logging.warning(f"Failed to cache result: {e}")
        
        return results
        
    except HTTPException as http_exc:
        logging.error(f"HTTP Exception: {http_exc}")
        raise http_exc
    except Exception as e:
        logging.error(f"Error fetching data: {str(e)}")
        logging.exception(e)
        raise HTTPException(status_code=500, detail=f"Error fetching measurements: {str(e)}")


# Cache management endpoints
@app.get("/cache/stats")
async def cache_stats():
    """Get Redis cache statistics."""
    try:
        info = redis_client.info("stats")
        keyspace = redis_client.info("keyspace")
        memory = redis_client.info("memory")
        
        total_commands = info.get("total_commands_processed", 0)
        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        
        return {
            "connected": True,
            "total_commands": total_commands,
            "hits": hits,
            "misses": misses,
            "hit_rate_percent": round((hits / max(total_commands, 1)) * 100, 2),
            "cached_keys": keyspace.get("db0", {}).get("keys", 0) if "db0" in keyspace else 0,
            "memory_used_mb": round(memory["used_memory"] / 1024 / 1024, 2),
            "memory_peak_mb": round(memory.get("used_memory_peak", 0) / 1024 / 1024, 2)
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}

@app.delete("/cache/clear")
async def clear_cache():
    """Clear all cached queries."""
    try:
        keys = redis_client.keys("query:*")
        if keys:
            redis_client.delete(*keys)
            logging.info(f"Cleared {len(keys)} cached queries")
            return {"cleared": len(keys), "message": f"Cleared {len(keys)} cached queries"}
        return {"cleared": 0, "message": "No cached queries to clear"}
    except Exception as e:
        logging.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=f"Error clearing cache: {str(e)}")
