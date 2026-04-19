#!/bin/bash
# Kubernetes Clean Script
# Removes deployments from cluster with option to preserve databases

set -e

# Move to this directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Deleting CityAirQ from Kubernetes..."
echo ""

# Ask about databases
DELETE_DBS="n"
read -p "Delete databases (QuestDB + Redis)? This will ERASE ALL DATA! [y/N]: " DELETE_DBS
DELETE_DBS="${DELETE_DBS:-n}"

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

# Conditionally delete databases
if [[ "$DELETE_DBS" =~ ^[Yy]$ ]]; then
    echo ""
    echo "Deleting databases (DATA WILL BE LOST)..."
    
    echo "  - QuestDB..."
    kubectl delete -f dbs/questdb-deployment.yaml --ignore-not-found=true
    
    echo "  - Redis..."
    kubectl delete -f dbs/redis-deployment.yaml --ignore-not-found=true
    
    echo ""
    echo "Deleting secrets..."
    kubectl delete secret credentials-secret --ignore-not-found=true --namespace=default
    
    echo ""
    echo "All services and databases deleted."
else
    echo ""
    echo "Microservices deleted. Databases preserved (QuestDB + Redis)."
fi

echo ""
echo "Remaining resources:"
kubectl get all --namespace=default
