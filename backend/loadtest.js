import http from 'k6/http';
import { check, sleep } from 'k6';

// Configurația load test-ului
export let options = {
    stages: [
        { duration: '30s', target: 100 }, // Ramp-up la 100 utilizatori
        { duration: '2m', target: 100 },  // Menține 100 utilizatori timp de 2 minute
        { duration: '30s', target: 0 },   // Ramp-down la 0 utilizatori
    ],
    thresholds: {
        http_req_duration: ['p(95)<500'], // 95% din requesturi trebuie să răspundă sub 500ms
        http_req_failed: ['rate<0.01'],   // < 1% rată de eroare acceptabilă
    },
};

// Timestamp-ul curent
const currentTimestamp = Math.floor(Date.now() / 1000);

// URL-urile endpointurilor
const ingestUrl = 'https://kong-fea27b0248eua7mms.kongcloud.dev/ingest/';
const resultsUrl = 'https://kong-fea27b0248eua7mms.kongcloud.dev/results/';

export default function () {
    // Generează un clientId random
    let randomClientId = `clientId-${Math.random().toString(36).substring(2, 18)}`;

    // Payload pentru ingestie
    let ingestPayload = JSON.stringify({
        clientId: randomClientId,
        timestamp: 1751293865,
        location: {
            latitude: 45.764043,
            longitude: 4.835659
        },
        data: [
            { dimension: "Temperature", value: 30.5 },
            { dimension: "Humidity", value: 55.2 },
            { dimension: "Pressure", value: 1012.3 },
            { dimension: "Altitude", value: 120.4 },
            { dimension: "CO2", value: 600 },
            { dimension: "PM1.0", value: 10.1 },
            { dimension: "PM2.5", value: 15.3 },
            { dimension: "PM10", value: 18.2 }
        ]
    });

    let headers = { 'Content-Type': 'application/json' };

    // Trimite request către endpoint-ul de ingestie
    let ingestRes = http.post(ingestUrl, ingestPayload, { headers: headers });
    check(ingestRes, { 'Ingest status is 200': (r) => r.status === 200 });

    // Trimite request către endpoint-ul results
    let resultsPayload = JSON.stringify({
        latitude: 45.764043,
        longitude: 4.835659,
        radius: 5,
        layers: ["Temperature", "Humidity", "Pressure", "Altitude", "CO2", "PM1_0", "PM2_5", "PM10"]
    });

    let resultsRes = http.post(resultsUrl, resultsPayload, { headers: headers });

    // Verifică statusul și structura răspunsului
    check(resultsRes, {
        'Results status is 200': (r) => r.status === 200,
        'Results has data': (r) => {
            try {
                let jsonData = JSON.parse(r.body);
                return jsonData.data && Array.isArray(jsonData.data) && jsonData.data.length > 0;
            } catch (e) {
                return false;
            }
        }
    });

    // Pauză de 1s între requesturi
    sleep(1);
}
