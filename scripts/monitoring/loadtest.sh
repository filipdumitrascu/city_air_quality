#!/bin/bash
# run-loadtest.sh
# Run k6 load test against CityAirQ

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Get URLs from kubectl automatically
echo "Getting service IPs..."
CLIENT_IP=$(kubectl get svc client-message-handler -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
FRONTEND_IP=$(kubectl get svc frontend -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")

# Use detected IPs or fall back to arguments
if [ -n "$CLIENT_IP" ]; then
    BASE_URL="http://${CLIENT_IP}:8000"
else
    BASE_URL="${1:-http://localhost:8000}"
    echo "Warning: Could not detect client-message-handler IP"
fi

if [ -n "$FRONTEND_IP" ]; then
    FRONTEND_URL="http://${FRONTEND_IP}"
else
    FRONTEND_URL="${2:-http://localhost:80}"
    echo "Warning: Could not detect frontend IP"
fi

echo "CityAirQ Load Test"
echo ""
echo "Backend URL: $BASE_URL"
echo "Frontend URL: $FRONTEND_URL"
echo ""

# Check if k6 is installed
if ! command -v k6 &> /dev/null; then
    echo "k6 is not installed. Installing..."
    sudo snap install k6
fi

# Create output directory
OUTPUT_DIR="$SCRIPT_DIR/results"
mkdir -p "$OUTPUT_DIR"

# Generate timestamp for results
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RESULTS_FILE="$OUTPUT_DIR/loadtest_${TIMESTAMP}.json"

echo "Running load test..."
echo "Results will be saved to: $RESULTS_FILE"
echo ""

# Run the load test
k6 run \
    --env BASE_URL="$BASE_URL" \
    --env FRONTEND_URL="$FRONTEND_URL" \
    --out json="$RESULTS_FILE" \
    "$SCRIPT_DIR/../../monitoring/k6/loadtest.js"

echo ""
echo "Load test completed!"
echo "Results saved to: $RESULTS_FILE"
