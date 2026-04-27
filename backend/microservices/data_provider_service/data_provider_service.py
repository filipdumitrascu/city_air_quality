from fastapi import HTTPException, FastAPI
from contextlib import asynccontextmanager
from prometheus_fastapi_instrumentator import Instrumentator
import logging
import os
import json
import asyncio
import redis
import hashlib

from database_service.client.database_service_client import get_data_from_database
from common.message_queue_googlepubsub.pubsub_client import PubSubClientSubscriber, PubSubClientPublisher


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

AVAILABLE_LAYERS = [
    "pm10", "pm2_5", "pm1_0",  # Particulate matter
    "no2", "co", "co2", "nh3", "vocs",  # Gases
    "temperature", "humidity", "pressure", "altitude"  # Weather
]


# Helper functions
def generate_cache_key(query_params: dict) -> str:
    """ Generate unique cache key from query parameters. """
    sensor_types = query_params.get('sensor_types', ['SPO-RO', 'CityAirQ', 'WearAware'])
    if sensor_types:
        sensor_types = sorted(sensor_types)
    else:
        sensor_types = ['SPO-RO', 'CityAirQ', 'WearAware']
    
    layers = query_params.get('layers') or []
    
    key_data = json.dumps({
        'latitude': round(query_params.get('latitude', 0), 4),
        'longitude': round(query_params.get('longitude', 0), 4),
        'radius': query_params.get('radius', 0),
        'layers': sorted(layers) if layers else 'all',
        'sensor_types': sensor_types
    }, sort_keys=True)
    
    hash_hex = hashlib.md5(key_data.encode()).hexdigest()
    return f"provider_query:{hash_hex}"


# PubSub message handler
async def process_message(message):
    """
    Process incoming query requests from PubSub with Redis caching.
    
    Cache strategy:
    - Cache HIT: return cached result (~5ms)
    - Cache MISS: query Database Service, cache result, return (~150ms)
    - Cache TTL: 4 minutes
    
    Args:
        message: PubSub message containing query parameters
                 (latitude, longitude, radius, layers, sensor_types)
    """
    try:
        # Decode query parameters from message
        decoded_message = json.loads(message.data.decode("utf-8"))
        logging.info(f"Received query: lat={decoded_message.get('latitude')}, "
                     f"lon={decoded_message.get('longitude')}, "
                     f"radius={decoded_message.get('radius')}")

        # Acknowledge message to PubSub
        message.ack()

        # Handle layer selection - default to all if not specified
        selected_layers = decoded_message.get("layers")
        if not selected_layers:
            selected_layers = AVAILABLE_LAYERS
        decoded_message["layers"] = selected_layers

        # Handle sensor_types - default to CityAirQ, WearAware if not specified
        sensor_types = decoded_message.get("sensor_types")
        if not sensor_types:
            sensor_types = ["CityAirQ", "WearAware"]
        decoded_message["sensor_types"] = sensor_types

        # Redis cache check
        cache_key = generate_cache_key(decoded_message)

        try:
            cached_result = redis_client.get(cache_key)
            if cached_result:
                logging.info(f"Cache HIT: {cache_key}")

                # Publish cached result directly
                PubSubClientPublisher.publish_message("results_response_messages", cached_result)
                return
            logging.info(f"Cache MISS: {cache_key}")
        except Exception as e:
            logging.warning(f"Redis error (continuing without cache): {e}")

        # Query database (Cache miss)
        try:
            response = await get_data_from_database(decoded_message)

            # Cache result
            try:
                redis_client.setex(cache_key, 240, response)
                logging.info(f"Cached result: {cache_key} (TTL: 240s)")
            except Exception as e:
                logging.warning(f"Failed to cache result: {e}")

            # Publish response back to Client Message Handler
            PubSubClientPublisher.publish_message("results_response_messages", response)
            logging.info("Response published to results_response_messages")

        except HTTPException as e:
            logging.error(f"Database error: {e.detail}")
            PubSubClientPublisher.publish_message("results_response_messages", {
                "error": e.detail, 
                "status_code": e.status_code
            })

    except Exception as e:
        logging.error(f"Error processing message: {str(e)}")
        message.nack()

# PubSub subscriber
results_subscriber = PubSubClientSubscriber("results_service_messages-sub", process_message)


# FASTAPI APPLICATION
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - start subscriber on startup."""
    asyncio.create_task(results_subscriber.start_subscriber())
    logging.info("PubSub subscriber started for 'results_service_messages-sub'")
    
    try:
        redis_client.ping()
        logging.info(f"Redis connected at {os.getenv('REDIS_HOST', 'redis-service')}:6379")
    except Exception as e:
        logging.warning(f"Redis unavailable (caching disabled): {e}")
    
    yield
    
    results_subscriber.stop()
    logging.info("Data Provider Service shutting down")

app = FastAPI(
    title="Data Provider Service",
    description="Query handler for pollution data with Redis caching",
    version="2.0.0",
    lifespan=lifespan
)

# Prometheus metrics
Instrumentator().instrument(app).expose(app)


# HEALTH ENDPOINTS
@app.get("/")
async def root():
    return {
        "service": "data_provider_service",
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
        "service": "data_provider_service",
        "redis": "connected" if redis_ok else "disconnected"
    }


# CACHE ENDPOINTS
@app.get("/cache/stats")
async def cache_stats():
    """Get Redis cache statistics."""
    try:
        info = redis_client.info("stats")
        provider_keys = len(redis_client.keys("provider_query:*"))
        
        return {
            "connected": True,
            "total_commands": info.get("total_commands_processed", 0),
            "hits": info.get("keyspace_hits", 0),
            "misses": info.get("keyspace_misses", 0),
            "hit_rate_percent": round(
                info.get("keyspace_hits", 0) / max(info.get("total_commands_processed", 1), 1) * 100,
                2
            ),
            "cached_queries": provider_keys
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}

@app.delete("/cache/clear")
async def clear_cache():
    """Clear all cached queries."""
    try:
        keys = redis_client.keys("provider_query:*")
        if keys:
            redis_client.delete(*keys)
            logging.info(f"Cleared {len(keys)} cached queries")
            return {"cleared": len(keys)}
        return {"cleared": 0, "message": "No cached queries"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cache clear error: {str(e)}")
