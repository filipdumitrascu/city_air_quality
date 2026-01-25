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
        from ingest_service import process_message

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


# Test Data
valid_payload = {
    "clientId": "clientId-a12b34cd5678ef90",
    "timestamp": 1718699260000,  # Unix timestamp in milliseconds
    "location": {
        "latitude": 45.764043,
        "longitude": 4.835659
    },
    "data": [
        {"dimension": "Temperature", "value": 30.5},
        {"dimension": "Humidity", "value": 55.2},
        {"dimension": "Pressure", "value": 1012.3},
        {"dimension": "Altitude", "value": 120.4},
        {"dimension": "CO2", "value": 600},
        {"dimension": "PM1.0", "value": 10.1},
        {"dimension": "PM2.5", "value": 15.3},
        {"dimension": "PM10", "value": 18.2}
    ]
}


@pytest.mark.asyncio
@patch("ingest_service.send_data_to_database", new_callable=AsyncMock)
async def test_process_message_success(mock_send):
    """Test successful message processing and database insertion"""
    # Mock successful database response
    mock_send.return_value = {"success": True}

    # Create mock message
    message = DummyMessage(data=json.dumps(valid_payload).encode("utf-8"))

    # Process message
    await process_message(message)

    # Assertions
    assert message.ack_called is True, "Message should be acknowledged"
    assert message.nack_called is False, "Message should not be negatively acknowledged"
    
    mock_send.assert_awaited_once()
    
    # Verify processed data
    args, _ = mock_send.call_args
    processed_data = args[0]
    
    assert processed_data["clientId"] == "clientId-a12b34cd5678ef90"
    
    # Verify timestamp was converted to ISO format
    assert "T" in processed_data["timestamp"], "Timestamp should be in ISO format"
    # Should end with timezone info (Z or +00:00)
    assert processed_data["timestamp"].endswith("Z") or "+00:00" in processed_data["timestamp"]


@pytest.mark.asyncio
@patch("ingest_service.send_data_to_database", new_callable=AsyncMock)
async def test_process_message_preserves_sensor_data(mock_send):
    """Test that sensor data is preserved during processing"""
    mock_send.return_value = {"success": True}

    message = DummyMessage(data=json.dumps(valid_payload).encode("utf-8"))
    await process_message(message)

    # Verify sensor data integrity
    args, _ = mock_send.call_args
    processed_data = args[0]
    
    assert processed_data["location"]["latitude"] == 45.764043
    assert processed_data["location"]["longitude"] == 4.835659
    assert len(processed_data["data"]) == 8
    
    # Verify specific measurements
    temp_data = next(d for d in processed_data["data"] if d["dimension"] == "Temperature")
    assert temp_data["value"] == 30.5


@pytest.mark.asyncio
@patch("ingest_service.send_data_to_database", new_callable=AsyncMock)
async def test_process_message_database_error(mock_send):
    """Test handling of database service error"""
    # Mock database returning error
    mock_send.return_value = {"error": "Database connection failed"}

    message = DummyMessage(data=json.dumps(valid_payload).encode("utf-8"))
    await process_message(message)

    # Should still acknowledge (error was handled)
    assert message.ack_called is True
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
@patch("ingest_service.send_data_to_database", new_callable=AsyncMock)
async def test_process_message_invalid_json(mock_send):
    """Test handling of malformed message data"""
    # Invalid JSON
    message = DummyMessage(data=b"invalid json{{{")
    
    await process_message(message)

    # Should nack (negative acknowledge) - message will be redelivered
    assert message.nack_called is True
    assert message.ack_called is False
    
    # Should NOT call database
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
@patch("ingest_service.send_data_to_database", new_callable=AsyncMock)
async def test_process_message_timestamp_conversion(mock_send):
    """Test timestamp conversion from Unix to ISO format"""
    mock_send.return_value = {"success": True}

    # Test with specific timestamp
    test_payload = valid_payload.copy()
    test_payload["timestamp"] = 1609459200000  # 2021-01-01 00:00:00 UTC

    message = DummyMessage(data=json.dumps(test_payload).encode("utf-8"))
    await process_message(message)

    args, _ = mock_send.call_args
    processed_timestamp = args[0]["timestamp"]
    
    # Verify ISO format
    assert "2021-01-01" in processed_timestamp or "2020-12-31" in processed_timestamp  # Timezone adjustment
    assert "T" in processed_timestamp
    assert processed_timestamp.endswith("Z") or "+00:00" in processed_timestamp
