import pytest
import json
import sys
import os
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from client_message_handler import app, response_queue

# Test data
valid_payload = {
    "clientId": "clientId-a12b34cd5678ef90",
    "timestamp": 1718699260,
    "location": {"latitude": 45.764043, "longitude": 4.835659},
    "data": [{"dimension": "Temperature", "value": 30.5}]
}

test_payload = {
    "latitude": 45.764043,
    "longitude": 4.835659,
    "radius": 0,
    "layers": ["Temperature"]
}

test_response = json.dumps([
    [
        "clientId-a12b34cd5678ef90",
        "1970-01-20T23:24:59.260000",
        45.764043,
        4.835659,
        30.5
    ]
])


@pytest.mark.asyncio
@patch("client_message_handler.authorize", return_value=None)
@patch("client_message_handler.PubSubClientPublisher.publish_message")
async def test_ingest_data_success(mock_publish, mock_auth):
    """Test /ingest/ endpoint publishes message to PubSub"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/ingest/", json=valid_payload, headers={"x-auth-token": "test-token"})

    assert response.status_code == 200
    assert response.json()["details"] == "Data successfully added in the database"
    mock_auth.assert_awaited_once()
    mock_publish.assert_called_once_with("ingest_service_messages", valid_payload)


@pytest.mark.asyncio
@patch("client_message_handler.authorize", new_callable=AsyncMock)
@patch("client_message_handler.PubSubClientPublisher.publish_message")
@patch("client_message_handler.response_queue")
async def test_get_data_success(mock_queue, mock_publish, mock_authorize):
    """Test /results/ endpoint retrieves data from response queue"""
    mock_authorize.return_value = None
    mock_queue.empty.return_value = False
    mock_queue.get_nowait.return_value = test_response

    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.request(
            method="POST",
            url="/results/",
            headers={"x-auth-token": "dummy-token"},
            content=json.dumps(test_payload)
        )

    assert response.status_code == 200
    assert "data" in response.json()
    assert isinstance(response.json()["data"], list)
    assert response.json()["data"][0][0] == "clientId-a12b34cd5678ef90"
