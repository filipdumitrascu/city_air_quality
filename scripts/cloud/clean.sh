#!/bin/bash
# Kubernetes Delete Script
# Removes all deployments from cluster

set -e

echo "Deleting CityAirQ from Kubernetes..."
echo ""

cd ../../deploy

# Delete in reverse order (opposite of deploy)
echo "Deleting Client Message Handler..."
kubectl delete -f client_message_handler-deployment.yaml --ignore-not-found=true

echo "Deleting Data Provider Service..."
kubectl delete -f data_provider_service-deployment.yaml --ignore-not-found=true

echo "Deleting Ingest Service..."
kubectl delete -f ingest_service-deployment.yaml --ignore-not-found=true

echo "Deleting Routing Service..."
kubectl delete -f routing-service-deployment.yaml --ignore-not-found=true

echo "Deleting Database Service..."
kubectl delete -f database_service-deployment.yaml --ignore-not-found=true

echo "Deleting QuestDB..."
kubectl delete -f questdb-deployment.yaml --ignore-not-found=true

echo "Deleting Redis..."
kubectl delete -f redis-deployment.yaml --ignore-not-found=true

echo "Deleting secrets..."
kubectl delete secret credentials-secret --ignore-not-found=true --namespace=default

echo ""
echo "All services deleted"
echo ""
echo "Remaining resources:"
kubectl get all --namespace=default
