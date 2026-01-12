import json
import logging
from datetime import datetime
import pytz
import os
import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager 


# Configure file-based logging for Ingest Service
logging.basicConfig(
    level=logging.INFO, 
    filename=os.path.join('logs', 'ingest_service.log'),
    filemode='w', 
    format='%(asctime)s - %(levelname)s - %(message)s'
)  

# Import dependencies
from database_service.client.database_service_client import send_data_to_database
from pubsub.message_queue_googlepubsub.pubsub_client import PubSubClientSubscriber


# Subscribe to sensor data messages from Client Message Handler
subscription_name = "ingest_service_messages-sub"


async def process_message(message):
    """
    Process incoming sensor data and store in database.
    
    Flow:
    1. Client Message Handler publishes sensor data to 'ingest_service_messages'
    2. This subscriber receives the message
    3. Preprocess timestamp (convert Unix timestamp to ISO format)
    4. Send processed data to Database Service
    5. Database Service stores in QuestDB
    
    Args:
        message: PubSub message containing sensor data
                 (clientId, timestamp, location, pollution measurements)
    """
    try:
        # Decode message payload
        decoded_message = json.loads(message.data.decode("utf-8"))
        
        # Acknowledge message immediately (prevents redelivery)
        message.ack()
        logging.info(f"Received message: {decoded_message}")

        # Convert Unix timestamp (milliseconds) to ISO 8601 format
        # Add 7200000ms (2 hours) for timezone adjustment
        utc_time = decoded_message["timestamp"] + 7200000 
        utc_dt = datetime.fromtimestamp(utc_time / 1000)
        isoTimestamp = pytz.utc.localize(utc_dt).isoformat()
        decoded_message["timestamp"] = isoTimestamp

        # Forward processed data to Database Service for storage
        response = await send_data_to_database(decoded_message)
        
        if response.get("success"):
            logging.info("Message successfully processed and acknowledged")

    except Exception as e:
        # Handle processing errors
        logging.error(f"Error processing message: {str(e)}")
        
        # Negative acknowledge - message will be redelivered
        message.nack() 


# Create subscriber that listens for sensor data messages
ingest_subscriber = PubSubClientSubscriber(subscription_name, process_message)


# Fast API
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI app.
    Starts PubSub subscriber as background task on app startup.
    """
    # Startup - start listening for sensor data
    asyncio.create_task(ingest_subscriber.start_subscriber())
    logging.info("Subscriber started and listening for messages on 'ingest_service_messages-sub'.")
    
    yield  # App runs here
    
    # Shutdown
    logging.info("Shutting down Ingest Service...")


app = FastAPI(
    title="Ingest Service API",
    description="Preprocess and ingest sensor data",
    lifespan=lifespan,
    version="1.0.0"
)

# NOTE: No HTTP endpoints defined
# This service operates entirely through PubSub messaging.
# It has no direct HTTP API - all communication is async via:
# - Input: 'ingest_service_messages' topic
# - Output: HTTP calls to Database Service
