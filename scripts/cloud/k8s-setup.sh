#!/bin/bash

# Kubernetes Setup Script
# Authenticates and configures kubectl for GKE

set -e

# Configuration
PROJECT_ID="cityairq-pollution-project"
CLUSTER_NAME="cityairq-standard"
ZONE="europe-west1-b"
SERVICE_ACCOUNT_KEY="../deploy/cityairq-pollution-project-522aec65f650.json"

echo "Setting up Kubernetes access..."

# Authenticate with service account
echo "Authenticating with Google Cloud..."
gcloud auth activate-service-account \
    --key-file=$SERVICE_ACCOUNT_KEY

# Set project
echo "Setting project to $PROJECT_ID..."
gcloud config set project $PROJECT_ID

# Get cluster credentials
echo "Getting cluster credentials..."
gcloud container clusters get-credentials $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID

# Verify connection
echo "Verifying cluster connection..."
kubectl cluster-info

echo "Kubernetes setup complete"
