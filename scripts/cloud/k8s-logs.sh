#!/bin/bash

# Kubernetes Logs Script
# Shows logs for a specific pod

POD_NAME=$1

if [ -z "$POD_NAME" ]; then
    echo "Usage: ./k8s-logs.sh <pod-name>"
    echo ""
    echo "Available pods:"
    kubectl get pods
    exit 1
fi

echo "Showing logs for $POD_NAME..."
kubectl logs -f $POD_NAME
