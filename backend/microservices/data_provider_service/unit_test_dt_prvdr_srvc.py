import pytest
import sys
import os
import json
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

sys.modules['google'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.pubsub_v1'] = MagicMock()
sys.modules['google.auth'] = MagicMock()

sys.modules['database_service'] = MagicMock()
sys.modules['database_service.client'] = MagicMock()
sys.modules['database_service.client.database_service_client'] = MagicMock()

with patch('common.message_queue_googlepubsub.pubsub_client.pubsub_v1.SubscriberClient'):
    with patch('common.message_queue_googlepubsub.pubsub_client.pubsub_v1.PublisherClient'):
        from data_provider_service import process_message

class DummyMessage:
    """Mock PubSub message for testing"""
    def __init__(self, data):
        self.data = data
        self.ack_called = False
        self.nack_called = False

    def ack(self):
        """Acknowledge message"""
        self.ack_called = True

    def nack(self):
        """Negative acknowledge message"""
        self.nack_called = True


@pytest.mark.asyncio
@patch("data_provider_service.get_data_from_database", new_callable=AsyncMock)
@patch("data_provider_service.PubSubClientPublisher.publish_message")
async def test_process_message_success(mock_publish, mock_get_data):
    """Test successful message processing and data retrieval"""
    # Mock database response
    mock_get_data.return_value = {
        "Temperature": 30.5,
        "Humidity": 55.2,
        "Pressure": 1012.3
    }

    # Create test payload
    payload = {
        "latitude": 45.764043,
        "longitude": 4.835659,
        "radius": 0,
        "layers": ["Temperature", "Humidity", "Pressure"]
    }

    # Create mock message
    message = DummyMessage(data=json.dumps(payload).encode("utf-8"))

    # Process message
    await process_message(message)

    # Assertions
    assert message.ack_called is True, "Message should be acknowledged"
    assert message.nack_called is False, "Message should not be negatively acknowledged"
    
    mock_get_data.assert_awaited_once()
    mock_publish.assert_called_once()

    # Verify published data
    published_data = mock_publish.call_args[0][1]
    assert "Temperature" in published_data
    assert published_data["Temperature"] == 30.5
    assert "Humidity" in published_data
    assert published_data["Humidity"] == 55.2
    assert "Pressure" in published_data
    assert published_data["Pressure"] == 1012.3


@pytest.mark.asyncio
@patch("data_provider_service.get_data_from_database", new_callable=AsyncMock)
@patch("data_provider_service.PubSubClientPublisher.publish_message")
async def test_process_message_with_default_layers(mock_publish, mock_get_data):
    """Test message processing when no layers specified (should use all)"""
    mock_get_data.return_value = {"PM10": 50.0}

    # Payload without layers (should default to all)
    payload = {
        "latitude": 45.764043,
        "longitude": 4.835659,
        "radius": 5,
        "layers": []  # Empty - should use all available layers
    }

    message = DummyMessage(data=json.dumps(payload).encode("utf-8"))
    await process_message(message)

    assert message.ack_called is True
    
    # Check that get_data_from_database was called with all layers
    call_args = mock_get_data.call_args[0][0]
    expected_layers = ["Temperature", "Humidity", "Pressure", "Altitude", "CO2", "PM1_0", "PM2_5", "PM10"]
    assert call_args["layers"] == expected_layers


@pytest.mark.asyncio
@patch("data_provider_service.get_data_from_database", new_callable=AsyncMock)
@patch("data_provider_service.PubSubClientPublisher.publish_message")
async def test_process_message_database_error(mock_publish, mock_get_data):
    """Test error handling when database returns HTTPException"""
    from fastapi import HTTPException
    
    # Mock database raising error
    mock_get_data.side_effect = HTTPException(status_code=404, detail="No data found")

    payload = {
        "latitude": 45.764043,
        "longitude": 4.835659,
        "radius": 5,
        "layers": ["PM10"]
    }

    message = DummyMessage(data=json.dumps(payload).encode("utf-8"))
    await process_message(message)

    # Should still acknowledge (error was handled)
    assert message.ack_called is True
    
    # Should publish error response
    mock_publish.assert_called_once()
    error_response = mock_publish.call_args[0][1]
    assert "error" in error_response
    assert "No data found" in error_response["error"]
    assert error_response["status_code"] == 404


@pytest.mark.asyncio
@patch("data_provider_service.get_data_from_database", new_callable=AsyncMock)
@patch("data_provider_service.PubSubClientPublisher.publish_message")
async def test_process_message_invalid_json(mock_publish, mock_get_data):
    """Test handling of malformed message data"""
    # Invalid JSON
    message = DummyMessage(data=b"invalid json{{{")
    
    await process_message(message)

    # Should nack (negative acknowledge) - message will be redelivered
    assert message.nack_called is True
    assert message.ack_called is False
    
    # Should NOT call database or publish
    mock_get_data.assert_not_awaited()
    mock_publish.assert_not_called()
