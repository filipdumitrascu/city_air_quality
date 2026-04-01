"""
Client Message Handler - API Gateway for CityAirQ

Main entry point for all client requests. Routes to appropriate services:
- /ingest/ -> Ingest Service (via PubSub) - REQUIRES AUTH
- /results/ -> Data Provider Service (via PubSub) - No auth required
- /route/ -> Routing Service (via HTTP) - No auth required
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from prometheus_fastapi_instrumentator import Instrumentator
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, field_validator
import logging
import os
import time
import json
import asyncio
import hashlib
from queue import Queue

import redis
import httpx

from common.message_queue_googlepubsub.pubsub_client import PubSubClientPublisher, PubSubClientSubscriber
from common.authentification_service.auth import authorize


# Redis connection for caching
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'redis-service'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    db=int(os.getenv('REDIS_DB', 0)),
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5
)

# Logging to stdout only (visible via kubectl logs)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# REQUEST MODELS (matching pollution_data schema)
# Romania timezone offset (GMT+3 during summer, GMT+2 during winter)
ROMANIA_OFFSET_MS = 3 * 60 * 60 * 1000  # 3 hours in milliseconds

def get_current_timestamp_ms() -> int:
    """Get current Unix timestamp in milliseconds, adjusted for Romania (GMT+3)."""
    import time
    return int(time.time() * 1000) + ROMANIA_OFFSET_MS


class IngestPayload(BaseModel):
    """
    Payload for ingesting sensor data into pollution_data table.
    
    sensor_type values:
      - CityAirQ   (mobile)
      - WearAware  (mobile)
      - SPO-RO     (fixed, EEA stations)
      - Forecast   (predicted, ML)
    
    Required: sensor_type, latitude, longitude
    Optional: sensor_id (None for Forecast), timestamp (default: current time)
    """
    # Required fields
    sensor_type: Literal["CityAirQ", "WearAware", "SPO-RO", "Forecast"] = Field(
        ..., description="Sensor type: CityAirQ, WearAware, SPO-RO, or Forecast"
    )
    sensor_id: Optional[str] = Field(
        default=None, description="Sensor identifier (e.g., '001'). None for Forecast."
    )
    timestamp: Optional[int] = Field(
        default=None, description="Unix timestamp in milliseconds. Default: current time."
    )
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    
    # Optional - Weather data (BME680 sensor)
    altitude: Optional[float] = Field(default=-1, description="Altitude in meters")
    humidity: Optional[float] = Field(default=-1, description="Relative humidity %")
    pressure: Optional[float] = Field(default=-1, description="Atmospheric pressure hPa")
    temperature: Optional[float] = Field(default=-1, description="Temperature in Celsius")
    
    # Optional - Gas sensors
    co: Optional[float] = Field(default=-1, description="Carbon monoxide (MICS sensor)")
    co2: Optional[float] = Field(default=-1, description="Carbon dioxide (MHZ19/STCC44)")
    no2: Optional[float] = Field(default=-1, description="Nitrogen dioxide (MICS sensor)")
    nh3: Optional[float] = Field(default=-1, description="Ammonia (MICS sensor)")
    vocs: Optional[float] = Field(default=-1, description="Volatile organic compounds (BME680)")
    
    # Optional - Particulate matter (PM sensor / BMV080)
    pm1_0: Optional[float] = Field(default=-1, description="PM1.0 concentration ug/m3")
    pm2_5: Optional[float] = Field(default=-1, description="PM2.5 concentration ug/m3")
    pm10: Optional[float] = Field(default=-1, description="PM10 concentration ug/m3")
    
    # Convert None values to -1 for optional numeric fields
    @field_validator('altitude', 'humidity', 'pressure', 'temperature', 
                     'co', 'co2', 'no2', 'nh3', 'vocs', 'pm1_0', 'pm2_5', 'pm10', 
                     mode='before')
    @classmethod
    def none_to_default(cls, v):
        return -1 if v is None else v


class ResultsPayload(BaseModel):
    """
    Payload for querying pollution data.
    
    Required: latitude, longitude, radius
    Optional: sensor_types (default: mobile), layers (default: all)
    """
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius: float = Field(..., gt=0, description="Search radius in km")
    sensor_types: Optional[List[str]] = Field(
        default=["CityAirQ", "WearAware"],
        description="'CityAirQ', 'WearAware', 'SPO-RO', 'Forecast'"
    )
    layers: Optional[List[str]] = Field(
        default=None,
        description="Pollutant layers to return: 'pm10', 'pm2_5', 'no2', etc. None = all"
    )


class RoutePayload(BaseModel):
    """
    Payload for route calculation.
    
    Required: start, goal (each with lat, lon)
    Optional: alpha (default: 1 = cleanest), transport_mode (default: bicycle)
    """
    start: dict = Field(..., description="Start point: {lat, lon}")
    goal: dict = Field(..., description="Goal point: {lat, lon}")
    alpha: float = Field(default=1, ge=0, le=1, description="0=shortest, 1=cleanest")
    sensor_types: Optional[List[str]] = Field(
        default=["CityAirQ", "WearAware", "SPO-RO", "Forecast"],
        description="'CityAirQ', 'WearAware', 'SPO-RO' or Forecast"
    )
    transport_mode: str = Field(default="bicycle", description="'foot' or 'bicycle'")
    heuristic: str = Field(default="haversine", description="A* heuristic for foot mode")


# HELPER FUNCTIONS
def generate_cache_key(payload: dict) -> str:
    """Generate unique cache key from query payload."""
    sensor_types = payload.get('sensor_types', ['CityAirQ', 'WearAware', 'SPO-RO', 'Forecast'])
    if sensor_types:
        sensor_types = sorted(sensor_types)
    else:
        sensor_types = ['CityAirQ', 'WearAware', 'SPO-RO', 'Forecast']
    
    layers = payload.get('layers') or []
    
    key_data = json.dumps({
        'latitude': round(payload.get('latitude', 0), 4),
        'longitude': round(payload.get('longitude', 0), 4),
        'radius': payload.get('radius', 0),
        'layers': sorted(layers) if layers else 'all',
        'sensor_types': sensor_types
    }, sort_keys=True)
    
    hash_hex = hashlib.md5(key_data.encode()).hexdigest()
    return f"client_query:{hash_hex}"

# Response queue for PubSub request-response pattern
response_queue = Queue()

async def process_results_message(message):
    """Callback for results response from Data Provider Service."""
    try:
        response_data = json.loads(message.data.decode("utf-8"))
        response_queue.put(response_data)
        message.ack()
        logging.info("Received response from Data Provider Service")
    except Exception as e:
        logging.error(f"Error processing message: {str(e)}")
        message.nack()

# PubSub subscriber for results responses
results_subscriber = PubSubClientSubscriber("results_response_messages-sub", process_results_message)


# FASTAPI APPLICATION
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - start subscriber on startup."""
    asyncio.create_task(results_subscriber.start_subscriber())
    logging.info("PubSub subscriber started for 'results_response_messages-sub'")
    
    try:
        redis_client.ping()
        logging.info(f"Redis connected at {os.getenv('REDIS_HOST', 'redis-service')}:6379")
    except Exception as e:
        logging.warning(f"Redis unavailable (caching disabled): {e}")
    
    yield
    
    results_subscriber.stop()
    logging.info("Client Message Handler shutting down")

app = FastAPI(
    title="CityAirQ API Gateway",
    description="API Gateway for pollution monitoring and routing services",
    version="2.0.0",
    lifespan=lifespan
)

# Prometheus metrics
Instrumentator().instrument(app).expose(app)


# HEALTH ENDPOINTS
@app.get("/")
async def root():
    return {
        "service": "client_message_handler",
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
        "service": "client_message_handler",
        "redis": "connected" if redis_ok else "disconnected"
    }


# INGEST ENDPOINT
@app.post("/ingest/")
async def ingest_data(
    payload: IngestPayload,
    user: dict = Depends(authorize)
):
    """
    Ingest sensor data into the database.
    
    Accepts data from CityAirQ, WearAware, SPO-RO, and Forecast sensors.
    If timestamp is not provided, current time is used.
    Authentication: REQUIRED (Google OAuth or API key)
    """
    try:
        data = payload.model_dump()
        
        # Set timestamp to current time if not provided
        if data.get('timestamp') is None:
            data['timestamp'] = get_current_timestamp_ms()
            logging.info(f"Using current timestamp: {data['timestamp']}")
        
        data['submitted_by'] = user.get('email')
        
        PubSubClientPublisher.publish_message("ingest_service_messages", data)
        logging.info(f"Ingest from {user.get('email')} for {payload.sensor_type}/{payload.sensor_id}")

        return JSONResponse(
            status_code=200,
            content={
                "message": "Data accepted for processing",
                "sensor_type": payload.sensor_type,
                "sensor_id": payload.sensor_id,
                "timestamp": data['timestamp']
            }
        )
    except Exception as e:
        logging.error(f"Ingest error: {str(e)}")
        raise HTTPException(
            status_code=400, 
            detail=f"Failed to process ingest request: {str(e)}"
        )


# RESULTS ENDPOINT
@app.post("/results/")
async def get_results(payload: ResultsPayload):
    """
    Query pollution data within a geographic area.
    
    Returns sensor readings matching the location, radius, and filters.
    Results are cached in Redis for 3 minutes.
    Authentication: Not required
    """
    query = payload.model_dump()
    cache_key = generate_cache_key(query)
    
    # Check cache
    try:
        cached_result = redis_client.get(cache_key)
        if cached_result:
            logging.info(f"Cache HIT: {cache_key}")
            return {"data": json.loads(cached_result), "cached": True}
        logging.info(f"Cache MISS: {cache_key}")
    except Exception as e:
        logging.warning(f"Redis error: {e}")
    
    # Query via PubSub
    try:
        PubSubClientPublisher.publish_message("results_service_messages", query)
        logging.info("Results query published, waiting for response...")
        
        start_time = time.time()
        while response_queue.empty():
            if time.time() - start_time > 30:
                raise HTTPException(
                    status_code=408, 
                    detail="Timeout waiting for response from Data Provider Service"
                )
            await asyncio.sleep(0.5)
        
        response_data = response_queue.get_nowait()
        
        if "error" in response_data:
            error_msg = response_data.get("error", "Unknown error")
            logging.error(f"Data Provider error: {error_msg}")
            raise HTTPException(status_code=500, detail=str(error_msg))
        
        if isinstance(response_data, str):
            response_data = json.loads(response_data)
        
        # Cache result
        try:
            redis_client.setex(cache_key, 180, json.dumps(response_data))
            logging.info(f"Cached result: {cache_key} (TTL: 180s)")
        except Exception as e:
            logging.warning(f"Failed to cache: {e}")
        
        return {"data": response_data, "cached": False}
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Results query error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# ROUTE ENDPOINT
@app.post("/route/")
async def calculate_route(payload: RoutePayload):
    """
    Calculate pollution-aware route between two points.
    
    Forwards request to Routing Service (A* algorithm with pollution weighting).
    Authentication: Not required
    """
    routing_service_url = os.getenv('ROUTING_SERVICE_URL', 'http://routing-service:8000')
    
    try:
        route_request = payload.model_dump()
        logging.info(f"Route request: {route_request['start']} -> {route_request['goal']}")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{routing_service_url}/route",
                json=route_request
            )
        
        if response.status_code == 200:
            logging.info("Route calculated successfully")
            return response.json()
        else:
            error_detail = response.text
            logging.error(f"Routing Service error: {error_detail}")
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Routing Service error: {error_detail}"
            )
            
    except httpx.TimeoutException:
        logging.error("Routing Service timeout")
        raise HTTPException(status_code=504, detail="Routing Service timeout")
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Route calculation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# CACHE MANAGEMENT ENDPOINTS
@app.get("/cache/stats")
async def cache_stats():
    try:
        info = redis_client.info("stats")
        client_keys = len(redis_client.keys("client_query:*"))
        
        return {
            "connected": True,
            "total_commands": info.get("total_commands_processed", 0),
            "hits": info.get("keyspace_hits", 0),
            "misses": info.get("keyspace_misses", 0),
            "hit_rate_percent": round(
                info.get("keyspace_hits", 0) / max(info.get("total_commands_processed", 1), 1) * 100,
                2
            ),
            "cached_queries": client_keys
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}


@app.delete("/cache/clear")
async def clear_cache():
    try:
        keys = redis_client.keys("client_query:*")
        if keys:
            redis_client.delete(*keys)
            logging.info(f"Cleared {len(keys)} cached queries")
            return {"cleared": len(keys)}
        return {"cleared": 0, "message": "No cached queries"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cache clear error: {str(e)}")
