from fastapi import HTTPException
from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio
import logging
import os
import json
import redis
import hashlib


# Connect to Redis for caching query results
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'redis'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    db=int(os.getenv('REDIS_DB', 0)),
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5
)


# Configure file-based logging for Data Provider Service
logging.basicConfig(
    level=logging.INFO,
    filename=os.path.join('logs', 'data_provider_service.log'),
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s'
)


# Test Redis connection at startup
try:
    redis_client.ping()
    logging.info(f"Redis connected at {os.getenv('REDIS_HOST', 'redis')}:6379")
except Exception as e:
    logging.warning(f"Redis unavailable (caching disabled): {e}")


# Import dependencies
from database_service.client.database_service_client import get_data_from_database
from pubsub.message_queue_googlepubsub.pubsub_client import PubSubClientSubscriber, PubSubClientPublisher


def generate_cache_key(query_params: dict) -> str:
    """
    Generate unique cache key from query parameters.
    
    Args:
        query_params: Query dict with latitude, longitude, radius, layers
    
    Returns:
        Cache key string (e.g., 'provider_query:abc123')
    """
    # Sort parameters for consistent keys
    key_data = json.dumps({
        'latitude': round(query_params.get('latitude', 0), 4),
        'longitude': round(query_params.get('longitude', 0), 4),
        'radius': query_params.get('radius', 0),
        'layers': sorted(query_params.get('layers', []))
    }, sort_keys=True)
    
    hash_hex = hashlib.md5(key_data.encode()).hexdigest()
    return f"provider_query:{hash_hex}"


# Subscribe to query requests from Client Message Handler
subscription_name = "results_service_messages-sub"


async def process_message(message):
    """
    Process incoming query requests from PubSub with Redis caching.
    
    Cache strategy:
    1. Generate cache key from query parameters
    2. Check Redis for cached result
    3. If HIT: publish cached response (~5ms)
    4. If MISS: query Database Service, cache result, publish (~150ms)
    
    Flow:
    1. Client Message Handler publishes query to 'results_service_messages'
    2. This subscriber receives the message
    3. Check Redis cache
    4. If miss: Query Database Service for pollution data
    5. Cache result in Redis
    6. Publish response to 'results_response_messages'
    7. Client Message Handler picks up response and returns to client
    
    Args:
        message: PubSub message containing query parameters
                 (latitude, longitude, radius, layers)
    
    Cache TTL: 4 minutes
    """
    try:
        # Decode query parameters from message
        decoded_message = json.loads(message.data.decode("utf-8"))
        logging.info(f"Received message: {decoded_message}")
        
        # Acknowledge message to PubSub (won't be redelivered)
        message.ack()

        # Handle layer selection
        # If no specific layers requested, query all available pollution metrics
        available_layers = ["Temperature", "Humidity", "Pressure", "Altitude", "CO2", "PM1_0", "PM2_5", "PM10"]
        selected_layers = decoded_message["layers"] if decoded_message["layers"] else available_layers
        decoded_message["layers"] = selected_layers

        # Redis cache check
        cache_key = generate_cache_key(decoded_message)
        
        try:
            cached_result = redis_client.get(cache_key)
            if cached_result:
                logging.info(f"Cache HIT: {cache_key}")
                # Publish cached result directly
                PubSubClientPublisher.publish_message("results_response_messages", cached_result)
                return
            else:
                logging.info(f"Cache MISS: {cache_key}")
        except Exception as e:
            logging.warning(f"Redis error (continuing without cache): {e}")

        # Query database (Cache miss)
        try:
            # Query Database Service for pollution data
            # Returns list of sensor readings matching location/radius criteria
            response = await get_data_from_database(decoded_message)
            
            # Cache result
            try:
                redis_client.setex(
                    cache_key,
                    240,  # TTL in seconds
                    response
                )
                logging.info(f" Cached result: {cache_key} (TTL: 240s)")
            except Exception as e:
                logging.warning(f"Failed to cache result: {e}")
            
            # Publish successful response back to Client Message Handler
            PubSubClientPublisher.publish_message("results_response_messages", response)
            
        except HTTPException as e:
            # Database Service returned error (404 not found, 500 server error, etc.)
            logging.error(f"Error receiving response from database: {e.detail}")
            
            # Publish error response so Client Message Handler can inform user
            PubSubClientPublisher.publish_message("results_response_messages", {
                "error": e.detail, 
                "status_code": e.status_code
            })
            
    except Exception as e:
        # Unexpected error processing message
        logging.error(f"Error processing message: {str(e)}")
        
        # Negative acknowledge - message will be redelivered
        message.nack()


# Create subscriber that listens for query requests
results_subscriber = PubSubClientSubscriber(subscription_name, process_message)


# Fast API
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI app.
    Starts PubSub subscriber as background task on app startup.
    """
    # Startup - start listening for query requests
    asyncio.create_task(results_subscriber.start_subscriber())
    logging.info("Subscriber started and listening for messages on 'results_service_messages-sub'.")
    
    yield  # App runs here
    
    # Shutdown
    logging.info("Shutting down Data Provider Service...")


app = FastAPI(
    title="Data Provider Service API",
    description="Receives requests and returns data",
    lifespan=lifespan,
    version="1.0.0"
)


# Cache management endpoints (for debugging/monitoring)
@app.get("/cache/stats")
async def cache_stats():
    """Get Redis cache statistics for Data Provider Service"""
    try:
        info = redis_client.info("stats")
        
        # Count only provider_query:* keys
        provider_keys = len(redis_client.keys("provider_query:*"))
        
        return {
            "connected": True,
            "total_commands": info.get("total_commands_processed", 0),
            "hits": info.get("keyspace_hits", 0),
            "misses": info.get("keyspace_misses", 0),
            "hit_rate_percent": round(
                (info.get("keyspace_hits", 0) / max(info.get("total_commands_processed", 1), 1)) * 100, 
                2
            ),
            "cached_provider_queries": provider_keys
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}

@app.delete("/cache/clear")
async def clear_cache():
    """Clear cached queries for Data Provider Service"""
    try:
        keys = redis_client.keys("provider_query:*")
        if keys:
            redis_client.delete(*keys)
            logging.info(f" Cleared {len(keys)} cached provider queries")
            return {"cleared": len(keys)}
        return {"cleared": 0, "message": "No cached queries to clear"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing cache: {str(e)}")


# NOTE: Service Communication
# This service operates primarily through PubSub messaging:
# - Input: 'results_service_messages' topic
# - Output: 'results_response_messages' topic
#
# HTTP endpoints (/cache/stats, /cache/clear) are for monitoring only
