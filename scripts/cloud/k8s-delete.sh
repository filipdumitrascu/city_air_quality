#!/bin/bash

# Kubernetes Delete Script
# Removes all deployments from cluster

set -e

echo "Deleting CityAirQ from Kubernetes..."

cd deploy

# Delete in reverse order
echo "Deleting services..."
kubectl delete -f client_message_handler-deployment.yaml --ignore-not-found=true
kubectl delete -f routing-service-deployment.yaml --ignore-not-found=true
kubectl delete -f data_provider_service-deployment.yaml --ignore-not-found=true
kubectl delete -f ingest_service-deployment.yaml --ignore-not-found=true
kubectl delete -f database_service-deployment.yaml --ignore-not-found=true
kubectl delete -f questdb-service.yaml --ignore-not-found=true
kubectl delete -f redis-deployment.yaml --ignore-not-found=true

# Delete monitoring
kubectl delete -f prometheus/prometheus-ServiceMonitor.yaml --ignore-not-found=true
kubectl delete -f loki/loki-custom-values.yaml --ignore-not-found=true

echo "All services deleted"
