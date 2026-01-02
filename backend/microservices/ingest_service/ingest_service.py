import json
import logging
from datetime import datetime
import pytz
import os
import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager 

logging.basicConfig(
    level=logging.DEBUG, 
    filename=os.path.join('logs', 'ingest_service.log'),
    filemode='w', 
    format='%(asctime)s - %(levelname)s - %(message)s'
)  

from database_service.client.database_service_client import send_data_to_database
from pubsub.message_queue_googlepubsub.pubsub_client import PubSubClientSubscriber

subscription_name = "ingest_service_messages-sub"

async def process_message(message):
    try:
        decoded_message = json.loads(message.data.decode("utf-8"))
        message.ack()
        logging.info(f"Received message: {decoded_message}")

        #Process timestamp
        utc_time = decoded_message["timestamp"] + 7200000 
        utc_dt = datetime.fromtimestamp(utc_time / 1000)
        isoTimestamp = pytz.utc.localize(utc_dt).isoformat()
        decoded_message["timestamp"] = isoTimestamp

        response = await send_data_to_database(decoded_message)
        
        if response.get("success"):
            logging.info("Message successfully processed and acknowledged")

    except Exception as e:
        logging.error(f"Error processing message: {str(e)}")
        message.nack() 

ingest_subscriber = PubSubClientSubscriber(subscription_name, process_message)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestionarea ciclului de viață al aplicației pentru a porni subscriber-ul."""
    asyncio.create_task(ingest_subscriber.start_subscriber())
    logging.info("Subscriber started and listening for messages on 'ingest_service_messages-sub'.")
    yield

app = FastAPI(lifespan=lifespan)
