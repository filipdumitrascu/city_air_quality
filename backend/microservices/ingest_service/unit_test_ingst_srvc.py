import pytest
import sys
import os
import json
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone

# Setup mocks before imports
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
        from ingest_service import app, process_message

from httpx import AsyncClient


# TEST HELPERS
class DummyMessage:
    """Mock PubSub message for testing"""
    def __init__(self, data):
        self.data = data
        self.ack_called = False
        self.nack_called = False

    def ack(self):
        self.ack_called = True

    def nack(self):
        self.nack_called = True


# TEST DATA (matching pollution_data schema)
valid_payload_full = {
    "sensor_id": "CityAirQ_001",
    "sensor_type": "mobile",
    "timestamp": 1718699260000,
    "latitude": 44.4268,
    "longitude": 26.1025,
    "altitude": 75.0,
    "humidity": 65.5,
    "pressure": 1013.25,
    "temperature": 22.3,
    "co": 0.5,
    "co2": 420.0,
    "no2": 35.2,
    "nh3": 12.1,
    "vocs": 150.0,
    "pm1_0": 8.5,
    "pm2_5": 15.3,
    "pm10": 42.7
}

valid_payload_minimal = {
    "sensor_id": "WearAware_005",
    "sensor_type": "mobile",
    "timestamp": 1718699260000,
    "latitude": 44.4268,
    "longitude": 26.1025
    # Optional fields will be passed as-is (defaults handled by database_service)
}

valid_payload_wearaware = {
    "sensor_id": "WearAware_003",
    "sensor_type": "mobile",
    "timestamp": 1718699260000,
    "latitude": 44.4300,
    "longitude": 26.1100,
    "altitude": 80.0,
    "humidity": 70.0,
    "pressure": 1010.0,
    "temperature": 20.0,
    "pm1_0": 10.0,
    "pm2_5": 18.0,
    "pm10": 35.0,
    "co2": 450.0,
    # WearAware doesn't measure: co, no2, nh3, vocs
    "co": -1,
    "no2": -1,
    "nh3": -1,
    "vocs": -1
}



# HEALTH ENDPOINT TESTS
@pytest.mark.asyncio
async def test_health_check():
    """Test /health endpoint returns healthy status"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/health")
    
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["service"] == "ingest_service"

@pytest.mark.asyncio
async def test_root_endpoint():
    """Test / endpoint returns service info"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/")
    
    assert response.status_code == 200
    assert response.json()["service"] == "ingest_service"
    assert response.json()["status"] == "running"



# MESSAGE PROCESSING TESTS
@pytest.mark.asyncio
@patch("ingest_service.send_data_to_database", new_callable=AsyncMock)
async def test_process_message_success_full(mock_send):
    """Test successful processing with all fields"""
    mock_send.return_value = {"success": True}

    message = DummyMessage(data=json.dumps(valid_payload_full).encode("utf-8"))
    await process_message(message)

    assert message.ack_called is True
    assert message.nack_called is False
    
    mock_send.assert_awaited_once()
    
    # Verify data passed to database
    args = mock_send.call_args[0][0]
    assert args["sensor_id"] == "CityAirQ_001"
    assert args["sensor_type"] == "mobile"
    assert args["pm10"] == 42.7
    assert args["no2"] == 35.2


@pytest.mark.asyncio
@patch("ingest_service.send_data_to_database", new_callable=AsyncMock)
async def test_process_message_success_minimal(mock_send):
    """Test successful processing with minimal fields"""
    mock_send.return_value = {"success": True}

    message = DummyMessage(data=json.dumps(valid_payload_minimal).encode("utf-8"))
    await process_message(message)

    assert message.ack_called is True
    mock_send.assert_awaited_once()
    
    args = mock_send.call_args[0][0]
    assert args["sensor_id"] == "WearAware_005"
    assert args["latitude"] == 44.4268


@pytest.mark.asyncio
@patch("ingest_service.send_data_to_database", new_callable=AsyncMock)
async def test_process_message_wearaware_sensor(mock_send):
    """Test processing WearAware sensor data (partial measurements)"""
    mock_send.return_value = {"success": True}

    message = DummyMessage(data=json.dumps(valid_payload_wearaware).encode("utf-8"))
    await process_message(message)

    assert message.ack_called is True
    
    args = mock_send.call_args[0][0]
    assert args["sensor_id"] == "WearAware_003"
    assert args["pm10"] == 35.0
    assert args["co2"] == 450.0
    assert args["no2"] == -1  # Not measured by WearAware


@pytest.mark.asyncio
@patch("ingest_service.send_data_to_database", new_callable=AsyncMock)
async def test_process_message_timestamp_conversion(mock_send):
    """Test timestamp conversion from Unix ms to ISO format"""
    mock_send.return_value = {"success": True}

    # Test with known timestamp: 2024-06-18 10:27:40 UTC
    payload = valid_payload_minimal.copy()
    payload["timestamp"] = 1718699260000

    message = DummyMessage(data=json.dumps(payload).encode("utf-8"))
    await process_message(message)

    args = mock_send.call_args[0][0]
    timestamp = args["timestamp"]
    
    # Should be ISO format
    assert "T" in timestamp
    assert "2024-06-18" in timestamp


@pytest.mark.asyncio
@patch("ingest_service.send_data_to_database", new_callable=AsyncMock)
async def test_process_message_timestamp_epoch(mock_send):
    """Test timestamp conversion for epoch start"""
    mock_send.return_value = {"success": True}

    payload = valid_payload_minimal.copy()
    payload["timestamp"] = 0  # Epoch start

    message = DummyMessage(data=json.dumps(payload).encode("utf-8"))
    await process_message(message)

    args = mock_send.call_args[0][0]
    timestamp = args["timestamp"]
    
    # Should be 1970-01-01
    assert "1970-01-01" in timestamp


@pytest.mark.asyncio
@patch("ingest_service.send_data_to_database", new_callable=AsyncMock)
async def test_process_message_database_error(mock_send):
    """Test handling when database returns error"""
    mock_send.return_value = {"error": "Connection failed"}

    message = DummyMessage(data=json.dumps(valid_payload_full).encode("utf-8"))
    await process_message(message)

    # Should still acknowledge (error was logged, not retriable)
    assert message.ack_called is True
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
@patch("ingest_service.send_data_to_database", new_callable=AsyncMock)
async def test_process_message_database_exception(mock_send):
    """Test handling when database throws exception"""
    mock_send.side_effect = Exception("Network error")

    message = DummyMessage(data=json.dumps(valid_payload_full).encode("utf-8"))
    await process_message(message)

    # Should nack for retry
    assert message.nack_called is True


@pytest.mark.asyncio
@patch("ingest_service.send_data_to_database", new_callable=AsyncMock)
async def test_process_message_invalid_json(mock_send):
    """Test handling of malformed JSON"""
    message = DummyMessage(data=b"invalid json{{{")
    
    await process_message(message)

    assert message.nack_called is True
    assert message.ack_called is False
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
@patch("ingest_service.send_data_to_database", new_callable=AsyncMock)
async def test_process_message_empty_payload(mock_send):
    """Test handling of empty payload"""
    mock_send.return_value = {"success": True}
    message = DummyMessage(data=b"{}")
    
    await process_message(message)

    # Should still process (with defaults/missing data)
    assert message.ack_called is True
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
@patch("ingest_service.send_data_to_database", new_callable=AsyncMock)
async def test_process_message_preserves_all_fields(mock_send):
    """Test that all pollution fields are preserved"""
    mock_send.return_value = {"success": True}

    message = DummyMessage(data=json.dumps(valid_payload_full).encode("utf-8"))
    await process_message(message)

    args = mock_send.call_args[0][0]
    
    # Verify all fields present
    assert args["altitude"] == 75.0
    assert args["humidity"] == 65.5
    assert args["pressure"] == 1013.25
    assert args["temperature"] == 22.3
    assert args["co"] == 0.5
    assert args["co2"] == 420.0
    assert args["no2"] == 35.2
    assert args["nh3"] == 12.1
    assert args["vocs"] == 150.0
    assert args["pm1_0"] == 8.5
    assert args["pm2_5"] == 15.3
    assert args["pm10"] == 42.7
