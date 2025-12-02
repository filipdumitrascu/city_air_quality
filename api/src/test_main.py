import pytest
from httpx import AsyncClient
from main import app

@pytest.mark.asyncio
async def test_ingest_data():
    """ Testează endpoint-ul de ingestie cu date simulate """
    fake_payload = {
        "clientId": "test-device-1",
        "timestamp": 1708600000000,
        "location": {
            "latitude": 44.431278,
            "longitude": 26.112345
        },
        "data": [
            {"dimension": "temperature", "value": 22.5},
            {"dimension": "humidity", "value": 55.1}
        ]
    }

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/ingest/", json=fake_payload)

    assert response.status_code == 200
    assert response.json() == {"success": True}

@pytest.mark.asyncio
async def test_get_measurements():
    """ Testează endpoint-ul de obținere a măsurătorilor """
    params = {
        "latitude": 44.431278,
        "longitude": 26.112345,
        "radius": 500,
        "layers": ["temperature", "humidity"]
    }

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/measurements/", params=params)

    assert response.status_code == 200
    assert "data" in response.json()
    assert isinstance(response.json()["data"], list)
