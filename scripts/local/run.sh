#!/bin/bash
# Docker Compose Start Script
# Builds and starts all CityAirQ services locally

set -e

# Fix messy terminal output
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1
export BUILDKIT_PROGRESS=plain

echo ""
echo "  CityAirQ - Starting Services"
echo ""

# Go to backend directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../../backend"

# Check if credentials.json exists
if [ ! -f "credentials.json" ]; then
    echo "WARNING: credentials.json not found"
    echo "Some services may fail without Google Cloud credentials"
    echo ""
fi

# Build and start services
echo "Building and starting services..."
docker compose up -d --build
#docker compose build --progress=plain
#docker compose up --no-color < /dev/null


echo ""
echo "Waiting for services to be ready..."
echo ""

# Wait for Redis
echo -n "Redis..."
sleep 3
if docker exec cityairq-redis redis-cli ping > /dev/null 2>&1; then
    echo " ready"
else
    echo " not responding"
fi

# QuestDB - just check container is running
echo -n "QuestDB..."
if docker ps | grep -q cityairq-questdb; then
    echo " container running (may take 30-60s)"
else
    echo " container not found"
fi

# Wait for Database Service
echo -n "Database Service..."
sleep 5
if curl -sf http://localhost:8001/health > /dev/null 2>&1; then
    echo " ready"
else
    echo " not responding"
fi

# Wait for Routing Service
echo -n "Routing Service..."
sleep 5
if curl -sf http://localhost:8080/health > /dev/null 2>&1; then
    echo " ready"
else
    echo " not responding"
fi

echo ""
echo "  Service Status"
docker compose ps

echo ""
echo "  Access Services"
echo "  QuestDB Web UI:     http://localhost:9000"
echo "  Database Service:   http://localhost:8001/health"
echo "  Routing Service:    http://localhost:8080/health"
echo "  Redis:              localhost:6379"
echo ""
echo "  Useful Commands"
echo "  View logs:      docker compose logs -f <service>"
echo "  Stop services:  docker compose down"
echo "  Full cleanup:   ./scripts/local/stop.sh -y"
echo ""
