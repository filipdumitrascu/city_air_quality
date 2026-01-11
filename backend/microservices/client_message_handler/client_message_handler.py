from fastapi import FastAPI, HTTPException
import logging
import os
import time
import json
import asyncio
import hashlib
from fastapi import Header
from fastapi.responses import JSONResponse
from queue import Queue
from fastapi import Request
from prometheus_fastapi_instrumentator import Instrumentator
from contextlib import asynccontextmanager

from pubsub.message_queue_googlepubsub.pubsub_client import PubSubClientPublisher, PubSubClientSubscriber
from pubsub.authentification_service.auth import authorize

import redis
import httpx

# Connect to Redis for caching query results
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'redis'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    db=int(os.getenv('REDIS_DB', 0)),
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5
)


# Create logs directory and configure file-based logging
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)

log_file = os.path.join(log_dir, 'client_message_handler.log')
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


def generate_cache_key(payload: dict) -> str:
    """
    Generate unique cache key from query payload.
    
    Args:
        payload: Query parameters (latitude, longitude, radius, layers)
    
    Returns:
        Cache key string (e.g., 'client_query:abc123')
    """
    # Extract and sort parameters for consistent keys
    key_data = json.dumps({
        'latitude': round(payload.get('latitude', 0), 4),
        'longitude': round(payload.get('longitude', 0), 4),
        'radius': payload.get('radius', 0),
        'layers': sorted(payload.get('layers', []))
    }, sort_keys=True)
    
    hash_hex = hashlib.md5(key_data.encode()).hexdigest()
    return f"client_query:{hash_hex}"


# Queue to temporarily store responses from data provider service
# Works as a bridge between PubSub subscriber and HTTP response
response_queue = Queue()


async def process_results_message(message):
    """
    Callback function triggered when a message arrives from PubSub.
    
    Flow:
    1. Data Provider Service queries database
    2. Data Provider publishes response to 'results_response_messages' topic
    3. This subscriber receives the message
    4. Message is placed in response_queue
    5. /results/ endpoint retrieves it from queue and returns to client
    """
    try:
        # Decode message payload
        response_data = json.loads(message.data.decode("utf-8"))
        
        # Put response in queue (consumed by /results/ endpoint)
        response_queue.put(response_data)
        
        # Acknowledge message to PubSub (won't be redelivered)
        message.ack()
        
        logging.info(f"Received response from message queue: {response_data}")
    except Exception as e:
        logging.error(f"Error processing message: {str(e)}")
        # Negative acknowledge - message will be redelivered
        message.nack()


# Subscribe to 'results_response_messages-sub' topic
# This listens for responses from Data Provider Service
results_subscriber = PubSubClientSubscriber("results_response_messages-sub", process_results_message)


# Fast API
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI app.
    Starts PubSub subscriber as background task on app startup.
    """
    # Start subscriber in background (runs continuously)
    asyncio.create_task(results_subscriber.start_subscriber())
    logging.info("Subscriber started and listening for messages on 'results_response_messages-sub'.")
    
    yield  # App runs here
    
    # Shutdown
    logging.info("Shutting down...")

app = FastAPI(
    title="Client Message Handler API",
    description="Handles requests to enter pollution information or read existing data",
    lifespan=lifespan,
    version="1.0.0"
)


# Health check endpoints
@app.get("/")
async def root():
    """Root endpoint"""
    return {"service": "client_message_handler", "status": "running"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "client_message_handler"}



# Prometheus metrics for monitoring
Instrumentator().instrument(app).expose(app)


# Endpoint ingest
@app.post("/ingest/")
async def ingest_data(payload: dict, x_auth_token: str = Header(None)):
    """
    Publish sensor data to Ingest Service via PubSub.
    
    Flow:
    1. Client sends pollution data (sensor_id, location, readings)
    2. Publishes to 'ingest_service_messages' topic
    3. Ingest Service picks it up and stores in database
    4. Returns immediate success (async fire-and-forget)
    
    Args:
        payload: Sensor data (sensor_id, timestamp, location, measurements)
        x_auth_token: Authentication token
    
    Returns:
        200: Success message
        400: Error publishing to PubSub
    """
    # await authorize(x_auth_token)

    try:
        # Publish message to PubSub topic (async, non-blocking)
        PubSubClientPublisher.publish_message("ingest_service_messages", payload)
        logging.info("The request was sent to ingest service")

        return JSONResponse(
            status_code=200,
            content={"details": "Data successfully added in the database"},
        )
    except Exception as e:
        logging.error(f"{str(e)}")
        raise HTTPException(
            status_code=400, 
            detail=f"Error while sending the request into the message queue"
        )

# Endpoint results with redis caching
@app.post("/results/")
async def get_data(payload: dict, x_auth_token: str = Header(None)):
    """
    Query pollution data via PubSub request-response pattern with Redis caching.
    
    Cache strategy:
    1. Generate cache key from query parameters
    2. Check Redis for cached result
    3. If HIT: return cached data immediately
    4. If MISS: query via PubSub, cache result, return
    
    Flow:
    1. Client sends query (location, radius, pollution layers)
    2. Publishes to 'results_service_messages' topic
    3. Data Provider Service receives message
    4. Data Provider queries database
    5. Data Provider publishes response to 'results_response_messages'
    6. Subscriber (process_results_message) puts response in queue
    7. This endpoint polls queue and returns data to client
    
    Args:
        payload: Query parameters (latitude, longitude, radius, layers)
        x_auth_token: Authentication token
    
    Returns:
        200: Query results
        404: Error from data provider
        408: Timeout (no response within 30 seconds)
        500: Internal server error

    Cache TTL: 3 minutes
    """
    # await authorize(x_auth_token)
    
    # Redis cache check
    cache_key = generate_cache_key(payload)
    
    try:
        cached_result = redis_client.get(cache_key)
        if cached_result:
            logging.info(f" Cache HIT: {cache_key}")
            return {"data": json.loads(cached_result), "cached": True}
        else:
            logging.info(f"✗ Cache MISS: {cache_key}")
    except Exception as e:
        # Redis error - continue without cache
        logging.warning(f"Redis error (continuing without cache): {e}")
    
    # Pubsub queery (Cache miss)
    try:
        # Publish query request to PubSub
        PubSubClientPublisher.publish_message("results_service_messages", payload)
        logging.info("The request was published in the queue and waiting for response....")
        
        # Poll response_queue for up to 30 seconds
        start_time = time.time()
        while response_queue.empty():
            if time.time() - start_time > 30:
                raise HTTPException(
                    status_code=408, 
                    detail="Timeout waiting for response from results service"
                )
            # Sleep to avoid busy-waiting
            await asyncio.sleep(1)
        
        # Response arrived - retrieve from queue
        response_data = response_queue.get_nowait()
        logging.info(f"Received response: {response_data}")
        
        # Check if response contains error
        if "error" in response_data:
            error_message = json.loads(response_data["error"])
            logging.error(f"Error received from results service: {error_message}")
            raise HTTPException(
                status_code=404, 
                detail=f"Error received from results service: {error_message}"
            )
        
        # Parse successful response
        response_data = json.loads(response_data)
        
        # Cache result
        try:
            redis_client.setex(
                cache_key,
                180,  # TTL in seconds
                json.dumps(response_data)
            )
            logging.info(f" Cached result: {cache_key} (TTL: 180s)")
        except Exception as e:
            # Failed to cache - not critical, continue
            logging.warning(f"Failed to cache result: {e}")
        
        return {"data": response_data, "cached": False}
        
    except HTTPException as e:
        logging.error(f"{str(e)}")
        raise e
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Endpoint route
@app.post("/route/")
async def calculate_route(payload: dict, x_auth_token: str = Header(None)):
    """
    Calculate pollution-aware route via Routing Service.
    
    Flow:
    1. Client sends route request (start, goal, alpha, sensor_types)
    2. Forward to Routing Service via HTTP
    3. Routing Service calculates A* path
    4. Returns GeoJSON route with statistics
    
    Args:
        payload: Route parameters
            - start: {lat, lon}
            - goal: {lat, lon}
            - alpha: 0.0-1.0 (0=fastest, 1=cleanest)
            - sensor_types: ["fixed"], ["mobile"], or ["fixed", "mobile"]
    
    Returns:
        GeoJSON route with waypoints and statistics
    """
    # await authorize(x_auth_token)
    
    try:
        # Forward to Routing Service
        routing_service_url = os.getenv('ROUTING_SERVICE_URL', 'http://routing-service:8003')
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{routing_service_url}/route",
                json=payload
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
        raise HTTPException(
            status_code=504,
            detail="Routing Service timeout"
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Cache management endpoints (for debugging/monitoring)
@app.get("/cache/stats")
async def cache_stats():
    """Get Redis cache statistics for Client Message Handler"""
    try:
        info = redis_client.info("stats")
        keyspace = redis_client.info("keyspace")
        
        # Count only client_query:* keys
        client_keys = len(redis_client.keys("client_query:*"))
        
        return {
            "connected": True,
            "total_commands": info.get("total_commands_processed", 0),
            "hits": info.get("keyspace_hits", 0),
            "misses": info.get("keyspace_misses", 0),
            "hit_rate_percent": round(
                (info.get("keyspace_hits", 0) / max(info.get("total_commands_processed", 1), 1)) * 100, 
                2
            ),
            "cached_client_queries": client_keys
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}

@app.delete("/cache/clear")
async def clear_cache():
    """Clear cached queries for Client Message Handler"""
    try:
        keys = redis_client.keys("client_query:*")
        if keys:
            redis_client.delete(*keys)
            logging.info(f" Cleared {len(keys)} cached client queries")
            return {"cleared": len(keys)}
        return {"cleared": 0, "message": "No cached queries to clear"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing cache: {str(e)}")
