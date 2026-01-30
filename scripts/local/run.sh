#!/bin/bash
# Docker Compose Start Script - Clean Output Version

set -e

# Clean terminal output settings
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1
export BUILDKIT_PROGRESS=plain

echo ""
echo "  CityAirQ - Starting Services"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../../deploy"

# Check credentials
if [ ! -f "credentials.json" ]; then
    echo "WARNING: credentials.json not found"
    echo ""
fi

# Build and start services - CLEAN WAY
echo "Building and starting services..."
echo ""

docker compose up -d --build

echo "Containers started"
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

# Wait for QuestDB
echo -n "QuestDB..."
if docker ps | grep -q cityairq-questdb; then
    echo " ready"
else
    echo " container not found"
fi

sleep 5

# Create QuestDB schema
echo -n "Checking QuestDB schema..."

python3 << 'PYTHON_SCRIPT' 2>&1 | grep -v "^$"
import psycopg2
import sys

try:
    conn = psycopg2.connect('postgresql://admin:quest@localhost:8812/qdb')
    cur = conn.cursor()

    # Create table
    with open('config/questdb/schema.sql', 'r') as f:
        schema = f.read()
    cur.execute(schema)
    conn.commit()
    print("table created")
    
    cur.close()
    conn.close()
except Exception as e:
    print(f"error: {e}")
    sys.exit(1)
PYTHON_SCRIPT


# Wait for Database Service
echo -n "Database Service..."
if curl -sf http://localhost:8001/docs > /dev/null 2>&1; then
    echo " ready"
else
    echo " not responding"
fi

# Wait for Routing Service
echo -n "Routing Service..."
if curl -sf http://localhost:8080/docs > /dev/null 2>&1; then
    echo " ready"
else
    echo " not responding"
fi

# Insert in table 
python3 ../backend/config/questdb/import_from_excel.py ../backend/config/questdb/cityairq_sensor_data.xlsx


echo ""
echo " Service Status"
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || docker compose ps

echo ""
echo "  Access Services"
echo "  Frontend            http://localhost:3000"
echo "  QuestDB Web:        http://localhost:9000"
echo "  Client Handler:     http://localhost:8000/docs"
echo "  Database Service:   http://localhost:8001/docs"
echo "  Data Provider:      http://localhost:8002/docs"
echo "  Ingest Service:     http://localhost:8003/docs"
echo "  Routing Service:    http://localhost:8080/docs"
echo "  Redis:              localhost:6379"
echo ""
echo "  Useful Commands"
echo "  View logs:      docker compose logs -f <service>"
echo "  Stop services:  docker compose down"
echo "  Full cleanup:   ./scripts/local/stop.sh -y"
echo ""
