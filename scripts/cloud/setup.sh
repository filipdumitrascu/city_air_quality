#!/bin/bash

# Kubernetes Setup Script
# Authenticates and configures kubectl for GKE

set -e

# Configuration
PROJECT_ID="cityairq"
CLUSTER_NAME="cityairq-standard"
REGION="us-central1-a"
SERVICE_ACCOUNT_KEY="../../deploy/credentials.json"

echo "Setting up Kubernetes access..."

# Authenticate with service account
echo "Authenticating with Google Cloud..."
gcloud auth activate-service-account \
    --key-file=$SERVICE_ACCOUNT_KEY

echo ""

# Set project
echo "Setting project to $PROJECT_ID..."
gcloud config set project $PROJECT_ID

echo ""

# Get cluster credentials
echo "Getting cluster credentials..."
gcloud container clusters get-credentials $CLUSTER_NAME \
    --region=$REGION \
    --project=$PROJECT_ID

echo ""

# Verify connection
echo "Verifying cluster connection..."
kubectl cluster-info

echo ""
echo "Kubernetes setup complete"
