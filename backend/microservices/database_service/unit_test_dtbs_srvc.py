import pytest
import sys
import os
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

sys.modules['psycopg2'] = MagicMock()
sys.modules['psycopg2.pool'] = MagicMock()

# Mock config to avoid DATABASE_URL requirement
mock_config = MagicMock()
mock_config.get_db_config.return_value = {
    'host': 'localhost',
    'port': 8812,
    'user': 'admin',
    'password': 'quest',
    'dbname': 'qdb'
}
sys.modules['config'] = mock_config


from database_service import app
from db import insert_data, fetch_data


# Test Data
valid_payload = {
    "clientId": "clientId-a12b34cd5678ef90",
    "timestamp": "2024-06-17T06:06:00+02:00",
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


# /add_data/ endpoint
@pytest.mark.asyncio
@patch("database_service.insert_data")
async def test_add_data_success(mock_insert):
    """Test successful data insertion"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/add_data/", json=valid_payload)
    
    assert response.status_code == 200
    assert response.json() == {"success": True}
    mock_insert.assert_called_once()
    
    # Verify correct parameters passed to insert_data
    call_args = mock_insert.call_args[0][0]
    assert call_args[0] == "clientId-a12b34cd5678ef90"  # clientId
    assert call_args[2] == 45.764043  # latitude
    assert call_args[4] == 30.5  # Temperature


@pytest.mark.asyncio
async def test_add_data_invalid_payload():
    """Test validation error with missing required field"""
    invalid_payload = valid_payload.copy()
    del invalid_payload["data"]  # Remove required field

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/add_data/", json=invalid_payload)
    
    # FastAPI returns 422 for validation errors
    assert response.status_code == 422


@pytest.mark.asyncio
@patch("database_service.insert_data")
async def test_add_data_database_error(mock_insert):
    """Test handling of database insertion error"""
    # Mock database raising exception
    mock_insert.side_effect = Exception("Database connection failed")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/add_data/", json=valid_payload)
    
    assert response.status_code == 400
    assert "Error adding data" in response.text



# /get_data/ endpoint
@pytest.mark.asyncio
@patch("database_service.fetch_data")
async def test_get_data_success(mock_fetch):
    """Test successful data retrieval"""
    # Mock database response
    mock_fetch.return_value = [
        [
            "clientId-a12b34cd5678ef90",
            "1970-01-20T23:24:59.260000",
            45.764043,
            4.835659,
            30.5,   # Temperature
            55.2,   # Humidity
            1012.3  # Pressure
        ]
    ]

    params = {
        "latitude": 45.764043,
        "longitude": 4.835659,
        "radius": 5,
        "layers": ["Temperature", "Humidity", "Pressure"]
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/get_data/", params=params)

    assert response.status_code == 200
    assert isinstance(response.json(), list)

    result_row = response.json()[0]
    assert result_row[4] == 30.5   # Temperature
    assert result_row[5] == 55.2   # Humidity
    assert result_row[6] == 1012.3 # Pressure

    mock_fetch.assert_called_once()


@pytest.mark.asyncio
@patch("database_service.fetch_data")
async def test_get_data_with_default_layers(mock_fetch):
    """Test data retrieval without specifying layers (should use all)"""
    mock_fetch.return_value = [["sensor-001", "2024-01-01", 44.43, 26.10, 25.0]]

    params = {
        "latitude": 44.43,
        "longitude": 26.10,
        "radius": 10
        # No layers specified - should default to all
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/get_data/", params=params)

    assert response.status_code == 200
    
    # Verify all layers were requested
    call_args = mock_fetch.call_args[0][0]
    expected_layers = ["Temperature", "Humidity", "Pressure", "Altitude", "CO2", "PM1_0", "PM2_5", "PM10"]
    assert call_args[0] == expected_layers


@pytest.mark.asyncio
@patch("database_service.fetch_data")
async def test_get_data_no_results(mock_fetch):
    """Test handling when no data found (404)"""
    from fastapi import HTTPException
    
    # Mock database raising 404
    mock_fetch.side_effect = HTTPException(status_code=404, detail="No data found")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/get_data/", params={
            "latitude": 45.76,
            "longitude": 4.83,
            "radius": 10
        })
    
    assert response.status_code == 404
    assert "No data found" in response.text


@pytest.mark.asyncio
@patch("database_service.fetch_data")
async def test_get_data_database_error(mock_fetch):
    """Test handling of database query error (500)"""
    # Mock database raising generic exception
    mock_fetch.side_effect = Exception("DB connection lost")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/get_data/", params={
            "latitude": 45.76,
            "longitude": 4.83,
            "radius": 10
        })
    
    assert response.status_code == 500
    assert "Error fetching measurements" in response.text
