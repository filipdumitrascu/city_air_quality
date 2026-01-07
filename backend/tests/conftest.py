import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

# Add backend/ to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# Mock Google Cloud globally
sys.modules['google'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.pubsub_v1'] = MagicMock()
sys.modules['google.auth'] = MagicMock()

@pytest.fixture(autouse=True)
def mock_pubsub():
    """Mock PubSub for all tests"""
    with patch('pubsub.message_queue_googlepubsub.pubsub_client.pubsub_v1.SubscriberClient'):
        with patch('pubsub.message_queue_googlepubsub.pubsub_client.pubsub_v1.PublisherClient'):
            yield
