#!/bin/bash

# Docker Logs Script
# Shows logs for all or specific service

SERVICE=$1

cd backend

if [ -z "$SERVICE" ]; then
    echo "Showing logs for all services..."
    docker-compose logs -f
else
    echo "Showing logs for $SERVICE..."
    docker-compose logs -f $SERVICE
fi
