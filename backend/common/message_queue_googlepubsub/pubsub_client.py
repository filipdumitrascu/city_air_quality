from google.cloud import pubsub_v1
import logging
import json
import asyncio

project_id = "cityairq-pollution-project"

class PubSubClientSubscriber:
    def __init__(self, subscription_name, process_message):
        self.project_id = project_id
        self.subscription_name = subscription_name
        self.client = pubsub_v1.SubscriberClient()
        self.process_message = process_message
        self.subscription_path = self.client.subscription_path(self.project_id, self.subscription_name)

    async def callback(self, message):
        """Execută callback-ul într-un mod compatibil cu asyncio."""
        try:
            await self.process_message(message)
            message.ack()
        except Exception as e:
            logging.error(f"Error in callback: {str(e)}")
            message.nack()

    async def start_subscriber(self):
        """Pornește subscriber-ul în event loop-ul principal."""
        loop = asyncio.get_running_loop()
        future = self.client.subscribe(self.subscription_path, callback=lambda msg: asyncio.run_coroutine_threadsafe(self.callback(msg), loop))
        logging.info(f"Listening for messages on {self.subscription_path}...")
        # await future

class PubSubClientPublisher:
    def publish_message(topic_name, message_data):
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(project_id, topic_name)
        
        encoded_message = json.dumps(message_data).encode("utf-8") 
        
        future = publisher.publish(topic_path, encoded_message)
        print(f"Message published: {future.result()}")
