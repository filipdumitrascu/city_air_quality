#!/bin/bash

# Kubernetes Deployment Script
# Deploys all services to GKE cluster

set -e

echo "Deploying CityAirQ to Kubernetes..."

# Check if kubectl is configured
if ! kubectl cluster-info &> /dev/null; then
    echo "Error: kubectl not configured. Run k8s-setup.sh first"
    exit 1
fi

cd deploy

# Create secrets if not exists
echo "Creating secrets..."
kubectl create secret generic credentials-secret \
    --from-file=credentials.json=../backend/credentials.json \
    --dry-run=client -o yaml | kubectl apply -f -

# Deploy Redis first
echo "Deploying Redis..."
kubectl apply -f redis-deployment.yaml

# Wait for Redis
echo "Waiting for Redis to be ready..."
kubectl wait --for=condition=ready pod -l app=redis --timeout=60s

# Deploy QuestDB
echo "Deploying QuestDB..."
kubectl apply -f questdb-service.yaml

# Deploy Database Service
echo "Deploying Database Service..."
kubectl apply -f database_service-deployment.yaml

# Wait for Database Service
kubectl wait --for=condition=ready pod -l app=database-service --timeout=60s

# Deploy other services
echo "Deploying Ingest Service..."
kubectl apply -f ingest_service-deployment.yaml

echo "Deploying Data Provider Service..."
kubectl apply -f data_provider_service-deployment.yaml

echo "Deploying Routing Service..."
kubectl apply -f routing-service-deployment.yaml

echo "Deploying Client Message Handler..."
kubectl apply -f client_message_handler-deployment.yaml

# Deploy monitoring
echo "Deploying monitoring stack..."
kubectl apply -f prometheus/prometheus-ServiceMonitor.yaml
kubectl apply -f loki/loki-custom-values.yaml

echo "Waiting for all deployments to be ready..."
kubectl wait --for=condition=available deployment --all --timeout=300s

echo "Deployment complete"
echo "Checking pod status..."
kubectl get pods
