### DATABASE SERVICE

 - timestamp should be converted before sending
 - for get it should send the selected layers directly

for running the server: uvicorn main:app --reload

ingest:

{
  "clientId": "clientId-ec85695bd6a1fdaa",
  "timestamp": "2024-06-17T06:06:00+02:00",
  "location": {
    "latitude": 23.384256,
    "longitude": 25.0866048
  },
  "data": [
    {
      "dimension": "Temperature",
      "value": 35.827482
    },
    {
      "dimension": "Humidity",
      "value": 67.626262
    },
    {
      "dimension": "Pressure",
      "value": 1006.28282
    },
    {
      "dimension": "Altitude",
      "value": 59.222
    },
    {
      "dimension": "CO2",
      "value": 805
    },
    {
      "dimension": "PM1.0",
      "value": 16.181188
    },
    {
      "dimension": "PM2.5",
      "value": 19.28282
    },
    {
      "dimension": "PM10",
      "value": 20.1111
    }
  ]
}

get:

{
  "latitude": 23.384256,
  "longitude": 25.0866048,
  "radius": 0,
  "layers": ["Temperature", "Humidity", "Pressure", "Altitude", "CO2", "PM1_0", "PM2_5", "PM10"]
}

returned:

[
    [
        "clientId-ec85695bd6a1fdaa",
        "2024-06-17T04:06:00",
        23.384256,
        25.0866048,
        35.827482,
        67.626262,
        1006.28282,
        59.222,
        805.0,
        16.181188,
        19.28282,
        20.1111
    ]
]