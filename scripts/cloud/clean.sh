#!/bin/bash
# Kubernetes Clean Script

set -e

# Move to this directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Deleting CityAirQ from Kubernetes..."
echo ""

cd ../../deploy

# Delete in reverse order (opposite of deploy)
echo "Deleting Frontend..."
kubectl delete -f frontend/frontend-deployment.yaml --ignore-not-found=true

echo "Deleting Client Message Handler..."
kubectl delete -f microservices/client_message_handler-deployment.yaml --ignore-not-found=true

echo "Deleting Data Provider Service..."
kubectl delete -f microservices/data_provider_service-deployment.yaml --ignore-not-found=true

echo "Deleting Ingest Service..."
kubectl delete -f microservices/ingest_service-deployment.yaml --ignore-not-found=true

echo "Deleting Routing Service..."
kubectl delete -f microservices/routing-service-deployment.yaml --ignore-not-found=true

echo "Deleting Forecast Service..."
kubectl delete -f microservices/forecast-service-deployment.yaml --ignore-not-found=true

echo "Deleting Database Service..."
kubectl delete -f microservices/database_service-deployment.yaml --ignore-not-found=true

echo "Deleting QuestDB..."
kubectl delete -f dbs/questdb-deployment.yaml --ignore-not-found=true

echo "Deleting Redis..."
kubectl delete -f dbs/redis-deployment.yaml --ignore-not-found=true

echo "Deleting secrets..."
kubectl delete secret credentials-secret --ignore-not-found=true
kubectl delete secret google-maps-secret --ignore-not-found=true

echo ""
echo "All services deleted."
echo ""
echo "Remaining resources:"
kubectl get all
