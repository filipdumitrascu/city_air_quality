from fastapi import HTTPException
from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio
import logging
import os
import json


# Configure file-based logging for Data Provider Service
logging.basicConfig(
    level=logging.DEBUG,
    filename=os.path.join('logs', 'data_provider_service.log'),
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Import dependencies
from database_service.client.database_service_client import get_data_from_database
from pubsub.message_queue_googlepubsub.pubsub_client import PubSubClientSubscriber, PubSubClientPublisher


# Subscribe to query requests from Client Message Handler
subscription_name = "results_service_messages-sub"


async def process_message(message):
    """
    Process incoming query requests from PubSub.
    
    Flow:
    1. Client Message Handler publishes query to 'results_service_messages'
    2. This subscriber receives the message
    3. Query Database Service for pollution data
    4. Publish response to 'results_response_messages'
    5. Client Message Handler picks up response and returns to client
    
    Args:
        message: PubSub message containing query parameters
                 (latitude, longitude, radius, layers)
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

        try:
            # Query Database Service for pollution data
            # Returns list of sensor readings matching location/radius criteria
            response = await get_data_from_database(decoded_message)
            
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
    
    # Shutdown (cleanup if needed)
    logging.info("Shutting down Data Provider Service...")


app = FastAPI(
    title="Data Provider Service API",
    description="Receives requests and returns data",
    lifespan=lifespan,
    version="1.0.0"
)

# NOTE: No HTTP endpoints defined
# This service operates entirely through PubSub messaging.
# It has no direct HTTP API - all communication is async via:
# - Input: 'results_service_messages' topic
# - Output: 'results_response_messages' topic
