import pytest
import sys
import os
import json
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ingest_service.ingest_service import process_message

@pytest.mark.asyncio
@patch("ingest_service.ingest_service.send_data_to_database")
async def test_process_message_success(mock_send):
    mock_send.return_value = {"success": True}

    # Simulăm un mesaj Pub/Sub
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
    "clientId": "clientId-a12b34cd5678ef90",
    "timestamp": 1718699260,
    "location": {
      "latitude": 45.764043,
      "longitude": 4.835659
    },
    "data": [
      {
        "dimension": "Temperature",
        "value": 30.5
      },
      {
        "dimension": "Humidity",
        "value": 55.2
      },
      {
        "dimension": "Pressure",
        "value": 1012.3
      },
      {
        "dimension": "Altitude",
        "value": 120.4
      },
      {
        "dimension": "CO2",
        "value": 600
      },
      {
        "dimension": "PM1.0",
        "value": 10.1
      },
      {
        "dimension": "PM2.5",
        "value": 15.3
      },
      {
        "dimension": "PM10",
        "value": 18.2
      }
    ]
  }

    message = DummyMessage(data=json.dumps(payload).encode("utf-8"))

    await process_message(message)

    # Verificări
    assert message.ack_called is True
    assert message.nack_called is False
    mock_send.assert_awaited_once()
    args, _ = mock_send.call_args
    processed_data = args[0]
    assert processed_data["clientId"] == "clientId-a12b34cd5678ef90"
    assert processed_data["timestamp"].endswith("Z") or "T" in processed_data["timestamp"]
