import pytest
import sys
import os
import json
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport

# Setup mocks before imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

sys.modules['psycopg2'] = MagicMock()
sys.modules['psycopg2.pool'] = MagicMock()

mock_config = MagicMock()
mock_config.get_db_config.return_value = {
    'host': 'localhost',
    'port': 8812,
    'user': 'admin',
    'password': 'quest',
    'dbname': 'qdb'
}
sys.modules['config'] = mock_config

from database_service import app, AVAILABLE_LAYERS
from db import insert_data, fetch_data


# TEST DATA (matching pollution_data schema)
valid_insert_payload_full = {
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

valid_insert_payload_minimal = {
    "sensor_id": "WearAware_005",
    "sensor_type": "mobile",
    "timestamp": 1718699260000,
    "latitude": 44.4268,
    "longitude": 26.1025
    # All optional fields will default to -1
}

mock_fetch_response = [
    {
        "sensor_id": "CityAirQ_001",
        "sensor_type": "mobile",
        "timestamp": "2026-03-15T10:00:00",
        "latitude": 44.4268,
        "longitude": 26.1025,
        "pm10": 42.7,
        "pm2_5": 15.3,
        "no2": 35.2
    },
    {
        "sensor_id": "CityAirQ_002",
        "sensor_type": "mobile",
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
    with patch('database_service.redis_client') as mock_redis:
        mock_redis.ping.return_value = True
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/health")
        
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert response.json()["service"] == "database_service"

@pytest.mark.asyncio
async def test_root_endpoint():
    """Test / endpoint returns service info"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/")
    
    assert response.status_code == 200
    assert response.json()["service"] == "database_service"
    assert response.json()["status"] == "running"



# ADD DATA ENDPOINT TESTS
@pytest.mark.asyncio
@patch("database_service.insert_data")
async def test_add_data_success_full(mock_insert):
    """Test /add_data/ with all fields"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/add_data/", json=valid_insert_payload_full)
    
    assert response.status_code == 200
    assert response.json()["success"] == True
    assert response.json()["sensor_id"] == "CityAirQ_001"
    mock_insert.assert_called_once()
    
    # Verify all 17 params passed correctly
    call_args = mock_insert.call_args[0][0]
    assert len(call_args) == 17
    assert call_args[0] == "CityAirQ_001"  # sensor_id
    assert call_args[1] == "mobile"  # sensor_type
    assert call_args[15] == 42.7  # pm10


@pytest.mark.asyncio
@patch("database_service.insert_data")
async def test_add_data_success_minimal(mock_insert):
    """Test /add_data/ with only required fields - optional should default to -1"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/add_data/", json=valid_insert_payload_minimal)
    
    assert response.status_code == 200
    assert response.json()["success"] == True
    
    # Verify optional fields defaulted to -1
    call_args = mock_insert.call_args[0][0]
    assert call_args[5] == -1  # altitude
    assert call_args[15] == -1  # pm10
    assert call_args[16] == -1  # vocs


@pytest.mark.asyncio
async def test_add_data_missing_required():
    """Test /add_data/ with missing required field - should return 422"""
    invalid_payload = {
        "sensor_type": "mobile",
        "timestamp": 1718699260000,
        "latitude": 44.4268,
        "longitude": 26.1025
        # Missing sensor_id
    }
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/add_data/", json=invalid_payload)
    
    assert response.status_code == 422


@pytest.mark.asyncio
@patch("database_service.insert_data")
async def test_add_data_database_error(mock_insert):
    """Test /add_data/ database error handling"""
    mock_insert.side_effect = Exception("Connection failed")
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/add_data/", json=valid_insert_payload_full)
    
    assert response.status_code == 400
    assert "Error adding data" in response.text



# GET DATA ENDPOINT TESTS
@pytest.mark.asyncio
@patch("database_service.redis_client")
@patch("database_service.fetch_data")
async def test_get_data_success(mock_fetch, mock_redis):
    """Test /get_data/ successful query"""
    mock_redis.get.return_value = None  # Cache miss
    mock_fetch.return_value = mock_fetch_response
    
    params = {
        "latitude": 44.4268,
        "longitude": 26.1025,
        "radius": 5.0,
        "layers": ["pm10", "pm2_5", "no2"],
        "sensor_types": ["mobile"]
    }
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/get_data/", params=params)
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["sensor_id"] == "CityAirQ_001"

@pytest.mark.asyncio
@patch("database_service.redis_client")
async def test_get_data_cache_hit(mock_redis):
    """Test /get_data/ returns cached result"""
    mock_redis.get.return_value = json.dumps(mock_fetch_response)
    
    params = {
        "latitude": 44.4268,
        "longitude": 26.1025,
        "radius": 5.0
    }
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/get_data/", params=params)
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

@pytest.mark.asyncio
@patch("database_service.redis_client")
@patch("database_service.fetch_data")
async def test_get_data_default_layers(mock_fetch, mock_redis):
    """Test /get_data/ without layers - should use all available"""
    mock_redis.get.return_value = None
    mock_fetch.return_value = mock_fetch_response
    
    params = {
        "latitude": 44.4268,
        "longitude": 26.1025,
        "radius": 5.0
        # No layers specified
    }
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/get_data/", params=params)
    
    assert response.status_code == 200
    
    # Verify all layers were requested
    call_args = mock_fetch.call_args[0][0]
    assert call_args[0] == AVAILABLE_LAYERS

@pytest.mark.asyncio
@patch("database_service.redis_client")
@patch("database_service.fetch_data")
async def test_get_data_default_sensor_types(mock_fetch, mock_redis):
    """Test /get_data/ without sensor_types - should default to mobile"""
    mock_redis.get.return_value = None
    mock_fetch.return_value = mock_fetch_response
    
    params = {
        "latitude": 44.4268,
        "longitude": 26.1025,
        "radius": 5.0,
        "layers": ["pm10"]
    }
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/get_data/", params=params)
    
    assert response.status_code == 200
    
    call_args = mock_fetch.call_args[0][0]
    assert call_args[5] == ["mobile"]

@pytest.mark.asyncio
@patch("database_service.redis_client")
@patch("database_service.fetch_data")
async def test_get_data_fixed_sensors(mock_fetch, mock_redis):
    """Test /get_data/ with fixed sensor type"""
    mock_redis.get.return_value = None
    mock_fetch.return_value = mock_fetch_response
    
    params = {
        "latitude": 44.4268,
        "longitude": 26.1025,
        "radius": 5.0,
        "sensor_types": ["fixed"]
    }
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/get_data/", params=params)
    
    assert response.status_code == 200
    
    call_args = mock_fetch.call_args[0][0]
    assert call_args[5] == ["fixed"]

@pytest.mark.asyncio
@patch("database_service.redis_client")
@patch("database_service.fetch_data")
async def test_get_data_no_results(mock_fetch, mock_redis):
    """Test /get_data/ when no data found - returns 404"""
    from fastapi import HTTPException
    
    mock_redis.get.return_value = None
    mock_fetch.side_effect = HTTPException(status_code=404, detail="No data found")
    
    params = {
        "latitude": 44.4268,
        "longitude": 26.1025,
        "radius": 5.0
    }
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/get_data/", params=params)
    
    assert response.status_code == 404
    assert "No data found" in response.text

@pytest.mark.asyncio
@patch("database_service.redis_client")
@patch("database_service.fetch_data")
async def test_get_data_database_error(mock_fetch, mock_redis):
    """Test /get_data/ database error handling"""
    mock_redis.get.return_value = None
    mock_fetch.side_effect = Exception("Connection lost")
    
    params = {
        "latitude": 44.4268,
        "longitude": 26.1025,
        "radius": 5.0
    }
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/get_data/", params=params)
    
    assert response.status_code == 500



# CACHE MANAGEMENT TESTS
@pytest.mark.asyncio
@patch("database_service.redis_client")
async def test_cache_stats(mock_redis):
    """Test /cache/stats returns statistics"""
    mock_redis.info.side_effect = [
        {"total_commands_processed": 100, "keyspace_hits": 80, "keyspace_misses": 20},
        {"used_memory": 1024 * 1024 * 5}  # 5MB
    ]
    mock_redis.keys.return_value = ["key1", "key2"]
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/cache/stats")
    
    assert response.status_code == 200
    assert response.json()["connected"] == True
    assert response.json()["cached_queries"] == 2

@pytest.mark.asyncio
@patch("database_service.redis_client")
async def test_cache_clear(mock_redis):
    """Test /cache/clear removes cached queries"""
    mock_redis.keys.return_value = ["db_query:abc", "db_query:def"]
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete("/cache/clear")
    
    assert response.status_code == 200
    assert response.json()["cleared"] == 2
    mock_redis.delete.assert_called_once()

@pytest.mark.asyncio
@patch("database_service.redis_client")
async def test_cache_clear_empty(mock_redis):
    """Test /cache/clear when no cached queries"""
    mock_redis.keys.return_value = []
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete("/cache/clear")
    
    assert response.status_code == 200
    assert response.json()["cleared"] == 0
