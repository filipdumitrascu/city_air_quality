#!/bin/bash

# Kubernetes Status Script
# Shows status of all resources

set -e

echo "CityAirQ Kubernetes Status"
echo "=========================="

echo ""
echo "Pods:"
kubectl get pods

echo ""
echo "Services:"
kubectl get services

echo ""
echo "Deployments:"
kubectl get deployments

echo ""
echo "PersistentVolumeClaims:"
kubectl get pvc

echo ""
echo "ConfigMaps:"
kubectl get configmaps
