from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from schemas import InsertPollutionDataRequest
from db import insert_data, fetch_data, init_db, close_db
import logging
import os
from typing import List, Optional
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
    level=logging.DEBUG,
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


def generate_cache_key(latitude: float, longitude: float, radius: float, layers: List[str]) -> str:
    """
    Generate unique cache key for query.
    
    Uses MD5 hash of sorted parameters to ensure:
    - Same query --> same key
    - Different order of layers --> same key
    
    Example: 
      (44.43, 26.10, 5, ['PM10', 'NO2']) --> 'query:a3f5c8d9e2b1...'
    
    Args:
        latitude: Query center latitude
        longitude: Query center longitude
        radius: Search radius in km
        layers: List of pollution layers
    
    Returns:
        Cache key string (e.g., 'query:abc123def456')
    """
    # Round coordinates to 4 decimals (~11m precision)
    key_data = f"{latitude:.4f},{longitude:.4f},{radius:.2f},{sorted(layers)}"
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


# Helper function
def get_coordinate_deltas(radius_km: float, latitude_deg: float):
    """
    Calculate latitude and longitude deltas for a given radius in km.
    
    Used to convert radius (km) to coordinate bounds for spatial queries.
    
    Args:
        radius_km: Search radius in kilometers
        latitude_deg: Center latitude in degrees
    
    Returns:
        (delta_lat, delta_lng): Coordinate deltas in degrees
        
    Math:
        - 1 degree latitude = 111.32 km everywhere
        - 1 degree longitude = 111.32 * cos(latitude) km (varies with latitude)
    """
    # Latitude: constant 111.32 km per degree
    delta_lat = radius_km / 111.32

    # Longitude: varies with latitude (narrower near poles)
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
        # Initialize pollution data dictionary
        pollution_data = {
            "PM10": None,
            "PM2.5": None,
            "NO2": None
        }

        # Map payload data to pollution_data dictionary
        for entry in payload.data:
            dimension = entry.dimension
            if dimension == "PM2_5":
                pollution_data["PM2.5"] = entry.value
            elif dimension in pollution_data:
                pollution_data[dimension] = entry.value

        # Prepare parameters for database insertion
        # Schema: sensor_id, timestamp, latitude, longitude, pm10, pm25, no2
        params = (
            payload.clientId,           # sensor_id
            payload.timestamp,          # timestamp
            payload.location.latitude,  # latitude
            payload.location.longitude, # longitude
            pollution_data["PM10"],     # pm10
            pollution_data["PM2.5"],    # pm25
            pollution_data["NO2"]       # no2
        )

        # Execute INSERT query
        insert_data(params)
        return {"success": True}

    except Exception as e:
        logging.error(f"Error adding data {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error adding data: {str(e)}")

# Endpoint (data retrieval) with redis caching
@app.get("/get_data/")
async def get_data(
    latitude: float = Query(...),
    longitude: float = Query(...),
    radius: float = Query(..., ge=0),
    layers: Optional[List[str]] = Query(None)
):
    """
    Retrieve pollution data within a geographic radius with Redis caching.
    
    Cache strategy:
    1. Generate cache key from parameters
    2. Check Redis for cached result
    3. If HIT: return cached data
    4. If MISS: query QuestDB, cache result, return
    
    Flow:
    1. Convert radius (km) to coordinate deltas
    2. Query QuestDB for readings within bounding box
    3. Return latest readings per grid cell (LATEST ON partition)
    
    Args:
        latitude: Center point latitude
        longitude: Center point longitude
        radius: Search radius in kilometers (float, >=0)
        layers: Optional list of pollution metrics to retrieve
                Default: All metrics (Temperature, PM10, etc.)
    
    Returns:
        List of sensor readings: [clientId, timestamp, lat, lon, ...pollution values]
        
    Raises:
        404: No data found in specified area
        500: Database query error
    
    Cache TTL: 5 minutes (300s)
    """
    # Default to all available pollution layers if none specified
    if not layers:
        layers = ["Temperature", "Humidity", "Pressure", "Altitude", "CO2", "PM1_0", "PM2_5", "PM10"]

    # Redis cache check
    cache_key = generate_cache_key(latitude, longitude, radius, layers)
    
    try:
        cached_result = redis_client.get(cache_key)
        if cached_result:
            logging.info(f"Cache HIT: {cache_key}")
            return json.loads(cached_result)
        else:
            logging.info(f"Cache MISS: {cache_key}")
    except Exception as e:
        # Redis error - continue without cache
        logging.warning(f"Redis error (continuing without cache): {e}")

    # Query database (Cache miss)
    try:
        # Convert radius to coordinate deltas
        delta_lat, delta_lng = get_coordinate_deltas(radius, latitude)
        
        # Prepare parameters for query
        params = (layers, latitude, delta_lat, longitude, delta_lng)
        
        # Execute SELECT query
        results = fetch_data(params)
        
        # Cache result
        try:
            redis_client.setex(
                cache_key,
                300,  # TTL in seconds
                json.dumps(results)
            )
            logging.info(f"Cached result: {cache_key}")
        except Exception as e:
            # Failed to cache - not critical, continue
            logging.warning(f"Failed to cache result: {e}")
        
        return results
        
    except HTTPException as http_exc:
        # Re-raise HTTP exceptions (404, etc.)
        logging.error(f"HTTP Exception: {http_exc}")
        raise http_exc
    except Exception as e:
        # Log and wrap unexpected errors
        logging.error(f"Error fetching data: {str(e)}")
        logging.exception(e)
        raise HTTPException(status_code=500, detail=f"Error fetching measurements: {str(e)}")


# Cache management endpoints (for debugging/monitoring)
@app.get("/cache/stats")
async def cache_stats():
    """
    Get Redis cache statistics.
    
    Returns metrics useful for monitoring cache performance:
    - Hit rate percentage
    - Number of cached keys
    - Memory usage
    """
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
    """
    Clear all cached queries.
    
    WARNING: Use with caution in production!
    Only clears keys with 'query:' prefix (safe for other Redis data).
    
    Returns:
        Number of keys cleared
    """
    try:
        # Only delete keys with 'query:' prefix
        keys = redis_client.keys("query:*")
        if keys:
            redis_client.delete(*keys)
            logging.info(f"Cleared {len(keys)} cached queries")
            return {"cleared": len(keys), "message": f"Cleared {len(keys)} cached queries"}
        return {"cleared": 0, "message": "No cached queries to clear"}
    except Exception as e:
        logging.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=f"Error clearing cache: {str(e)}")
