from fastapi import FastAPI
from contextlib import asynccontextmanager
from prometheus_fastapi_instrumentator import Instrumentator
import logging
import json
import asyncio

from database_service.client.database_service_client import send_data_to_database
from common.message_queue_googlepubsub.pubsub_client import PubSubClientSubscriber


# Logging to stdout only (visible via kubectl logs)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Constants
OPTIONAL_FIELD_DEFAULTS = {
    'altitude': -1, 'humidity': -1, 'pressure': -1, 'temperature': -1,
    'co': -1, 'co2': -1, 'no2': -1, 'nh3': -1, 'vocs': -1,
    'pm1_0': -1, 'pm2_5': -1, 'pm10': -1
}


# PubSub message handler
async def process_message(message):
    """ Process incoming sensor data and store in database. """
    try:
        # Decode message payload
        data = json.loads(message.data.decode("utf-8"))
        
        # Acknowledge message immediately
        message.ack()
        
        sensor_id = data.get("sensor_id", "unknown")
        logging.info(f"Processing data from sensor: {sensor_id}")

        # Validate timestamp
        timestamp_ms = data.get("timestamp")
        if not isinstance(timestamp_ms, int) or timestamp_ms < 0:
            logging.error(f"Invalid timestamp for sensor {sensor_id}: {timestamp_ms}")
            return
        
        # Replace None values with defaults (-1)
        for field, default in OPTIONAL_FIELD_DEFAULTS.items():
            if data.get(field) is None:
                data[field] = default
        
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
ingest_subscriber = PubSubClientSubscriber("ingest_service_messages-sub", process_message)


# FASTAPI APPLICATION
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - start subscriber on startup."""
    asyncio.create_task(ingest_subscriber.start_subscriber())
    logging.info(f"PubSub subscriber started for 'ingest_service_messages-sub'")
    
    yield
    
    ingest_subscriber.stop()
    logging.info("Ingest Service shutting down")

app = FastAPI(
    title="Ingest Service",
    description="Sensor data processor for CityAirQ",
    version="2.0.0",
    lifespan=lifespan
)

# Prometheus metrics
Instrumentator().instrument(app).expose(app)


# HEALTH ENDPOINTS
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
    }
