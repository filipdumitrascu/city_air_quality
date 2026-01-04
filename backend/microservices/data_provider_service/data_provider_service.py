import logging
import os
import json
from fastapi import HTTPException
from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio

logging.basicConfig(
    level=logging.DEBUG,
    filename=os.path.join('logs', 'data_provider_service.log'),
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s'
)

from database_service.client.database_service_client import get_data_from_database
from pubsub.message_queue_googlepubsub.pubsub_client import PubSubClientSubscriber, PubSubClientPublisher

subscription_name = "results_service_messages-sub"

async def process_message(message):
    try:
        decoded_message = json.loads(message.data.decode("utf-8"))
        logging.info(f"Received message: {decoded_message}")
        message.ack()

        available_layers = ["Temperature", "Humidity", "Pressure", "Altitude", "CO2", "PM1_0", "PM2_5", "PM10"]
        selected_layers = decoded_message["layers"] if decoded_message["layers"] else available_layers        
        decoded_message["layers"] = selected_layers

        try:
            response = await get_data_from_database(decoded_message)
            PubSubClientPublisher.publish_message("results_response_messages", response)
        except HTTPException as e:
            logging.error(f"Error receiving response from database: {e.detail}")
            PubSubClientPublisher.publish_message("results_response_messages", {"error": e.detail, "status_code": e.status_code})
    except Exception as e:
        logging.error(f"Error processing message: {str(e)}")
        message.nack()

results_subscriber = PubSubClientSubscriber(subscription_name, process_message)

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(results_subscriber.start_subscriber())
    logging.info("Subscriber started and listening for messages on 'results_service_messages-sub'.")
    yield

app = FastAPI(
    title="Data provider service API",
    description="Receives requests and returns data",
    lifespan=lifespan,
    version="1.0.0")
