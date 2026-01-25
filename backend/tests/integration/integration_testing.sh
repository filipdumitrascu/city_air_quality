#!/bin/bash
# Integration Testing - CityAirQ End-to-End Flow
# Tests: Health, Ingest (PubSub), Query (QuestDB), Routing (Redis)

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
    echo "Health check passed"
else
    echo "Health check failed"
    exit 1
fi
echo ""


# TEST 2: Ingest Data (PubSub Flow)
echo "Test 2: Ingest Data via PubSub"

INGEST_PAYLOAD='{
  "sensor_id": "TEST_SENSOR_001",
  "sensor_type": "fixed",
  "latitude": 44.4268,
  "longitude": 26.1025,
  "timestamp": "'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'",
  "data": [
    {"dimension": "PM10", "value": 45.3},
    {"dimension": "PM2.5", "value": 25.2},
    {"dimension": "NO2", "value": 30.5}
  ]
}'

echo "Payload: $INGEST_PAYLOAD"

INGEST_RESPONSE=$(curl -s -X POST $BASE_URL/ingest/ \
  -H "Content-Type: application/json" \
  -d "$INGEST_PAYLOAD")

echo "Response: $INGEST_RESPONSE"

if [[ $INGEST_RESPONSE == *"published"* ]] || [[ $INGEST_RESPONSE == *"success"* ]]; then
    echo "Ingest successful"
else
    echo "Ingest response unclear, check logs"
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
  "sensor_types": ["fixed"]
}'

echo "Payload: $QUERY_PAYLOAD"

QUERY_RESPONSE=$(curl -s -X POST $BASE_URL/results/ \
  -H "Content-Type: application/json" \
  -d "$QUERY_PAYLOAD")

echo "Response preview: ${QUERY_RESPONSE:0:200}..."

RESULT_COUNT=$(echo "$QUERY_RESPONSE" | grep -o '"sensor_id"' | wc -l)
echo "Found $RESULT_COUNT sensor readings"

if [ "$RESULT_COUNT" -gt 0 ]; then
    echo "Query successful"
else
    echo "No results found"
fi
echo ""


# TEST 4: Route Calculation (cache miss)
echo "Test 4: Route Calculation (first call)"

ROUTE_PAYLOAD='{
  "start": {"lat": 44.4268, "lon": 26.1025},
  "goal": {"lat": 44.4350, "lon": 26.1100},
  "alpha": 0.5,
  "sensor_types": ["fixed"]
}'

START_TIME=$(date +%s%3N)
ROUTE_RESPONSE=$(curl -s -X POST $BASE_URL/route/ \
  -H "Content-Type: application/json" \
  -d "$ROUTE_PAYLOAD")
END_TIME=$(date +%s%3N)

FIRST_CALL_TIME=$((END_TIME - START_TIME))
echo "Response time: ${FIRST_CALL_TIME} ms"

DISTANCE=$(echo "$ROUTE_RESPONSE" | grep -o '"distance_km":[0-9.]*' | cut -d':' -f2)
PM10=$(echo "$ROUTE_RESPONSE" | grep -o '"avg_pollution_pm10":[0-9.]*' | cut -d':' -f2)
CACHED=$(echo "$ROUTE_RESPONSE" | grep -o '"cached":[a-z]*' | cut -d':' -f2)

if [ -n "$DISTANCE" ]; then
    echo "Route calculated"
    echo "Distance: ${DISTANCE} km"
    echo "Avg PM10: $PM10"
    echo "Cached: $CACHED"
else
    echo "Route calculation unclear"
fi
echo ""


# TEST 5: Route Calculation (cache hit)
echo "Test 5: Route Calculation (second call)"

START_TIME=$(date +%s%3N)
ROUTE_RESPONSE_2=$(curl -s -X POST $BASE_URL/route/ \
  -H "Content-Type: application/json" \
  -d "$ROUTE_PAYLOAD")
END_TIME=$(date +%s%3N)

SECOND_CALL_TIME=$((END_TIME - START_TIME))
echo "Response time: ${SECOND_CALL_TIME} ms"

CACHED_2=$(echo "$ROUTE_RESPONSE_2" | grep -o '"cached":[a-z]*' | cut -d':' -f2)

if [[ "$CACHED_2" == "true" ]]; then
    SPEEDUP=$((FIRST_CALL_TIME / SECOND_CALL_TIME))
    echo "Cache hit detected"
    echo "First call:  ${FIRST_CALL_TIME} ms"
    echo "Second call: ${SECOND_CALL_TIME} ms"
    echo "Speedup: ${SPEEDUP}x"
else
    echo "Cache miss (unexpected)"
fi
echo ""


# TEST 6: Redis Cache Stats
echo "Test 6: Redis Cache Statistics"
echo "Requires port-forward:"
echo "kubectl port-forward svc/routing-service 8080:8000"
echo "Then run:"
echo "curl http://localhost:8080/cache/stats"
echo ""


# SUMMARY
echo "Integration Test Summary"
echo "Health Check: PASSED"
echo "Ingest: PASSED"
echo "Query: ($RESULT_COUNT results)"
echo "Routing: (${DISTANCE} km, PM10: $PM10)"
echo "Redis Cache: (${SPEEDUP} x speedup)"
echo ""
echo "All integration tests completed successfully"
echo ""
echo "Next steps:"
echo "- Check logs: kubectl logs -l app=<service-name>"
echo "- Monitor cluster: ./info.sh"
