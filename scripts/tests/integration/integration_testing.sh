#!/bin/bash
# Integration Testing - CityAirQ End-to-End Flow
# Tests: Health, Ingest (PubSub), Query (QuestDB), Routing

set -e

echo "CityAirQ Integration Testing"
echo ""

# Get external IP
EXTERNAL_IP=$(kubectl get service client-message-handler -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

if [ -z "$EXTERNAL_IP" ]; then
    echo "Error: LoadBalancer IP not found"
    echo "Run: kubectl get service client-message-handler"
    exit 1
fi

BASE_URL="http://$EXTERNAL_IP:8000"
echo "Testing CityAirQ at: $BASE_URL"
echo ""


# TEST 1: Health Check
echo "Test 1: Health Check"
HEALTH=$(curl -s $BASE_URL/health)
echo "Response: $HEALTH"

if [[ $HEALTH == *"healthy"* ]]; then
    echo "PASSED"
else
    echo "FAILED"
    exit 1
fi
echo ""


# TEST 2: Ingest Data (PubSub Flow)
echo "Test 2: Ingest Data via PubSub"

TIMESTAMP_MS=$(($(date +%s) * 1000))

INGEST_PAYLOAD='{
  "clientId": "F000_IntTesting",
  "timestamp": '$TIMESTAMP_MS',
  "location": {"latitude": 44.4268, "longitude": 26.1025},
  "data": [
    {"dimension": "PM10", "value": 45.3},
    {"dimension": "PM2_5", "value": 25.2},
    {"dimension": "NO2", "value": 30.5}
  ]
}'

INGEST_RESPONSE=$(curl -s -X POST $BASE_URL/ingest/ \
  -H "Content-Type: application/json" \
  -d "$INGEST_PAYLOAD")

echo "Response: $INGEST_RESPONSE"

if [[ $INGEST_RESPONSE == *"success"* ]]; then
    echo "PASSED"
else
    echo "FAILED"
    exit 1
fi

echo "Waiting for PubSub processing..."
sleep 5
echo ""


# TEST 3: Query Data (QuestDB)
echo "Test 3: Query Data from QuestDB"

QUERY_PAYLOAD='{
  "latitude": 44.4268,
  "longitude": 26.1025,
  "radius": 5.0,
  "layers": ["pm10", "pm25", "no2"]
}'

QUERY_RESPONSE=$(curl -s -X POST $BASE_URL/results/ \
  -H "Content-Type: application/json" \
  -d "$QUERY_PAYLOAD")

echo "Response: $QUERY_RESPONSE"

if [[ $QUERY_RESPONSE == *"data"* ]]; then
    echo "PASSED"
else
    echo "FAILED"
    exit 1
fi
echo ""


# TEST 4: Route Calculation
echo "Test 4: Route Calculation"

ROUTE_PAYLOAD='{
  "start": {"lat": 44.4268, "lon": 26.1025},
  "goal": {"lat": 44.4350, "lon": 26.1100},
  "alpha": 0.5,
  "sensor_types": []
}'

ROUTE_RESPONSE=$(curl -s -X POST $BASE_URL/route/ \
  -H "Content-Type: application/json" \
  -d "$ROUTE_PAYLOAD")

echo "Response: $ROUTE_RESPONSE"

if [[ $ROUTE_RESPONSE == *"route"* ]] && [[ $ROUTE_RESPONSE == *"waypoints"* ]]; then
    echo "PASSED"
else
    echo "FAILED"
    exit 1
fi
echo ""

# SUMMARY
echo ""
echo "All integration tests completed!"
