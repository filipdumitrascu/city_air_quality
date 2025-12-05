#!/bin/bash

# Docker Compose Start Script
# Builds and starts all microservices locally

set -e

echo "Starting CityAirQ Docker services..."

cd backend

# Build and start services
echo "Building and starting services..."
docker compose up -d --build

# Wait for services to be healthy
echo "Waiting for services to be ready..."
sleep 10

# Check service status
echo "Checking service status..."
docker compose ps

# Show logs for quick verification
echo "Recent logs:"
docker compose logs --tail=20

echo "Docker services started successfully"
echo "Access services at:"
echo "  - Client Handler: http://localhost:8000"
echo "  - Data Provider: http://localhost:8001"
echo "  - Database Service: http://localhost:8002"
echo "  - Routing Service: http://localhost:8003"
echo "  - Redis: localhost:6379"
