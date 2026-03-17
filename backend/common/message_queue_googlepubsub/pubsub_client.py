from google.cloud import pubsub_v1
import logging
import json
import asyncio
import os
from typing import Callable, Any

# GCP Project ID from environment or default
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "elite-totem-484208-e2")


class PubSubClientSubscriber:
    def __init__(self, subscription_name: str, process_message: Callable):
        self.project_id = PROJECT_ID
        self.subscription_name = subscription_name
        self.client = pubsub_v1.SubscriberClient()
        self.process_message = process_message
        self.subscription_path = self.client.subscription_path(
            self.project_id, 
            self.subscription_name
        )
        self.streaming_pull_future = None
        
        logging.info(f"Subscriber initialized for {self.subscription_path}")

    def sync_callback(self, message) -> None:
        """
        Synchronous callback wrapper for Pub/Sub.
        
        Creates a new event loop to run the async process_message handler.
        This is required because Pub/Sub's callback runs in a thread pool.
        
        Args:
            message: Pub/Sub message object with .data, .ack(), .nack() methods
        """
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.process_message(message))
            finally:
                loop.close()
        except Exception as e:
            logging.error(f"Error processing message: {str(e)}")
            message.nack()

    async def start_subscriber(self) -> None:
        """
        Start the subscriber and listen for messages indefinitely.
        
        This method blocks and should be run as a background task:
            asyncio.create_task(subscriber.start_subscriber())
        """
        self.streaming_pull_future = self.client.subscribe(
            self.subscription_path, 
            callback=self.sync_callback
        )
        logging.info(f"Listening for messages on {self.subscription_path}...")
        
        loop = asyncio.get_running_loop()
        try:
            # Run the blocking subscriber in executor to not block async loop
            await loop.run_in_executor(None, self.streaming_pull_future.result)
        except asyncio.CancelledError:
            logging.info(f"Subscriber {self.subscription_name} cancelled")
            self.streaming_pull_future.cancel()
        except Exception as e:
            logging.error(f"Subscriber error: {e}")
            self.streaming_pull_future.cancel()
            raise

    def stop(self) -> None:
        """Stop the subscriber gracefully."""
        if self.streaming_pull_future:
            self.streaming_pull_future.cancel()
            logging.info(f"Subscriber {self.subscription_name} stopped")


class PubSubClientPublisher:
    # Reusable publisher client (thread-safe)
    _publisher = None
    
    @classmethod
    def _get_publisher(cls) -> pubsub_v1.PublisherClient:
        """Get or create singleton publisher client."""
        if cls._publisher is None:
            cls._publisher = pubsub_v1.PublisherClient()
        return cls._publisher
    
    @staticmethod
    def publish_message(topic_name: str, message_data: Any) -> str:
        """
        Publish a message to a Pub/Sub topic.
        
        Args:
            topic_name: Name of the topic (not full path)
            message_data: Data to publish (will be JSON serialized)
        
        Returns:
            str: Message ID of the published message
        
        Raises:
            Exception: If publishing fails
        """
        publisher = PubSubClientPublisher._get_publisher()
        topic_path = publisher.topic_path(PROJECT_ID, topic_name)
        
        # Handle both dict and string message data
        if isinstance(message_data, str):
            encoded_message = message_data.encode("utf-8")
        else:
            encoded_message = json.dumps(message_data).encode("utf-8")
        
        try:
            future = publisher.publish(topic_path, encoded_message)
            message_id = future.result(timeout=10)  # Wait up to 10s
            logging.info(f"Published message {message_id} to {topic_name}")
            return message_id
        except Exception as e:
            logging.error(f"Failed to publish to {topic_name}: {e}")
            raise
    
    @staticmethod
    async def publish_message_async(topic_name: str, message_data: Any) -> str:
        """
        Async wrapper for publish_message.
        
        Runs the synchronous publish in an executor to avoid blocking.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            PubSubClientPublisher.publish_message,
            topic_name,
            message_data
        )
