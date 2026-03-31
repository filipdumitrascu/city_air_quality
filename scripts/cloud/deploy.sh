#!/bin/bash
# Kubernetes Deployment Script
# Deploys all services to GKE cluster

set -e

# Move to this directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Deploying CityAirQ to Kubernetes..."
echo ""

# Check if kubectl is configured
if ! kubectl cluster-info &> /dev/null; then
    echo "Error: kubectl not configured. Run setup.sh first"
    exit 1
fi

# Kill any existing port-forwards
echo "Cleaning up existing port-forwards..."
pkill -f "kubectl port-forward" 2>/dev/null || true
sleep 2

# Free up ports if still in use
for port in 8812 9000; do
    if lsof -i :$port > /dev/null 2>&1; then
        echo "Freeing port $port..."
        fuser -k $port/tcp 2>/dev/null || true
        sleep 1
    fi
done

cd ../../deploy

# Create secrets if not exists
echo "Creating secrets..."

# Google Cloud credentials
kubectl create secret generic credentials-secret \
    --from-file=credentials.json=credentials.json \
    --dry-run=client -o yaml | kubectl apply -f -

# Google Maps key
kubectl create secret generic google-maps-secret \
    --from-file=GOOGLE_MAPS_API_KEY=google-maps-key.txt \
    --dry-run=client -o yaml | kubectl apply -f -

# Ingest auth key (API for developers, no OAuth)
kubectl create secret generic ingest-secret \
    --from-file=INGEST_KEY=ingest-key.txt \
    --dry-run=client -o yaml | kubectl apply -f -

# Fixed sensors API from OpenAQ
kubectl create secret generic fixed-sensors-secret \
    --from-file=FIXED_SENSORS_KEY=fixed-sensors-key.txt \
    --dry-run=client -o yaml | kubectl apply -f -

# Database credentials
kubectl create secret generic database-credentials \
    --from-literal=DB_USER=admin \
    --from-literal=DB_PASSWORD=quest \
    --from-literal=DB_HOST=questdb-service \
    --from-literal=DB_PORT=8812 \
    --dry-run=client -o yaml | kubectl apply -f -

echo "Secrets created"
echo ""

# Deploy Redis first (no dependencies)
echo "Deploying Redis..."
kubectl apply -f dbs/redis-deployment.yaml
echo "Waiting for Redis to be ready..."
kubectl wait --for=condition=ready pod -l app=redis --timeout=120s --namespace=default
echo "Redis ready"
echo ""

# Deploy QuestDB (no dependencies)
echo "Deploying QuestDB..."
kubectl apply -f dbs/questdb-deployment.yaml
echo "Waiting for QuestDB to be ready..."
kubectl wait --for=condition=ready pod -l app=questdb --timeout=180s --namespace=default
echo "QuestDB ready"
echo ""

# Initialize QuestDB schema and import data
echo "Initializing QuestDB..."
sleep 20  # Extra wait for QuestDB to fully initialize

# Port-forward in background
kubectl port-forward svc/questdb-service 8812:8812 &
PF_PID=$!
sleep 5

# Create schema
echo -n "Creating schema..."
python3 << 'PYTHON_SCRIPT' 2>&1 | grep -v "^$"
import psycopg2
import sys

try:
    conn = psycopg2.connect('postgresql://admin:quest@localhost:8812/qdb')
    cur = conn.cursor()

    with open('../backend/config/questdb/schema.sql', 'r') as f:
        schema = f.read()
    cur.execute(schema)
    conn.commit()
    print(" done")
    
    cur.close()
    conn.close()
except Exception as e:
    print(f" error: {e}")
    sys.exit(1)
PYTHON_SCRIPT


# Kill port-forward
kill $PF_PID 2>/dev/null || true
echo "QuestDB initialized"
echo 

# Deploy Database Service (depends on QuestDB)
echo "Deploying Database Service..."
kubectl apply -f microservices/database_service-deployment.yaml
echo "Waiting for Database Service to be ready..."
kubectl wait --for=condition=ready pod -l app=database-service --timeout=120s --namespace=default
echo "Database Service ready"
echo ""

# Deploy Routing Service (depends on Redis + Database Service)
echo "Deploying Routing Service..."
kubectl apply -f microservices/routing-service-deployment.yaml
echo "Waiting for Routing Service to be ready..."
kubectl wait --for=condition=ready pod -l app=routing-service --timeout=120s --namespace=default
echo "Routing Service ready"
echo ""

# Deploy Ingest Service (depends on Database Service)
echo "Deploying Ingest Service..."
kubectl apply -f microservices/ingest_service-deployment.yaml
echo "Ingest Service deployed"
echo ""

# Deploy Data Provider Service (depends on Database Service)
echo "Deploying Data Provider Service..."
kubectl apply -f microservices/data_provider_service-deployment.yaml
echo "Data Provider Service deployed"
echo ""

# Deploy Client Message Handler (public endpoint)
echo "Deploying Client Message Handler..."
kubectl apply -f microservices/client_message_handler-deployment.yaml
echo "Waiting for Client Handler to be ready..."
kubectl wait --for=condition=ready pod -l app=client-message-handler --timeout=120s --namespace=default
echo "Client Message Handler ready"
echo ""

# Deploy Frontend
echo "Deploying Frontend..."
kubectl apply -f frontend/frontend-deployment.yaml
echo "Waiting for Frontend to be ready..."
kubectl wait --for=condition=ready pod -l app=frontend --timeout=120s --namespace=default
echo "Frontend ready"
echo ""

# Wait for all deployments
echo "Waiting for all deployments to be ready..."
kubectl wait --for=condition=available deployment --all --timeout=300s --namespace=default

echo ""
echo "Deployment complete!"
echo ""
echo "Cluster Status:"
kubectl get pods --namespace=default
echo ""
kubectl get services --namespace=default

echo ""
echo "External IP (LoadBalancer):"
kubectl get service client-message-handler --namespace=default -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
echo ""
echo ""
echo "CityAirQ is now running on Kubernetes!"
