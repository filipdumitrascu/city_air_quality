# Routing Service

Pollution-aware navigation for CityAirQ.

## Transport Modes

| Mode | Implementation | Use Case |
|------|----------------|----------|
| `foot` | A* on pollution grid | Walking routes |
| `bicycle` | Google Routes API | Cycling (uses DRIVE mode, BICYCLE unavailable in Romania) |

## Pollutants Used

Only **PM10** and **PM2.5** - measured by all sensors (fixed, CityAirQ, WearAware).

NO2 excluded because WearAware doesn't measure it.

Values of `-1` are ignored in AQI calculation.

## API

```bash
# Calculate route
POST /route
{
  "start": {"lat": 44.4268, "lon": 26.1025},
  "goal": {"lat": 44.4368, "lon": 26.0925},
  "alpha": 0.5,
  "transport_mode": "foot",
  "sensor_types": ["fixed", "mobile"],
  "heuristic": "haversine"
}

# Health check
GET /health

# Available heuristics (foot mode)
GET /heuristics

# Cache management
GET /cache/stats
DELETE /cache/clear
```

**alpha**: `0.0` = fastest route, `1.0` = cleanest route

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `redis-service` | Redis host |
| `DATABASE_SERVICE_URL` | `http://database-service:8000` | Database service |
| `GOOGLE_MAPS_API_KEY` | - | Required for bicycle mode |
| `GRID_RESOLUTION` | `0.002` | ~220m grid cells |

## Run

```bash
uvicorn routing_service:app --host 0.0.0.0 --port 8000
```

## Test

```bash
pytest tests/ -v
```
