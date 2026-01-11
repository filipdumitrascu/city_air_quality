from fastapi import FastAPI, HTTPException
import logging
import os
import time
import json
import asyncio
from fastapi import Header
from fastapi.responses import JSONResponse
from queue import Queue
from fastapi import Request
from prometheus_fastapi_instrumentator import Instrumentator

from pubsub.message_queue_googlepubsub.pubsub_client import PubSubClientPublisher, PubSubClientSubscriber
from pubsub.authentification_service.auth import authorize

import redis

# Connect to Redis for potential caching/session management
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'redis'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    decode_responses=True
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

async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI app.
    Starts PubSub subscriber as background task on app startup.
    """
    # Start subscriber in background (runs continuously)
    asyncio.create_task(results_subscriber.start_subscriber())
    logging.info("Subscriber started and listening for messages on 'results_response_messages-sub'.")
    
    yield  # App runs here

app = FastAPI(
    title="Client Message Handler API",
    description="Handles requests to enter pollution information or read existing data",
    lifespan=lifespan,
    version="1.0.0"
)

# Prometheus metrics for monitoring
Instrumentator().instrument(app).expose(app)


# ENDPOINT: /ingest/
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

# ENDPOINT: /results/
@app.post("/results/")
async def get_data(payload: dict, x_auth_token: str = Header(None)):
    """
    Query pollution data via PubSub request-response pattern.
    
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
    """
    # await authorize(x_auth_token)
    
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
        
        # Parse and return successful response
        response_data = json.loads(response_data)
        return {"data": response_data}
        
    except HTTPException as e:
        logging.error(f"{str(e)}")
        raise e
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
