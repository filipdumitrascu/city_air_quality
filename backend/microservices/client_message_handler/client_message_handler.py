from fastapi import FastAPI, HTTPException
import logging
import os
import time
import json
import asyncio
import logging
from fastapi import Header
from fastapi.responses import JSONResponse
from queue import Queue
from fastapi import Request
from prometheus_fastapi_instrumentator import Instrumentator

from common.message_queue_googlepubsub.pubsub_client import PubSubClientPublisher, PubSubClientSubscriber
from common.authentification_service.auth import authorize

import redis
import os

# După inițializarea FastAPI
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'redis'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    decode_responses=True
)

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

response_queue = Queue()

async def process_results_message(message):
    """Procesează mesajele primite din results_response_messages-sub."""
    try:
        response_data = json.loads(message.data.decode("utf-8"))
        response_queue.put(response_data) 
        message.ack()
        logging.info(f"Received response from message queue: {response_data}")
    except Exception as e:
        logging.error(f"Error processing message: {str(e)}")
        message.nack() 

results_subscriber = PubSubClientSubscriber("results_response_messages-sub", process_results_message)

async def lifespan(app: FastAPI):
    asyncio.create_task(results_subscriber.start_subscriber())
    logging.info("Subscriber started and listening for messages on 'results_response_messages-sub'.")
    yield

app = FastAPI(lifespan=lifespan)
Instrumentator().instrument(app).expose(app)

@app.post("/ingest/")
async def ingest_data(payload: dict, x_auth_token: str = Header(None)):
    # await authorize(x_auth_token)
    try:
        PubSubClientPublisher.publish_message("ingest_service_messages", payload)
        logging.info("The request was sent to ingest service")
        return JSONResponse(
        status_code=200,
        content={"details": "Data successfully added in the database"},
    )

    except Exception as e:
        logging.error(f"{str(e)}")
        raise HTTPException(status_code=400, detail=f"Error while sending the request into the message queue")

@app.post("/results/")
async def get_data(payload: dict, x_auth_token: str = Header(None)):
    # await authorize(x_auth_token)
    try:
        PubSubClientPublisher.publish_message("results_service_messages", payload)
        logging.info("The request was published in the queue and waiting for response....")
        start_time = time.time()
        while response_queue.empty():
            if time.time() - start_time > 30:
                raise HTTPException(status_code=408, detail="Timeout waiting for response from results service")
            await asyncio.sleep(1)

        response_data = response_queue.get_nowait()
        logging.info(f"Received response: {response_data}")

        if "error" in response_data:
            error_message = json.loads(response_data["error"])
            logging.error(f"Error received from results service: {error_message}")
            raise HTTPException(status_code=404, detail=f"Error received from results service: {error_message}")

        response_data = json.loads(response_data)
        return {"data": response_data}
        
    except HTTPException as e:
        logging.error(f"{str(e)}")
        raise e

    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
    