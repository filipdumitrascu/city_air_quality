#!/bin/bash
# Docker Compose Stop Script - Clean Output Version

set -e

echo ""
echo "  CityAirQ - Stopping Services"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../../deploy"

# Stop and remove containers + volumes
echo "Stopping and removing containers & volumes..."
docker compose down -v 2>&1 | grep -v "^WARN" | grep -v "^Container" || true

echo ""
echo " Containers and volumes removed"
echo ""


# Ask about images
echo "Do you want to remove built images too?"
echo "This will force rebuild on next start (slower)"
echo ""
read -p "Remove images? [y/N]: " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Removing CityAirQ images..."
    
    docker rmi -f \
        deploy-data-provider-service:latest \
        deploy-database-service:latest \
        deploy-ingest-service:latest \
        deploy-routing-service:latest \
        deploy-client-message-handler:latest \
        deploy-frontend:latest \
        redis:7-alpine \
        questdb/questdb:latest
        2>/dev/null || true
    
    echo ""
    echo "Cleaning dangling images..."
    docker image prune -f 2>&1 | grep -v "^Total" || true
    
    echo ""
    echo "Cleanup complete"
    echo ""
else
    echo ""
    echo "Images kept (faster next startup)"
    echo ""
fi

echo "Services Stopped"
echo ""
echo "To start again: ./scripts/local/run.sh"
echo ""
