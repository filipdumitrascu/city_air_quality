import pytest
import sys
import os
import json
from unittest.mock import patch, AsyncMock, MagicMock

# Mock Google Cloud modules before importing app
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
        from data_provider_service import app, process_message, generate_cache_key, AVAILABLE_LAYERS

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
valid_query_payload = {
    "latitude": 44.4268,
    "longitude": 26.1025,
    "radius": 5.0,
    "sensor_types": ["CityAirQ", "WearAware"],
    "layers": ["pm10", "pm2_5", "no2"]
}

valid_query_payload_minimal = {
    "latitude": 44.4268,
    "longitude": 26.1025,
    "radius": 5.0
}

mock_database_response = [
    {
        "sensor_type": "CityAirQ",
        "sensor_id": "001",
        "timestamp": "2026-03-15T10:00:00",
        "latitude": 44.4268,
        "longitude": 26.1025,
        "pm10": 42.7,
        "pm2_5": 15.3,
        "no2": 35.2
    },
    {
        "sensor_type": "CityAirQ",
        "sensor_id": "002",
        "timestamp": "2026-03-15T10:05:00",
        "latitude": 44.4275,
        "longitude": 26.1030,
        "pm10": 38.5,
        "pm2_5": 12.1,
        "no2": 28.9
    }
]


# HEALTH ENDPOINT TESTS
@pytest.mark.asyncio
async def test_health_check():
    """Test /health endpoint returns healthy status"""
    with patch('data_provider_service.redis_client') as mock_redis:
        mock_redis.ping.return_value = True
        
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.get("/health")
        
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert response.json()["service"] == "data_provider_service"

@pytest.mark.asyncio
async def test_root_endpoint():
    """Test / endpoint returns service info"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/")
    
    assert response.status_code == 200
    assert response.json()["service"] == "data_provider_service"
    assert response.json()["status"] == "running"


# MESSAGE PROCESSING TESTS
@pytest.mark.asyncio
@patch("data_provider_service.redis_client")
@patch("data_provider_service.get_data_from_database", new_callable=AsyncMock)
@patch("data_provider_service.PubSubClientPublisher.publish_message")
async def test_process_message_success(mock_publish, mock_get_data, mock_redis):
    """Test successful message processing and data retrieval"""
    mock_redis.get.return_value = None  # Cache miss
    mock_get_data.return_value = json.dumps(mock_database_response)

    message = DummyMessage(data=json.dumps(valid_query_payload).encode("utf-8"))
    await process_message(message)

    assert message.ack_called is True
    assert message.nack_called is False
    
    mock_get_data.assert_awaited_once()
    mock_publish.assert_called_once_with("results_response_messages", json.dumps(mock_database_response))

@pytest.mark.asyncio
@patch("data_provider_service.redis_client")
@patch("data_provider_service.get_data_from_database", new_callable=AsyncMock)
@patch("data_provider_service.PubSubClientPublisher.publish_message")
async def test_process_message_cache_hit(mock_publish, mock_get_data, mock_redis):
    """Test cache hit - should return cached result without querying database"""
    cached_data = json.dumps(mock_database_response)
    mock_redis.get.return_value = cached_data

    message = DummyMessage(data=json.dumps(valid_query_payload).encode("utf-8"))
    await process_message(message)

    assert message.ack_called is True
    
    # Should NOT query database
    mock_get_data.assert_not_awaited()
    
    # Should publish cached result
    mock_publish.assert_called_once_with("results_response_messages", cached_data)

@pytest.mark.asyncio
@patch("data_provider_service.redis_client")
@patch("data_provider_service.get_data_from_database", new_callable=AsyncMock)
@patch("data_provider_service.PubSubClientPublisher.publish_message")
async def test_process_message_with_default_layers(mock_publish, mock_get_data, mock_redis):
    """Test message processing when no layers specified - should use all available"""
    mock_redis.get.return_value = None
    mock_get_data.return_value = json.dumps(mock_database_response)

    # Payload without layers
    payload = {
        "latitude": 44.4268,
        "longitude": 26.1025,
        "radius": 5.0
    }

    message = DummyMessage(data=json.dumps(payload).encode("utf-8"))
    await process_message(message)

    assert message.ack_called is True
    
    # Check that get_data_from_database was called with all layers
    call_args = mock_get_data.call_args[0][0]
    assert call_args["layers"] == AVAILABLE_LAYERS

@pytest.mark.asyncio
@patch("data_provider_service.redis_client")
@patch("data_provider_service.get_data_from_database", new_callable=AsyncMock)
@patch("data_provider_service.PubSubClientPublisher.publish_message")
async def test_process_message_with_default_sensor_types(mock_publish, mock_get_data, mock_redis):
    """Test message processing when no sensor_types specified - should default to mobile"""
    mock_redis.get.return_value = None
    mock_get_data.return_value = json.dumps(mock_database_response)

    # Payload without sensor_types
    payload = {
        "latitude": 44.4268,
        "longitude": 26.1025,
        "radius": 5.0,
        "layers": ["pm10"]
    }

    message = DummyMessage(data=json.dumps(payload).encode("utf-8"))
    await process_message(message)

    assert message.ack_called is True
    
    # Check that get_data_from_database was called with default sensor_types
    call_args = mock_get_data.call_args[0][0]
    assert call_args["sensor_types"] == ["CityAirQ", "WearAware"]

@pytest.mark.asyncio
@patch("data_provider_service.redis_client")
@patch("data_provider_service.get_data_from_database", new_callable=AsyncMock)
@patch("data_provider_service.PubSubClientPublisher.publish_message")
async def test_process_message_with_fixed_sensors(mock_publish, mock_get_data, mock_redis):
    """Test message processing with fixed sensor type"""
    mock_redis.get.return_value = None
    mock_get_data.return_value = json.dumps(mock_database_response)

    payload = {
        "latitude": 44.4268,
        "longitude": 26.1025,
        "radius": 5.0,
        "sensor_types": ["SPO-RO"],
        "layers": ["pm10", "no2"]
    }

    message = DummyMessage(data=json.dumps(payload).encode("utf-8"))
    await process_message(message)

    call_args = mock_get_data.call_args[0][0]
    assert call_args["sensor_types"] == ["SPO-RO"]

@pytest.mark.asyncio
@patch("data_provider_service.redis_client")
@patch("data_provider_service.get_data_from_database", new_callable=AsyncMock)
@patch("data_provider_service.PubSubClientPublisher.publish_message")
async def test_process_message_database_error(mock_publish, mock_get_data, mock_redis):
    """Test error handling when database returns HTTPException"""
    from fastapi import HTTPException
    
    mock_redis.get.return_value = None
    mock_get_data.side_effect = HTTPException(status_code=404, detail="No data found")

    message = DummyMessage(data=json.dumps(valid_query_payload).encode("utf-8"))
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
@patch("data_provider_service.redis_client")
@patch("data_provider_service.get_data_from_database", new_callable=AsyncMock)
@patch("data_provider_service.PubSubClientPublisher.publish_message")
async def test_process_message_invalid_json(mock_publish, mock_get_data, mock_redis):
    """Test handling of malformed message data"""
    message = DummyMessage(data=b"invalid json{{{")
    
    await process_message(message)

    # Should nack - message will be redelivered
    assert message.nack_called is True
    assert message.ack_called is False
    
    # Should NOT call database or publish
    mock_get_data.assert_not_awaited()
    mock_publish.assert_not_called()

@pytest.mark.asyncio
@patch("data_provider_service.redis_client")
@patch("data_provider_service.get_data_from_database", new_callable=AsyncMock)
@patch("data_provider_service.PubSubClientPublisher.publish_message")
async def test_process_message_redis_error_continues(mock_publish, mock_get_data, mock_redis):
    """Test that Redis errors don't block processing"""
    mock_redis.get.side_effect = Exception("Redis connection error")
    mock_get_data.return_value = json.dumps(mock_database_response)

    message = DummyMessage(data=json.dumps(valid_query_payload).encode("utf-8"))
    await process_message(message)

    # Should still process successfully
    assert message.ack_called is True
    mock_get_data.assert_awaited_once()
    mock_publish.assert_called_once()


# CACHE KEY GENERATION TESTS
def test_generate_cache_key_consistent():
    """Test that same params generate same cache key"""
    params1 = {"latitude": 44.4268, "longitude": 26.1025, "radius": 5, "layers": ["pm10", "no2"]}
    params2 = {"latitude": 44.4268, "longitude": 26.1025, "radius": 5, "layers": ["no2", "pm10"]}  # Different order
    
    key1 = generate_cache_key(params1)
    key2 = generate_cache_key(params2)
    
    # Should be same (layers are sorted)
    assert key1 == key2

def test_generate_cache_key_different_params():
    """Test that different params generate different cache keys"""
    params1 = {"latitude": 44.4268, "longitude": 26.1025, "radius": 5, "layers": ["pm10"]}
    params2 = {"latitude": 44.4268, "longitude": 26.1025, "radius": 10, "layers": ["pm10"]}  # Different radius
    
    key1 = generate_cache_key(params1)
    key2 = generate_cache_key(params2)
    
    assert key1 != key2

def test_generate_cache_key_with_sensor_types():
    """Test cache key includes sensor_types"""
    params1 = {"latitude": 44.4268, "longitude": 26.1025, "radius": 5, "sensor_types": ["mobile"]}
    params2 = {"latitude": 44.4268, "longitude": 26.1025, "radius": 5, "sensor_types": ["fixed"]}
    
    key1 = generate_cache_key(params1)
    key2 = generate_cache_key(params2)
    
    assert key1 != key2

def test_generate_cache_key_empty_layers():
    """Test cache key with empty layers uses 'all'"""
    params = {"latitude": 44.4268, "longitude": 26.1025, "radius": 5, "layers": []}
    key = generate_cache_key(params)
    
    assert key.startswith("provider_query:")


# CACHE MANAGEMENT ENDPOINT TESTS
@pytest.mark.asyncio
@patch("data_provider_service.redis_client")
async def test_cache_stats(mock_redis):
    """Test /cache/stats returns Redis statistics"""
    mock_redis.info.return_value = {
        "total_commands_processed": 100,
        "keyspace_hits": 80,
        "keyspace_misses": 20
    }
    mock_redis.keys.return_value = ["key1", "key2", "key3"]
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/cache/stats")
    
    assert response.status_code == 200
    assert response.json()["connected"] == True
    assert response.json()["cached_queries"] == 3

@pytest.mark.asyncio
@patch("data_provider_service.redis_client")
async def test_cache_clear(mock_redis):
    """Test /cache/clear removes cached queries"""
    mock_redis.keys.return_value = ["provider_query:abc", "provider_query:def"]
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.delete("/cache/clear")
    
    assert response.status_code == 200
    assert response.json()["cleared"] == 2
    mock_redis.delete.assert_called_once()

@pytest.mark.asyncio
@patch("data_provider_service.redis_client")
async def test_cache_clear_empty(mock_redis):
    """Test /cache/clear when no cached queries exist"""
    mock_redis.keys.return_value = []
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.delete("/cache/clear")
    
    assert response.status_code == 200
    assert response.json()["cleared"] == 0
