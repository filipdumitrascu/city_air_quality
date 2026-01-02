#!/bin/bash
# Docker Cleanup Script - Interactive
# Stops containers, removes volumes, optionally removes images

set -e

echo "  CityAirQ - Docker Cleanup"
echo ""

# Go to backend directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../../backend"

# Stop and remove containers + volumes
echo "Stopping and removing containers & volumes..."
docker compose down -v

echo ""
echo "Containers and volumes removed!"
echo ""

# Ask about images
echo "Do you want to remove built images too?"
echo "This will force rebuild on next start (slower)"
read -p "Remove images? (y/n): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Removing CityAirQ images..."

    docker rmi -f \
        backend-data-provider-service:latest \
        backend-database-service:latest \
        backend-ingest-service:latest \
        backend-routing-service:latest \
        redis:7-alpine \
        questdb/questdb:latest
        2>/dev/null || true
    
    echo ""
    echo "Images removed!"
    echo ""
    
    # Clean dangling images
    echo "Cleaning dangling images..."
    docker image prune -f
    
    echo ""
else
    echo ""
    echo "Images kept (faster next startup)"
fi

echo ""
echo "  Cleanup Complete!"
echo ""
echo "To start fresh: ./scripts/local/docker-run.sh"
echo ""
