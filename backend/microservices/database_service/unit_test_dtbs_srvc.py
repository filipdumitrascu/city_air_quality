import pytest
from httpx import AsyncClient
from httpx import ASGITransport
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "database_service")))
from microservices.database_service.database_service import app
from unittest.mock import patch

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

@pytest.mark.asyncio
@patch("microservices.database_service.insert_data")
async def test_add_data_success(mock_insert):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/add_data/", json=valid_payload)
    assert response.status_code == 200
    assert response.json() == {"success": True}
    mock_insert.assert_called_once()

@pytest.mark.asyncio
async def test_add_data_invalid_payload():
    invalid_payload = valid_payload.copy()
    del invalid_payload["data"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/add_data/", json=invalid_payload)
    assert response.status_code == 422  # FastAPI va da eroare de validare

@pytest.mark.asyncio
@patch("microservices.database_service.fetch_data")
async def test_get_data_success(mock_fetch):
    mock_fetch.return_value = [
        [
            "clientId-a12b34cd5678ef90",
            "1970-01-20T23:24:59.260000",
            45.764043,
            4.835659,
            30.5, 
            55.2,
            1012.3
        ]
    ]

    params = {
        "latitude": 45.764043,
        "longitude": 4.835659,
        "radius": 0,
        "layers": ["Temperature", "Humidity", "Pressure"]
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/get_data/", params=params)

    assert response.status_code == 200
    assert isinstance(response.json(), list)

    result_row = response.json()[0]

    assert result_row[4] == 30.5 
    assert result_row[5] == 55.2 
    assert result_row[6] == 1012.3

    mock_fetch.assert_called_once()


@pytest.mark.asyncio
@patch("db.fetch_data")
async def test_get_data_db_error(mock_fetch):
    mock_fetch.side_effect = Exception("DB failure")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/get_data/", params={
            "latitude": 45.76,
            "longitude": 4.83,
            "radius": 10
        })
    assert response.status_code == 500
    assert "Error fetching measurements" in response.text
