from google.cloud import pubsub_v1
import logging
import json
import asyncio
import os

project_id = os.getenv("GCP_PROJECT_ID", "elite-totem-484208-e2")

class PubSubClientSubscriber:
    def __init__(self, subscription_name, process_message):
        self.project_id = project_id
        self.subscription_name = subscription_name
        self.client = pubsub_v1.SubscriberClient()
        self.process_message = process_message
        self.subscription_path = self.client.subscription_path(self.project_id, self.subscription_name)
        self.streaming_pull_future = None

    def sync_callback(self, message):
        """Synchronised call back for PubSub. Stays in thread"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.process_message(message))
            finally:
                loop.close()
        except Exception as e:
            logging.error(f"Error in callback: {str(e)}")
            message.nack()

    async def start_subscriber(self):
        """Starts the subscriber which stays active"""
        self.streaming_pull_future = self.client.subscribe(
            self.subscription_path, 
            callback=self.sync_callback
        )
        logging.info(f"Listening for messages on {self.subscription_path}...")
        
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self.streaming_pull_future.result)
        except Exception as e:
            logging.error(f"Subscriber error: {e}")
            self.streaming_pull_future.cancel()

class PubSubClientPublisher:
    @staticmethod
    def publish_message(topic_name, message_data):
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(project_id, topic_name)
        
        encoded_message = json.dumps(message_data).encode("utf-8") 
        
        future = publisher.publish(topic_path, encoded_message)
        logging.info(f"Message published: {future.result()}")
