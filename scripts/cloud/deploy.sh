#!/bin/bash
# Kubernetes Deployment Script
# Deploys all services to GKE cluster

set -e

echo "Deploying CityAirQ to Kubernetes..."
echo ""

# Check if kubectl is configured
if ! kubectl cluster-info &> /dev/null; then
    echo "Error: kubectl not configured. Run setup.sh first"
    exit 1
fi

cd ../../deploy

# Create secrets if not exists
echo "Creating secrets..."

# Google Cloud credentials
kubectl create secret generic credentials-secret \
    --from-file=credentials.json=credentials.json \
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
kubectl apply -f redis-deployment.yaml
echo "Waiting for Redis to be ready..."
kubectl wait --for=condition=ready pod -l app=redis --timeout=120s --namespace=default
echo "Redis ready"
echo ""

# Deploy QuestDB (no dependencies)
echo "Deploying QuestDB..."
kubectl apply -f questdb-deployment.yaml
echo "Waiting for QuestDB to be ready..."
kubectl wait --for=condition=ready pod -l app=questdb --timeout=180s --namespace=default
echo "QuestDB ready"
echo ""

# Deploy Database Service (depends on QuestDB)
echo "Deploying Database Service..."
kubectl apply -f database_service-deployment.yaml
echo "Waiting for Database Service to be ready..."
kubectl wait --for=condition=ready pod -l app=database-service --timeout=120s --namespace=default
echo "Database Service ready"
echo ""

# Deploy Routing Service (depends on Redis + Database Service)
echo "Deploying Routing Service..."
kubectl apply -f routing-service-deployment.yaml
echo "Waiting for Routing Service to be ready..."
kubectl wait --for=condition=ready pod -l app=routing-service --timeout=120s --namespace=default
echo "Routing Service ready"
echo ""

# Deploy Ingest Service (depends on Database Service)
echo "Deploying Ingest Service..."
kubectl apply -f ingest_service-deployment.yaml
echo "Ingest Service deployed"
echo ""

# Deploy Data Provider Service (depends on Database Service)
echo "Deploying Data Provider Service..."
kubectl apply -f data_provider_service-deployment.yaml
echo "Data Provider Service deployed"
echo ""

# Deploy Client Message Handler (public endpoint)
echo "Deploying Client Message Handler..."
kubectl apply -f client_message_handler-deployment.yaml
echo "Waiting for Client Handler to be ready..."
kubectl wait --for=condition=ready pod -l app=client-message-handler --timeout=120s --namespace=default
echo "Client Message Handler ready"
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
