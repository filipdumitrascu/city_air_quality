#!/bin/bash

# Build and Push Script
# Builds Docker images and pushes to Google Artifact Registry

set -e

# Move to this directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

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

cd ../../deploy

# Build and push (with filesystem access permissions)
echo "Building and pushing all images..."
export BUILDX_BAKE_ENTITLEMENTS_FS=0

docker buildx bake -f docker-compose.buildx.yaml \
    --push \
    --set '*.platform=linux/amd64'

echo "All images built and pushed successfully"
