# Redis Cache for CityAirQ

## Configuration

Redis este folosit pentru:
1. Pre-calculated route cache (TTL 15 min)
2. Graph cache pollution (TTL 30 min)
3. Session data (future)

## Structure Keys
```
route:{hash}:{time_window}     # Calculated routes
graph:{time_window}h           # Graphs pre-built
stats:routing:hits             # Statistics cache hits
stats:routing:misses           # Statistics cache misses
```

## Local Development
```bash
# Start Redis
docker-compose up redis

# Connect to Redis CLI
docker exec -it cityairq-redis redis-cli

# Check keys
KEYS *

# Monitor în real-time
MONITOR
```

## Production

In GKE, we use Redis with persistent volumes for cache warm starts.

## Monitoring

Redis metrics are exposed at:
- Prometheus: `redis_exporter:9121/metrics`
- Grafana dashboard: Redis Overview
