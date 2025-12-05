#!/bin/bash

# Docker Compose Stop Script
# Stops all running containers

set -e

echo "Stopping CityAirQ Docker services..."

cd backend

# Stop services
docker compose down

echo "All services stopped"
