# CityAirQ

Backend infrastructure and AI model for air quality monitoring in Bucharest.

## Contributors

* [Filip Dumitrascu](https://github.com/filipdumitrascu)
* [Bianca Dumitru](https://github.com/dbianca0907)

## Quick Start

### Configuration

Make scripts executable:
```bash
chmod +x scripts/*.sh
```

### Local Development (Docker)

Start all services locally:
```bash
./scripts/docker-start.sh
```

Stop services:
```bash
./scripts/docker-stop.sh
```

View logs:
```bash
./scripts/docker-logs.sh [service-name]
```

Clean up:
```bash
./scripts/docker-clean.sh
```

### Production Deployment (Kubernetes)

Setup Kubernetes access:
```bash
./scripts/k8s-setup.sh
```

Deploy all services:
```bash
./scripts/k8s-deploy.sh
```

Check status:
```bash
./scripts/k8s-status.sh
```

View logs:
```bash
./scripts/k8s-logs.sh <pod-name>
```

Delete all services:
```bash
./scripts/k8s-delete.sh
```

### Build and Push Images

Build and push Docker images to Google Artifact Registry:
```bash
./scripts/build-push.sh
```

## Documentation

## Architecture

- **Microservices**: FastAPI-based services for data ingestion, processing, and routing
- **Message Queue**: Google Pub/Sub for async communication
- **Database**: QuestDB for time-series data
- **Cache**: Redis for route caching
- **Orchestration**: Kubernetes (GKE)
- **Monitoring**: Prometheus + Grafana + Loki

## Services

- `client-message-handler`: Public API endpoint (port 8000)
- `database-service`: Database interface (port 8002)
- `ingest-service`: Data ingestion
- `data-provider-service`: Data retrieval (port 8001)
- `routing-service`: A* pathfinding for least polluted routes (port 8003)
- `redis`: Cache layer (port 6379)
