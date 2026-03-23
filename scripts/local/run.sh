#!/bin/bash
# Docker Compose Start Script

set -e

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
    echo "ERROR: credentials.json not found in deploy/"
    echo "Copy your Google Cloud credentials to deploy/credentials.json"
    exit 1
fi

# Check if ports are in use
for port in 9000 8812 8000 8001 8080 3000 6379; do
    if lsof -i :$port > /dev/null 2>&1; then
        echo "WARNING: Port $port is in use. Attempting to free it..."
        # Try to kill the process using the port
        fuser -k $port/tcp 2>/dev/null || true
        sleep 1
    fi
done


# Build and start services
echo "Building and starting services..."
echo ""

docker compose up -d --build

echo "Containers started"
echo ""

echo "Waiting for services to be ready..."
echo ""


# Wait for Redis
echo -n "Redis..."
for i in {1..10}; do
    if docker exec cityairq-redis redis-cli ping > /dev/null 2>&1; then
        echo " ready"
        break
    fi
    sleep 2
done

# Wait for QuestDB
echo -n "QuestDB..."
if docker ps | grep -q cityairq-questdb; then
    echo " ready"
else
    echo " container not found"
fi

# Create QuestDB schema
echo -n "Checking QuestDB schema..."

python3 << 'PYTHON_SCRIPT' 2>&1 | grep -v "^$"
import psycopg2
import sys

try:
    conn = psycopg2.connect('postgresql://admin:quest@localhost:8812/qdb')
    cur = conn.cursor()

    # Create table
    with open('../backend/config/questdb/schema.sql', 'r') as f:
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

# Wait for services to start
sleep 5

# Wait for Database Service
echo -n "Database Service..."
for i in {1..15}; do
    if curl -sf http://localhost:8001/health > /dev/null 2>&1; then
        echo " ready"
        break
    fi
    if [ $i -eq 15 ]; then
        echo " timeout"
    fi
    sleep 2
done

# Wait for Routing Service
echo -n "Routing Service..."
for i in {1..15}; do
    if curl -sf http://localhost:8080/health > /dev/null 2>&1; then
        echo " ready"
        break
    fi
    if [ $i -eq 15 ]; then
        echo " timeout"
    fi
    sleep 2
done

# Wait for Client Message Handler
echo -n "Client Handler..."
for i in {1..15}; do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo " ready"
        break
    fi
    if [ $i -eq 15 ]; then
        echo " timeout"
    fi
    sleep 2
done

# Wait for Frontend
echo -n "Frontend..."
for i in {1..15}; do
    if curl -sf http://localhost:3000/health > /dev/null 2>&1; then
        echo " ready"
        break
    fi
    if [ $i -eq 15 ]; then
        echo " timeout"
    fi
    sleep 2
done

# Optional: Import sample data (Fixed sensors)
EXCEL_FILE_FIXED="../backend/config/questdb/xlsxs/fixed_sensors_2026.xlsx"
if [ -f "$EXCEL_FILE_FIXED" ]; then
    echo ""
    echo -n "Importing fixed sensors data..."
    python3 ../backend/config/questdb/import_from_excel.py "$EXCEL_FILE_FIXED" 2>/dev/null && echo " done" || echo " skipped"
fi

# Optional: Import sample data (Mobile sensors)
# EXCEL_FILE_MOBILE="../backend/config/questdb//xlsxs/mobile_sensors_2026.xlsx"
# if [ -f "$EXCEL_FILE_MOBILE" ]; then
#     echo -n "Importing mobile sensors data..."
#     python3 ../backend/config/questdb/import_from_excel.py "$EXCEL_FILE_MOBILE" 2>/dev/null && echo " done" || echo " skipped"
# fi

echo ""
echo "Service Status:"
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || docker compose ps

echo ""
echo "Access Services:"
echo "  Frontend:           http://localhost:3000"
echo "  QuestDB Web:        http://localhost:9000"
echo "  Client Handler:     http://localhost:8000/docs"
echo "  Database Service:   http://localhost:8001/docs"
echo "  Data Provider:      http://localhost:8002/docs"
echo "  Ingest Service:     http://localhost:8003/docs"
echo "  Routing Service:    http://localhost:8080/docs"
echo "  Redis:              localhost:6379"
echo ""
echo "Useful Commands:"
echo "  View logs:      cd deploy && docker compose logs -f <service>"
echo "  Stop services:  ./scripts/local/stop.sh"
echo ""
