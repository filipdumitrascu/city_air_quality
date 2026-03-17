#!/bin/bash
# Integration Testing - CityAirQ End-to-End Flow

echo "CityAirQ Integration Testing"
echo ""

EXTERNAL_IP=$(kubectl get service client-message-handler -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)

if [ -z "$EXTERNAL_IP" ]; then
    echo "Error: LoadBalancer IP not found"
    exit 1
fi

BASE_URL="http://$EXTERNAL_IP:8000"
echo "Testing at: $BASE_URL"
echo ""

PASSED=0
FAILED=0

# TEST 1: Health Check
echo "Test 1: Health Check"
HEALTH=$(curl -s "$BASE_URL/health")
echo "Response: $HEALTH"
if echo "$HEALTH" | grep -q "healthy"; then
    echo "PASSED"; PASSED=$((PASSED+1))
else
    echo "FAILED"; FAILED=$((FAILED+1))
fi
echo ""

# TEST 2: Ingest Data (requires real OAuth token - expected to fail in CI)
echo "Test 2: Ingest Data"
TIMESTAMP_MS=$(($(date +%s) * 1000))
INGEST_PAYLOAD="{\"sensor_id\":\"IntTest_001\",\"sensor_type\":\"mobile\",\"timestamp\":$TIMESTAMP_MS,\"latitude\":44.4268,\"longitude\":26.1025,\"pm10\":45.3,\"pm2_5\":25.2}"
AUTH_TOKEN="${INGEST_AUTH_TOKEN:-}"

if [ -n "$AUTH_TOKEN" ]; then
    INGEST_RESPONSE=$(curl -s -X POST "$BASE_URL/ingest/" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $AUTH_TOKEN" \
      -d "$INGEST_PAYLOAD")
    echo "Response: $INGEST_RESPONSE"
    if echo "$INGEST_RESPONSE" | grep -qE "(success|published)"; then
        echo "PASSED"; PASSED=$((PASSED+1))
    else
        echo "FAILED"; FAILED=$((FAILED+1))
    fi
else
    echo "SKIPPED (no INGEST_AUTH_TOKEN set)"
fi
sleep 1
echo ""

# TEST 3: Query Data
echo "Test 3: Query Pollution Data"
QUERY_PAYLOAD='{"latitude":44.4350,"longitude":26.1015,"radius":5.0,"sensor_types":["fixed","mobile"],"layers":["pm10","pm2_5"]}'
QUERY_RESPONSE=$(curl -s -X POST "$BASE_URL/results/" -H "Content-Type: application/json" -d "$QUERY_PAYLOAD")
echo "Response: ${QUERY_RESPONSE:0:200}..."
if echo "$QUERY_RESPONSE" | grep -qE "(data|results|\[)"; then
    echo "PASSED"; PASSED=$((PASSED+1))
else
    echo "FAILED"; FAILED=$((FAILED+1))
fi
echo ""

# TEST 4: Route (Foot)
echo "Test 4: Route (Foot)"
ROUTE_FOOT='{"start":{"lat":44.4350,"lon":26.1015},"goal":{"lat":44.4360,"lon":26.1020},"alpha":0.5,"transport_mode":"foot","sensor_types":["fixed","mobile"]}'
ROUTE_FOOT_RESP=$(curl -s -X POST "$BASE_URL/route/" -H "Content-Type: application/json" -d "$ROUTE_FOOT")
echo "Response: ${ROUTE_FOOT_RESP:0:200}..."
if echo "$ROUTE_FOOT_RESP" | grep -qE "(coordinates|waypoints|route)"; then
    echo "PASSED"; PASSED=$((PASSED+1))
else
    echo "FAILED"; FAILED=$((FAILED+1))
fi
echo ""

# TEST 5: Route (Bicycle)
echo "Test 5: Route (Bicycle)"
ROUTE_BIKE='{"start":{"lat":44.4268,"lon":26.1025},"goal":{"lat":44.4350,"lon":26.1100},"alpha":1.0,"transport_mode":"bicycle"}'
ROUTE_BIKE_RESP=$(curl -s -X POST "$BASE_URL/route/" -H "Content-Type: application/json" -d "$ROUTE_BIKE")
echo "Response: ${ROUTE_BIKE_RESP:0:200}..."
if echo "$ROUTE_BIKE_RESP" | grep -qE "(coordinates|waypoints|route)"; then
    echo "PASSED"; PASSED=$((PASSED+1))
elif echo "$ROUTE_BIKE_RESP" | grep -qE "(not configured|API)"; then
    echo "SKIPPED (Google API not configured)"
else
    echo "FAILED"; FAILED=$((FAILED+1))
fi
echo ""

# TEST 6: Routing Service Health
echo "Test 6: Routing Service Health"
ROUTING_IP=$(kubectl get service routing-service -o jsonpath='{.spec.clusterIP}' 2>/dev/null)
if [ -n "$ROUTING_IP" ]; then
    kubectl port-forward svc/routing-service 8001:8000 &>/dev/null &
    PF_PID=$!
    sleep 2
    ROUTING_HEALTH=$(curl -s "http://localhost:8001/health" 2>/dev/null || echo "unreachable")
    kill $PF_PID 2>/dev/null || true
    echo "Response: $ROUTING_HEALTH"
    if echo "$ROUTING_HEALTH" | grep -q "healthy"; then
        echo "PASSED"; PASSED=$((PASSED+1))
    else
        echo "FAILED"; FAILED=$((FAILED+1))
    fi
else
    echo "SKIPPED (routing-service not found)"
fi
echo ""

# SUMMARY
echo "PASSED: $PASSED"
echo "FAILED: $FAILED"
if [ $FAILED -eq 0 ]; then
    echo "All tests PASSED!"
    exit 0
else
    echo "Some tests FAILED!"
    exit 1
fi
