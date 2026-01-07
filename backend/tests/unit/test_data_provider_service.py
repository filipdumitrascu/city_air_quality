import pytest
import sys
import os
import json
from unittest.mock import patch

# Adaugă path-ul pentru a importa corect
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from microservices.data_provider_service.data_provider_service import process_message

@pytest.mark.asyncio
@patch("data_provider_service.data_provider_service.get_data_from_database")
@patch("data_provider_service.data_provider_service.PubSubClientPublisher.publish_message")
async def test_process_message_success(mock_publish, mock_get_data):
    mock_get_data.return_value = {
        "Temperature": 30.5,
        "Humidity": 55.2,
        "Pressure": 1012.3
    }

    class DummyMessage:
        def __init__(self, data):
            self.data = data
            self.ack_called = False
            self.nack_called = False

        def ack(self):
            self.ack_called = True

        def nack(self):
            self.nack_called = True

    payload = {
        "latitude": 45.764043,
        "longitude": 4.835659,
        "radius": 0,
        "layers": ["Temperature", "Humidity", "Pressure"]
    }

    message = DummyMessage(data=json.dumps(payload).encode("utf-8"))

    await process_message(message)

    assert message.ack_called is True
    assert message.nack_called is False
    mock_get_data.assert_awaited_once()
    mock_publish.assert_called_once()

    published_data = mock_publish.call_args[0][1]
    assert "Temperature" in published_data
    assert published_data["Temperature"] == 30.5
    assert "Humidity" in published_data
    assert published_data["Humidity"] == 55.2
    assert "Pressure" in published_data
    assert published_data["Pressure"] == 1012.3
