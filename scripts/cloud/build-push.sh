#!/bin/bash

# Build and Push Script
# Builds Docker images and pushes to Google Artifact Registry

set -e

echo "Building and pushing Docker images..."

# Authenticate with GCR
echo "Authenticating with Docker..."
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

# Create buildx instance if not exists
if ! docker buildx inspect multiarch-builder &> /dev/null; then
    echo "Creating buildx builder..."
    docker buildx create --name multiarch-builder --use
else
    echo "Using existing buildx builder..."
    docker buildx use multiarch-builder
fi

cd ../../backend

# Build and push
echo "Building and pushing all images..."
docker buildx bake -f docker-compose.buildx.yaml \
    --push \
    --set '*.platform=linux/amd64'

echo "All images built and pushed successfully"
