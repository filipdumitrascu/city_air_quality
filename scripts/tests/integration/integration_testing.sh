#!/bin/bash
# Integration Testing - CityAirQ End-to-End Flow
# Tests: Health, Ingest, Query, Routing (Foot & Bicycle)

set -e

echo "CityAirQ Integration Testing"
echo ""

# Get external IP
EXTERNAL_IP=$(kubectl get service client-message-handler -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)

if [ -z "$EXTERNAL_IP" ]; then
    echo "Error: LoadBalancer IP not found"
    echo "Run: kubectl get service client-message-handler"
    exit 1
fi

BASE_URL="http://$EXTERNAL_IP:8000"
echo "Testing CityAirQ at: $BASE_URL"
echo ""

PASSED=0
FAILED=0


# TEST 1: Health Check
echo "Test 1: Health Check"

HEALTH=$(curl -s "$BASE_URL/health")
echo "Response: $HEALTH"

if echo "$HEALTH" | grep -q "healthy"; then
    echo "Result: PASSED"
    ((PASSED++))
else
    echo "Result: FAILED"
    ((FAILED++))
fi
echo ""


# TEST 2: Ingest Data (New Schema)
echo "Test 2: Ingest Data (New Schema)"

TIMESTAMP_MS=$(($(date +%s) * 1000))

# New flat schema - no nested location/data
INGEST_PAYLOAD=$(cat <<EOF
{
  "sensor_id": "IntTest_001",
  "sensor_type": "mobile",
  "timestamp": $TIMESTAMP_MS,
  "latitude": 44.4268,
  "longitude": 26.1025,
  "altitude": 80.0,
  "humidity": 65.0,
  "pressure": 1013.0,
  "temperature": 22.0,
  "pm10": 45.3,
  "pm2_5": 25.2,
  "pm1_0": 12.0,
  "no2": -1,
  "co": -1,
  "co2": 420.0,
  "nh3": -1,
  "vocs": -1
}
EOF
)

# Auth token required for ingest
AUTH_TOKEN="${INGEST_AUTH_TOKEN:-test-token-123}"

INGEST_RESPONSE=$(curl -s -X POST "$BASE_URL/ingest/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -d "$INGEST_PAYLOAD")

echo "Response: $INGEST_RESPONSE"

if echo "$INGEST_RESPONSE" | grep -qE "(success|published|queued)"; then
    echo "Result: PASSED"
    ((PASSED++))
else
    echo "Result: FAILED (may need valid AUTH token)"
    ((FAILED++))
fi

echo "Waiting for PubSub processing..."
sleep 5
echo ""


# TEST 3: Query Data (QuestDB)
echo "Test 3: Query Pollution Data"

QUERY_PAYLOAD=$(cat <<EOF
{
  "latitude": 44.4268,
  "longitude": 26.1025,
  "radius": 10.0,
  "sensor_types": ["fixed", "mobile"],
  "layers": ["pm10", "pm2_5"]
}
EOF
)

QUERY_RESPONSE=$(curl -s -X POST "$BASE_URL/results/" \
  -H "Content-Type: application/json" \
  -d "$QUERY_PAYLOAD")

echo "Response: ${QUERY_RESPONSE:0:300}..."

if echo "$QUERY_RESPONSE" | grep -qE "(data|results|\[)"; then
    echo "Result: PASSED"
    ((PASSED++))
else
    echo "Result: FAILED"
    ((FAILED++))
fi
echo ""


# TEST 4: Route Calculation (Foot Mode - A* on pollution grid)
echo "Test 4: Route Calculation (By Foot)"

ROUTE_FOOT_PAYLOAD=$(cat <<EOF
{
  "start": {"lat": 44.4268, "lon": 26.1025},
  "goal": {"lat": 44.4350, "lon": 26.1100},
  "alpha": 0.5,
  "transport_mode": "foot",
  "sensor_types": ["fixed", "mobile"],
  "heuristic": "haversine"
}
EOF
)

ROUTE_FOOT_RESPONSE=$(curl -s -X POST "$BASE_URL/route/" \
  -H "Content-Type: application/json" \
  -d "$ROUTE_FOOT_PAYLOAD")

echo "Response: ${ROUTE_FOOT_RESPONSE:0:300}..."

if echo "$ROUTE_FOOT_RESPONSE" | grep -qE "(coordinates|waypoints|route)"; then
    echo "Result: PASSED"
    ((PASSED++))
else
    echo "Result: FAILED"
    ((FAILED++))
fi
echo ""

# TEST 5: Route Calculation (Bicycle Mode - Google Routes API)
echo "Test 5: Route Calculation (By Bicycle)"

ROUTE_BIKE_PAYLOAD=$(cat <<EOF
{
  "start": {"lat": 44.4268, "lon": 26.1025},
  "goal": {"lat": 44.4350, "lon": 26.1100},
  "alpha": 1.0,
  "transport_mode": "bicycle",
  "sensor_types": ["fixed", "mobile"]
}
EOF
)

ROUTE_BIKE_RESPONSE=$(curl -s -X POST "$BASE_URL/route/" \
  -H "Content-Type: application/json" \
  -d "$ROUTE_BIKE_PAYLOAD")

echo "Response: ${ROUTE_BIKE_RESPONSE:0:300}..."

if echo "$ROUTE_BIKE_RESPONSE" | grep -qE "(coordinates|waypoints|route)"; then
    echo "Result: PASSED"
    ((PASSED++))
elif echo "$ROUTE_BIKE_RESPONSE" | grep -qE "(not configured|API key)"; then
    echo "Result: SKIPPED (Google Routes API not configured)"
else
    echo "Result: FAILED"
    ((FAILED++))
fi
echo ""

# TEST 6: Routing Service Health (Direct)}
echo "Test 6: Routing Service Health"]

# Get routing service IP (internal or external)
ROUTING_IP=$(kubectl get service routing-service -o jsonpath='{.spec.clusterIP}' 2>/dev/null)

if [ -n "$ROUTING_IP" ]; then
    # Port-forward temporarily
    kubectl port-forward svc/routing-service 8001:8000 &>/dev/null &
    PF_PID=$!
    sleep 2
    
    ROUTING_HEALTH=$(curl -s "http://localhost:8001/health" 2>/dev/null || echo "unreachable")
    
    kill $PF_PID 2>/dev/null || true
    
    echo "Response: $ROUTING_HEALTH"
    
    if echo "$ROUTING_HEALTH" | grep -q "healthy"; then
        echo "Result: PASSED"
        ((PASSED++))
    else
        echo "Result: FAILED"
        ((FAILED++))
    fi
else
    echo "Result: SKIPPED (routing-service not found)"
fi
echo ""

echo "SUMMARY"
echo "Passed: $PASSED"
echo "Failed: $FAILED"
echo ""

if [ $FAILED -eq 0 ]; then
    echo "All integration tests PASSED!"
    exit 0
else
    echo "Some tests FAILED!"
    exit 1
fi
