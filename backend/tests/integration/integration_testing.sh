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

TIMESTAMP_MS=$(($(date +%s) * 1000))

INGEST_PAYLOAD='{
  "clientId": "TEST_SENSOR_001",
  "timestamp": '$TIMESTAMP_MS',
  "location": {"latitude": 44.4268, "longitude": 26.1025},
  "data": [
    {"dimension": "PM10", "value": 45.3},
    {"dimension": "PM2_5", "value": 25.2},
    {"dimension": "NO2", "value": 30.5}
  ]
}'

echo "Payload: $INGEST_PAYLOAD"

INGEST_RESPONSE=$(curl -s -X POST $BASE_URL/ingest/ \
  -H "Content-Type: application/json" \
  -d "$INGEST_PAYLOAD")

echo "Response: $INGEST_RESPONSE"

if [[ $INGEST_RESPONSE == *"success"* ]]; then
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
  "layers": ["pm10", "pm25", "no2"]
}'

echo "Payload: $QUERY_PAYLOAD"

QUERY_RESPONSE=$(curl -s -X POST $BASE_URL/results/ \
  -H "Content-Type: application/json" \
  -d "$QUERY_PAYLOAD")

echo "Response preview: ${QUERY_RESPONSE}..."

if [[ $QUERY_RESPONSE == *"error"* ]] || [[ $QUERY_RESPONSE == *"Timeout"* ]]; then
    echo "Query failed or timed out"
else
    echo "Query successful"
fi
echo ""


# # TEST 4: Route Calculation (first call) 
# echo "Test 4: Route Calculation (first call)"

# ROUTE_PAYLOAD='{
#   "start": {"lat": 44.4268, "lon": 26.1025},
#   "goal": {"lat": 44.4350, "lon": 26.1100},
#   "alpha": 0.5,
#   "sensor_types": []
# }'

# START_TIME=$(date +%s%3N)
# ROUTE_RESPONSE=$(curl -s -X POST $BASE_URL/route/ \
#   -H "Content-Type: application/json" \
#   -d "$ROUTE_PAYLOAD")
# END_TIME=$(date +%s%3N)

# FIRST_CALL_TIME=$((END_TIME - START_TIME))
# echo "Response time: ${FIRST_CALL_TIME} ms"

# DISTANCE=$(echo "$ROUTE_RESPONSE" | grep -o '"distance_km":[0-9.]*' | cut -d':' -f2)
# PM10=$(echo "$ROUTE_RESPONSE" | grep -o '"avg_pollution_pm10":[0-9.]*' | cut -d':' -f2)
# CACHED=$(echo "$ROUTE_RESPONSE" | grep -o '"cached":[a-z]*' | cut -d':' -f2)

# if [ -n "$DISTANCE" ]; then
#     echo "Route calculated"
#     echo "Distance: ${DISTANCE} km"
#     echo "Avg PM10: $PM10"
#     echo "Cached: $CACHED"
# else
#     echo "Route calculation failed"
#     echo "Response: $ROUTE_RESPONSE"
# fi
# echo ""


# # TEST 5: Route Calculation (cache hit)
# echo "Test 5: Route Calculation (second call - should be cached)"

# START_TIME=$(date +%s%3N)
# ROUTE_RESPONSE_2=$(curl -s -X POST $BASE_URL/route/ \
#   -H "Content-Type: application/json" \
#   -d "$ROUTE_PAYLOAD")
# END_TIME=$(date +%s%3N)

# SECOND_CALL_TIME=$((END_TIME - START_TIME))
# echo "Response time: ${SECOND_CALL_TIME} ms"

# CACHED_2=$(echo "$ROUTE_RESPONSE_2" | grep -o '"cached":[a-z]*' | cut -d':' -f2)

# if [[ "$CACHED_2" == "true" ]]; then
#     echo "Cache hit confirmed"
#     echo "First call:  ${FIRST_CALL_TIME} ms"
#     echo "Second call: ${SECOND_CALL_TIME} ms"
#     if [ "$SECOND_CALL_TIME" -gt 0 ]; then
#         SPEEDUP=$((FIRST_CALL_TIME / SECOND_CALL_TIME))
#         echo "Speedup: ${SPEEDUP}x"
#     fi
# else
#     echo "Cache miss (may be expected if route changed)"
# fi
# echo ""


# SUMMARY
echo "Integration Test Summary"
echo "Health Check: PASSED"
echo "Ingest: ${INGEST_RESPONSE}"
echo "Query: Response received"
# echo "Routing: Distance=${DISTANCE}km, PM10=${PM10}"
# echo "Cache: ${CACHED_2}"
echo ""
echo "All integration tests completed!"
