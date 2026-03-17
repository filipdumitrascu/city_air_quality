"""
Ingest Service - Sensor Data Processor for CityAirQ

Receives sensor data from Client Message Handler via PubSub,
processes timestamps, and forwards to Database Service for storage.

Flow:
1. Client Message Handler publishes to 'ingest_service_messages'
2. This service receives and processes the data
3. Converts timestamp to QuestDB-compatible format
4. Forwards to Database Service for storage in pollution_data table
"""

import json
import logging
import asyncio
import os
from datetime import datetime, timezone
from fastapi import FastAPI
from contextlib import asynccontextmanager
from prometheus_fastapi_instrumentator import Instrumentator

from database_service.client.database_service_client import send_data_to_database
from common.message_queue_googlepubsub.pubsub_client import PubSubClientSubscriber


# Logging to stdout only
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# PubSub subscription for sensor data
SUBSCRIPTION_NAME = "ingest_service_messages-sub"


# MESSAGE PROCESSING
async def process_message(message):
    """
    Process incoming sensor data and store in database.
    
    Expected payload (from Client Message Handler):
    {
        "sensor_id": "CityAirQ_001",
        "sensor_type": "mobile",
        "timestamp": 1718699260000,  # Unix ms
        "latitude": 44.4268,
        "longitude": 26.1025,
        "altitude": 75.0,      # optional, default -1
        "humidity": 65.5,      # optional, default -1
        "pressure": 1013.25,   # optional, default -1
        "temperature": 22.3,   # optional, default -1
        "co": 0.5,             # optional, default -1
        "co2": 420.0,          # optional, default -1
        "no2": 35.2,           # optional, default -1
        "nh3": 12.1,           # optional, default -1
        "vocs": 150.0,         # optional, default -1
        "pm1_0": 8.5,          # optional, default -1
        "pm2_5": 15.3,         # optional, default -1
        "pm10": 42.7           # optional, default -1
    }
    """
    try:
        # Decode message payload
        data = json.loads(message.data.decode("utf-8"))
        
        # Acknowledge message immediately
        message.ack()
        
        sensor_id = data.get("sensor_id", "unknown")
        logging.info(f"Processing data from sensor: {sensor_id}")

        # Convert Unix timestamp (ms) to ISO 8601 format for QuestDB
        timestamp_ms = data.get("timestamp", 0)
        if isinstance(timestamp_ms, int) and timestamp_ms >= 0:
            # Convert milliseconds to datetime
            dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            data["timestamp"] = dt.isoformat()
        
        # Forward to Database Service
        response = await send_data_to_database(data)
        
        if response.get("success"):
            logging.info(f"Data stored for sensor {sensor_id}")
        else:
            logging.error(f"Database error for sensor {sensor_id}: {response.get('error')}")

    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON: {str(e)}")
        message.nack()
    except Exception as e:
        logging.error(f"Error processing message: {str(e)}")
        message.nack()


# PubSub subscriber
ingest_subscriber = PubSubClientSubscriber(SUBSCRIPTION_NAME, process_message)


# FASTAPI APPLICATION
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - start subscriber on startup."""
    asyncio.create_task(ingest_subscriber.start_subscriber())
    logging.info(f"PubSub subscriber started for '{SUBSCRIPTION_NAME}'")
    
    yield
    
    ingest_subscriber.stop()
    logging.info("Ingest Service shutting down")

app = FastAPI(
    title="Ingest Service",
    description="Sensor data processor for CityAirQ",
    version="2.0.0",
    lifespan=lifespan
)

Instrumentator().instrument(app).expose(app)


# ENDPOINTS
@app.get("/")
async def root():
    return {
        "service": "ingest_service",
        "version": "2.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "ingest_service",
        "subscription": SUBSCRIPTION_NAME
    }
