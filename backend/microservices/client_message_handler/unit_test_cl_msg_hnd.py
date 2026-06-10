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

with patch('common.message_queue_googlepubsub.pubsub_client.pubsub_v1.SubscriberClient'):
    with patch('common.message_queue_googlepubsub.pubsub_client.pubsub_v1.PublisherClient'):
        from client_message_handler import app, response_queue

from httpx import AsyncClient


# Valid ingest payload - all fields
valid_ingest_payload_full = {
    "sensor_type": "CityAirQ",
    "sensor_id": "001",
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

# Valid ingest payload - only required fields (optional default to -1)
valid_ingest_payload_minimal = {
    "sensor_type": "WearAware",
    "sensor_id": "005",
    "timestamp": 1718699260000,
    "latitude": 44.4268,
    "longitude": 26.1025
}

# Invalid ingest payload - missing required field
invalid_ingest_payload = {
    "timestamp": 1718699260000,
    "latitude": 44.4268,
    "longitude": 26.1025
    # missing sensor_type
}

# Valid results payload
valid_results_payload = {
    "latitude": 44.4268,
    "longitude": 26.1025,
    "radius": 5.0,
    "sensor_types": ["CityAirQ", "WearAware"],
    "layers": ["pm10", "pm2_5", "no2"]
}

# Valid results payload - minimal (uses defaults)
valid_results_payload_minimal = {
    "latitude": 44.4268,
    "longitude": 26.1025,
    "radius": 5.0
}

# Valid route payload
valid_route_payload = {
    "start": {"lat": 44.4268, "lon": 26.1025},
    "goal": {"lat": 44.4368, "lon": 26.0925},
    "alpha": 1.0,
    "sensor_types": ["CityAirQ", "WearAware"],
    "transport_mode": "bicycle"
}

# Mock response from Data Provider Service
mock_results_response = [
    {
        "sensor_type": "CityAirQ",
        "sensor_id": "001",
        "timestamp": "2026-03-15T10:00:00",
        "latitude": 44.4268,
        "longitude": 26.1025,
        "pm10": 42.7,
        "pm2_5": 15.3,
        "no2": 35.2
    }
]

# Mock authenticated user
mock_user = {
    "email": "test@example.com",
    "sub": "123456789"
}


# HEALTH ENDPOINT TESTS
@pytest.mark.asyncio
async def test_health_check():
    """Test /health endpoint returns healthy status"""
    with patch('client_message_handler.redis_client') as mock_redis:
        mock_redis.ping.return_value = True
        
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.get("/health")
        
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert response.json()["service"] == "client_message_handler"

@pytest.mark.asyncio
async def test_root_endpoint():
    """Test / endpoint returns service info"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/")
    
    assert response.status_code == 200
    assert response.json()["service"] == "client_message_handler"
    assert response.json()["status"] == "running"


# RESULTS ENDPOINT TESTS
@pytest.mark.asyncio
@patch("client_message_handler.redis_client")
@patch("client_message_handler.PubSubClientPublisher.publish_message")
@patch("client_message_handler.response_queue")
async def test_results_success(mock_queue, mock_publish, mock_redis):
    """Test /results/ returns data from Data Provider Service"""
    mock_redis.get.return_value = None  # Cache miss
    mock_queue.empty.return_value = False
    mock_queue.get_nowait.return_value = mock_results_response
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/results/", json=valid_results_payload)
    
    assert response.status_code == 200
    assert "data" in response.json()
    assert response.json()["cache_hit"] == False
    mock_publish.assert_called_once_with("results_service_messages", valid_results_payload)

@pytest.mark.asyncio
@patch("client_message_handler.redis_client")
async def test_results_cache_hit(mock_redis):
    """Test /results/ returns cached data when available"""
    mock_redis.get.return_value = json.dumps(mock_results_response)
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/results/", json=valid_results_payload)
    
    assert response.status_code == 200
    assert response.json()["cache_hit"] == True
    assert "data" in response.json()

@pytest.mark.asyncio
async def test_results_no_auth_required():
    """Test /results/ works without authentication"""
    with patch("client_message_handler.redis_client") as mock_redis:
        with patch("client_message_handler.response_queue") as mock_queue:
            mock_redis.get.return_value = json.dumps(mock_results_response)
            
            async with AsyncClient(app=app, base_url="http://test") as ac:
                response = await ac.post("/results/", json=valid_results_payload)
            
            assert response.status_code == 200

@pytest.mark.asyncio
async def test_results_invalid_payload():
    """Test /results/ with invalid payload - should return 422"""
    invalid_payload = {"latitude": 44.4268}  # Missing required fields
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/results/", json=invalid_payload)
    
    assert response.status_code == 422

@pytest.mark.asyncio
@patch("client_message_handler.redis_client")
@patch("client_message_handler.PubSubClientPublisher.publish_message")
@patch("client_message_handler.response_queue")
async def test_results_with_layers_filter(mock_queue, mock_publish, mock_redis):
    """Test /results/ with specific layers filter"""
    mock_redis.get.return_value = None
    mock_queue.empty.return_value = False
    mock_queue.get_nowait.return_value = mock_results_response
    
    payload_with_layers = {
        "latitude": 44.4268,
        "longitude": 26.1025,
        "radius": 5.0,
        "layers": ["pm10"]
    }
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/results/", json=payload_with_layers)
    
    assert response.status_code == 200
    published_payload = mock_publish.call_args[0][1]
    assert published_payload["layers"] == ["pm10"]


# ROUTE ENDPOINT TESTS
@pytest.mark.asyncio
@patch("client_message_handler.httpx.AsyncClient.post")
async def test_route_success(mock_post):
    """Test /route/ forwards request to Routing Service"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "type": "FeatureCollection",
        "features": [],
        "properties": {"distance": 1500, "pollution_score": 0.3}
    }
    mock_post.return_value = mock_response
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/route/", json=valid_route_payload)
    
    assert response.status_code == 200
    assert "type" in response.json()

@pytest.mark.asyncio
async def test_route_no_auth_required():
    """Test /route/ works without authentication"""
    with patch("client_message_handler.httpx.AsyncClient.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"type": "FeatureCollection"}
        mock_post.return_value = mock_response
        
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post("/route/", json=valid_route_payload)
        
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_route_invalid_payload():
    """Test /route/ with invalid payload - should return 422"""
    invalid_payload = {"start": {"lat": 44.4268}}
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/route/", json=invalid_payload)
    
    assert response.status_code == 422

@pytest.mark.asyncio
@patch("client_message_handler.httpx.AsyncClient.post")
async def test_route_with_sensor_types(mock_post):
    """Test /route/ with sensor_types filter"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"type": "FeatureCollection"}
    mock_post.return_value = mock_response
    
    payload_with_sensors = {
        "start": {"lat": 44.4268, "lon": 26.1025},
        "goal": {"lat": 44.4368, "lon": 26.0925},
        "sensor_types": ["SPO-RO", "CityAirQ", "WearAware"]
    }
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/route/", json=payload_with_sensors)
    
    assert response.status_code == 200


# CACHE MANAGEMENT TESTS
@pytest.mark.asyncio
@patch("client_message_handler.redis_client")
async def test_cache_stats(mock_redis):
    """Test /cache/stats returns Redis statistics"""
    mock_redis.info.return_value = {
        "total_commands_processed": 100,
        "keyspace_hits": 80,
        "keyspace_misses": 20
    }
    mock_redis.keys.return_value = ["key1", "key2"]
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/cache/stats")
    
    assert response.status_code == 200
    assert response.json()["connected"] == True
    assert response.json()["cached_queries"] == 2

@pytest.mark.asyncio
@patch("client_message_handler.redis_client")
async def test_cache_clear(mock_redis):
    """Test /cache/clear removes cached queries"""
    mock_redis.keys.return_value = ["client_query:abc", "client_query:def"]
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.delete("/cache/clear")
    
    assert response.status_code == 200
    assert response.json()["cleared"] == 2
    mock_redis.delete.assert_called_once()
