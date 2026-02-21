import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

// Custom metrics
const routeRequests = new Counter('route_requests');
const queryRequests = new Counter('query_requests');
const routeErrors = new Rate('route_errors');
const queryErrors = new Rate('query_errors');
const routeDuration = new Trend('route_duration');
const queryDuration = new Trend('query_duration');

// Load test configuration
export let options = {
    stages: [
        { duration: '30s', target: 50 },   // Ramp-up to 50 users
        { duration: '2m', target: 50 },    // Maintain 50 users for 2 minutes
        { duration: '30s', target: 100 },  // Ramp-up to 100 users
        { duration: '2m', target: 100 },   // Maintain 100 users for 2 minutes
        { duration: '30s', target: 0 },    // Ramp-down to 0 users
    ],
    thresholds: {
        http_req_duration: ['p(95)<2000'],  // 95% of requests should respond under 2s
        http_req_failed: ['rate<0.05'],      // <5% error rate acceptable
        route_errors: ['rate<0.1'],          // <10% route errors
        query_errors: ['rate<0.1'],          // <10% query errors
    },
};

// CityAirQ API endpoints - UPDATE THESE WITH YOUR ACTUAL IPs
const BASE_URL = __ENV.BASE_URL || 'http://34.31.126.80:8000';
const FRONTEND_URL = __ENV.FRONTEND_URL || 'http://136.114.174.111';

// Bucharest coordinates for testing
const testLocations = [
    { name: 'Piata Unirii', lat: 44.4268, lon: 26.1025 },
    { name: 'Piata Victoriei', lat: 44.4530, lon: 26.0855 },
    { name: 'Herastrau', lat: 44.4712, lon: 26.0812 },
    { name: 'Titan', lat: 44.4134, lon: 26.1456 },
    { name: 'Drumul Taberei', lat: 44.4297, lon: 26.0298 },
    { name: 'Pipera', lat: 44.4789, lon: 26.1156 },
    { name: 'Berceni', lat: 44.3856, lon: 26.1234 },
    { name: 'Militari', lat: 44.4298, lon: 25.9987 },
    { name: 'Colentina', lat: 44.4567, lon: 26.1345 },
    { name: 'Rahova', lat: 44.4023, lon: 26.0678 },
];

// Get random location
function getRandomLocation() {
    return testLocations[Math.floor(Math.random() * testLocations.length)];
}

// Get two different random locations for routing
function getTwoLocations() {
    const start = getRandomLocation();
    let end = getRandomLocation();
    while (end.name === start.name) {
        end = getRandomLocation();
    }
    return { start, end };
}

export default function () {
    const headers = { 'Content-Type': 'application/json' };

    group('Route Calculation', function () {
        const { start, end } = getTwoLocations();
        
        // Randomly choose sensor types
        const sensorTypes = Math.random() > 0.3 
            ? ['fixed', 'mobile'] 
            : (Math.random() > 0.5 ? ['fixed'] : ['mobile']);
        
        // Random alpha value
        const alpha = Math.random().toFixed(2);

        const routePayload = JSON.stringify({
            start: { lat: start.lat, lon: start.lon },
            goal: { lat: end.lat, lon: end.lon },
            alpha: parseFloat(alpha),
            sensor_types: sensorTypes
        });

        const routeRes = http.post(`${BASE_URL}/route/`, routePayload, { headers });
        
        routeRequests.add(1);
        routeDuration.add(routeRes.timings.duration);

        const routeSuccess = check(routeRes, {
            'Route status is 200': (r) => r.status === 200,
            'Route has waypoints': (r) => {
                try {
                    const data = JSON.parse(r.body);
                    return data.waypoints && Array.isArray(data.waypoints) && data.waypoints.length > 0;
                } catch (e) {
                    return false;
                }
            },
            'Route has geometry': (r) => {
                try {
                    const data = JSON.parse(r.body);
                    return data.route && data.route.geometry && data.route.geometry.coordinates;
                } catch (e) {
                    return false;
                }
            }
        });

        routeErrors.add(!routeSuccess);
    });

    sleep(0.5);

    group('Pollution Query', function () {
        const location = getRandomLocation();
        const radius = (Math.random() * 4 + 1).toFixed(1); // 1-5 km radius

        const queryPayload = JSON.stringify({
            latitude: location.lat,
            longitude: location.lon,
            radius: parseFloat(radius),
            layers: ['pm10', 'pm25', 'no2'],
            sensor_types: ['fixed', 'mobile']
        });

        const queryRes = http.post(`${BASE_URL}/results/`, queryPayload, { headers });
        
        queryRequests.add(1);
        queryDuration.add(queryRes.timings.duration);

        const querySuccess = check(queryRes, {
            'Query status is 200': (r) => r.status === 200,
            'Query returns data': (r) => {
                try {
                    const data = JSON.parse(r.body);
                    return data.data && Array.isArray(data.data);
                } catch (e) {
                    return false;
                }
            }
        });

        queryErrors.add(!querySuccess);
    });

    sleep(0.5);

    group('Frontend Health', function () {
        const frontendRes = http.get(`${FRONTEND_URL}/`);
        
        check(frontendRes, {
            'Frontend status is 200': (r) => r.status === 200,
            'Frontend returns HTML': (r) => r.body.includes('<!DOCTYPE html>') || r.body.includes('<html'),
        });
    });

    sleep(1);
}

// Summary at the end of the test
export function handleSummary(data) {
    return {
        'stdout': textSummary(data, { indent: ' ', enableColors: true }),
        'summary.json': JSON.stringify(data, null, 2),
    };
}

function textSummary(data, opts) {
    const metrics = data.metrics;
    let summary = '\n========== CityAirQ Load Test Summary ==========\n\n';
    
    summary += `Total Requests: ${data.metrics.http_reqs?.values?.count || 0}\n`;
    summary += `Failed Requests: ${data.metrics.http_req_failed?.values?.passes || 0}\n`;
    summary += `Avg Response Time: ${(data.metrics.http_req_duration?.values?.avg || 0).toFixed(2)}ms\n`;
    summary += `P95 Response Time: ${(data.metrics.http_req_duration?.values?.['p(95)'] || 0).toFixed(2)}ms\n`;
    summary += `Route Requests: ${data.metrics.route_requests?.values?.count || 0}\n`;
    summary += `Query Requests: ${data.metrics.query_requests?.values?.count || 0}\n`;
    summary += `Route Error Rate: ${((data.metrics.route_errors?.values?.rate || 0) * 100).toFixed(2)}%\n`;
    summary += `Query Error Rate: ${((data.metrics.query_errors?.values?.rate || 0) * 100).toFixed(2)}%\n`;
    
    summary += '\n=================================================\n';
    
    return summary;
}