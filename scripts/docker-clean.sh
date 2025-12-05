#!/bin/bash

# Docker Cleanup Script
# Removes containers, volumes, and images

set -e

echo "Cleaning up Docker resources..."

cd backend

# Stop and remove containers, networks, volumes
docker compose down -v

# Remove dangling images
echo "Removing unused images..."
docker image prune -f

echo "Docker cleanup complete"
