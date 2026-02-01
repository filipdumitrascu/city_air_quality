// API URL - use proxy endpoints (same origin, no CORS issues)
const API_URL = "/api";

// Map initialization
const map = L.map('map').setView([44.4268, 26.1025], 13);

// OpenStreetMap tile layer
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
}).addTo(map);

// Layer groups
let routeLayer = L.layerGroup().addTo(map);
let markersLayer = L.layerGroup().addTo(map);
let pollutionLayer = L.layerGroup().addTo(map);

// Markers for start/end
let startMarker = null;
let endMarker = null;

// Map click mode
let clickMode = null;

// Custom icons - Square for start, X for end
const startIcon = L.divIcon({
    className: 'custom-marker',
    html: '<div style="width:24px; height:24px; background:#00cc66; border:3px solid #fff; border-radius:4px; box-shadow:0 2px 6px rgba(0,0,0,0.4); display:flex; align-items:center; justify-content:center; color:#fff; font-weight:bold; font-size:12px;">S</div>',
    iconSize: [24, 24],
    iconAnchor: [12, 12]
});

const endIcon = L.divIcon({
    className: 'custom-marker',
    html: '<div style="width:24px; height:24px; background:#ff4444; border:3px solid #fff; border-radius:4px; box-shadow:0 2px 6px rgba(0,0,0,0.4); display:flex; align-items:center; justify-content:center; color:#fff; font-weight:bold; font-size:16px;">✕</div>',
    iconSize: [24, 24],
    iconAnchor: [12, 12]
});

// Calculate combined Air Quality Index from multiple pollutants
function calculateAQI(pm10, pm25, no2) {
    const pm10Index = pm10 || 0;
    const pm25Index = (pm25 || 0) * 1.5;
    const no2Index = (no2 || 0) * 0.8;
    return (pm10Index + pm25Index + no2Index) / 3.3;
}

// Get pollution color based on combined AQI
function getPollutionColor(aqi) {
    if (aqi <= 50) return '#00ff00';
    if (aqi <= 100) return '#ffff00';
    if (aqi <= 150) return '#ff8800';
    return '#ff0000';
}

// Set start point from map click
function setStartFromMap() {
    clickMode = 'start';
    map.getContainer().style.cursor = 'crosshair';
    showMessage('Click on the map to set start point', 'info');
}

// Set end point from map click
function setEndFromMap() {
    clickMode = 'end';
    map.getContainer().style.cursor = 'crosshair';
    showMessage('Click on the map to set end point', 'info');
}

// Map click handler
map.on('click', function(e) {
    if (clickMode === 'start') {
        document.getElementById('start-lat').value = e.latlng.lat.toFixed(4);
        document.getElementById('start-lon').value = e.latlng.lng.toFixed(4);
        updateStartMarker(e.latlng.lat, e.latlng.lng);
        clickMode = null;
        map.getContainer().style.cursor = '';
        hideMessage();
    } else if (clickMode === 'end') {
        document.getElementById('end-lat').value = e.latlng.lat.toFixed(4);
        document.getElementById('end-lon').value = e.latlng.lng.toFixed(4);
        updateEndMarker(e.latlng.lat, e.latlng.lng);
        clickMode = null;
        map.getContainer().style.cursor = '';
        hideMessage();
    }
});

// Update start marker
function updateStartMarker(lat, lon) {
    if (startMarker) {
        markersLayer.removeLayer(startMarker);
    }
    startMarker = L.marker([lat, lon], {icon: startIcon})
        .bindPopup('<strong>Start Point</strong>')
        .addTo(markersLayer);
}

// Update end marker
function updateEndMarker(lat, lon) {
    if (endMarker) {
        markersLayer.removeLayer(endMarker);
    }
    endMarker = L.marker([lat, lon], {icon: endIcon})
        .bindPopup('<strong>End Point</strong>')
        .addTo(markersLayer);
}

// Show message
function showMessage(message, type) {
    const resultsSection = document.getElementById('results-section');
    const resultsDiv = document.getElementById('route-results');
    
    resultsSection.style.display = 'block';
    
    const className = type === 'error' ? 'error-message' : 
                      type === 'success' ? 'success-message' : 'info-message';
    
    resultsDiv.innerHTML = `<div class="${className}">${message}</div>`;
}

// Hide message
function hideMessage() {
    document.getElementById('results-section').style.display = 'none';
}

// Clear route from map (including start/end markers)
function clearRoute() {
    routeLayer.clearLayers();
    markersLayer.clearLayers();
    startMarker = null;
    endMarker = null;
    document.getElementById('results-section').style.display = 'none';
}

// Clear pollution data from map
function clearPollutionData() {
    pollutionLayer.clearLayers();
}

// Calculate route
async function calculateRoute() {
    const startLat = parseFloat(document.getElementById('start-lat').value);
    const startLon = parseFloat(document.getElementById('start-lon').value);
    const endLat = parseFloat(document.getElementById('end-lat').value);
    const endLon = parseFloat(document.getElementById('end-lon').value);
    const alpha = parseFloat(document.getElementById('alpha').value);
    
    const sensorTypes = [];
    if (document.getElementById('sensor-fixed').checked) sensorTypes.push('fixed');
    if (document.getElementById('sensor-mobile').checked) sensorTypes.push('mobile');
    
    if (isNaN(startLat) || isNaN(startLon) || isNaN(endLat) || isNaN(endLon)) {
        showMessage('Please enter valid coordinates', 'error');
        return;
    }
    
    // Show loading with correct text
    document.getElementById('loading-text').textContent = 'Calculating route...';
    document.getElementById('loading').style.display = 'flex';
    
    try {
        const response = await fetch(`${API_URL}/route/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                start: { lat: startLat, lon: startLon },
                goal: { lat: endLat, lon: endLon },
                alpha: alpha,
                sensor_types: sensorTypes
            })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            const errorMsg = data.detail || 'Route calculation failed';
            if (errorMsg.includes('No pollution data') || errorMsg.includes('No path found')) {
                showMessage('Not enough pollution data in the selected area to calculate a route.', 'error');
            } else {
                showMessage(`Error: ${errorMsg}`, 'error');
            }
            return;
        }
        
        if (!data.route || !data.route.properties || !data.waypoints || data.waypoints.length === 0) {
            showMessage('Not enough pollution data in the selected area to calculate a route.', 'error');
            return;
        }
        
        displayRoute(data);
        
    } catch (error) {
        console.error('Route error:', error);
        showMessage('Cannot connect to server. Please check your connection.', 'error');
    } finally {
        document.getElementById('loading').style.display = 'none';
    }
}


// Display route on map
function displayRoute(data) {
    routeLayer.clearLayers();
    
    const route = data.route;
    const waypoints = data.waypoints;
    const props = route.properties;
    
    // Draw route line with color based on AQI
    if (waypoints.length > 1) {
        for (let i = 0; i < waypoints.length - 1; i++) {
            const start = waypoints[i];
            const end = waypoints[i + 1];
            const aqi = start.aqi || calculateAQI(start.pm10, start.pm25, start.no2);
            const color = getPollutionColor(aqi);
            
            L.polyline([[start.lat, start.lon], [end.lat, end.lon]], {
                color: color,
                weight: 6,
                opacity: 0.8
            }).addTo(routeLayer);
        }
    }
    
    // Add waypoint markers (skip first and last)
    waypoints.forEach((wp, index) => {
        if (index === 0 || index === waypoints.length - 1) return;
        
        const aqi = wp.aqi || calculateAQI(wp.pm10, wp.pm25, wp.no2);
        const color = getPollutionColor(aqi);
        
        L.circleMarker([wp.lat, wp.lon], {
            radius: 8,
            fillColor: color,
            color: '#fff',
            weight: 2,
            fillOpacity: 0.8
        })
        .bindPopup(`
            <strong>Waypoint ${index}</strong><br>
            <hr style="margin: 5px 0;">
            PM10: ${(wp.pm10 || 0).toFixed(1)} µg/m³<br>
            PM2.5: ${(wp.pm25 || 0).toFixed(1)} µg/m³<br>
            NO2: ${(wp.no2 || 0).toFixed(1)} µg/m³<br>
            <strong>AQI: ${(wp.aqi || 0).toFixed(0)}</strong>
        `)
        .addTo(routeLayer);
    });
    
    // Update start/end markers
    if (waypoints.length > 0) {
        updateStartMarker(waypoints[0].lat, waypoints[0].lon);
        updateEndMarker(waypoints[waypoints.length - 1].lat, waypoints[waypoints.length - 1].lon);
    }
    
    // Fit map
    if (route.geometry.coordinates.length > 0) {
        const bounds = L.latLngBounds(route.geometry.coordinates.map(c => [c[1], c[0]]));
        map.fitBounds(bounds, { padding: [50, 50] });
    }
    
    displayResults(props);
}

// Display route results with all pollutants
function displayResults(props) {
    const resultsSection = document.getElementById('results-section');
    const resultsDiv = document.getElementById('route-results');
    
    resultsSection.style.display = 'block';
    
    resultsDiv.innerHTML = `
        <div class="result-item">
            <span class="result-label">Distance</span>
            <span class="result-value">${props.distance_km.toFixed(2)} km</span>
        </div>
        <div class="result-item">
            <span class="result-label">Avg AQI</span>
            <span class="result-value">${(props.avg_aqi || 0).toFixed(0)}</span>
        </div>
        <div class="result-item">
            <span class="result-label">Avg PM10</span>
            <span class="result-value">${props.avg_pollution_pm10.toFixed(1)} µg/m³</span>
        </div>
        <div class="result-item">
            <span class="result-label">Avg PM2.5</span>
            <span class="result-value">${(props.avg_pollution_pm25 || 0).toFixed(1)} µg/m³</span>
        </div>
        <div class="result-item">
            <span class="result-label">Avg NO2</span>
            <span class="result-value">${(props.avg_pollution_no2 || 0).toFixed(1)} µg/m³</span>
        </div>
        <div class="result-item">
            <span class="result-label">Calculation Time</span>
            <span class="result-value">${props.calculation_time_ms.toFixed(0)} ms</span>
        </div>
        <div class="result-item">
            <span class="result-label">Nodes Evaluated</span>
            <span class="result-value">${props.nodes_evaluated}</span>
        </div>
        <div class="result-item">
            <span class="result-label">Cached</span>
            <span class="result-value ${props.cached ? 'cached' : ''}">${props.cached ? 'Yes' : 'No'}</span>
        </div>
    `;
}

// Query pollution data
async function queryPollutionData() {
    const lat = parseFloat(document.getElementById('query-lat').value);
    const lon = parseFloat(document.getElementById('query-lon').value);
    const radius = parseFloat(document.getElementById('query-radius').value);
    
    if (isNaN(lat) || isNaN(lon) || isNaN(radius)) {
        showMessage('Please enter valid coordinates and radius', 'error');
        return;
    }
    
    // Show loading with correct text
    document.getElementById('loading-text').textContent = 'Fetching pollution data...';
    document.getElementById('loading').style.display = 'flex';
    
    try {
        const response = await fetch(`${API_URL}/results/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                latitude: lat,
                longitude: lon,
                radius: radius,
                layers: ['pm10', 'pm25', 'no2']
            })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            const errorMsg = data.detail || 'Query failed';
            if (errorMsg.includes('No data found') || errorMsg.includes('Timeout')) {
                showMessage('No pollution measurements found in the selected area.', 'error');
            } else {
                showMessage(`Error: ${errorMsg}`, 'error');
            }
            return;
        }
        
        if (!data.data || data.data.length === 0) {
            showMessage('No pollution measurements found in the selected area.', 'error');
            return;
        }
        
        displayPollutionData(data.data, lat, lon, radius);
        
    } catch (error) {
        console.error('Query error:', error);
        showMessage('Cannot connect to server. Please check your connection.', 'error');
    } finally {
        document.getElementById('loading').style.display = 'none';
    }
}

// Display pollution data on map
function displayPollutionData(readings, centerLat, centerLon, radius) {
    pollutionLayer.clearLayers();
    
    L.circle([centerLat, centerLon], {
        radius: radius * 1000,
        color: '#00d9ff',
        fillColor: '#00d9ff',
        fillOpacity: 0.1,
        weight: 2
    }).addTo(pollutionLayer);
    
    readings.forEach(reading => {
        const sensorId = reading[0];
        const timestamp = reading[1];
        const lat = reading[2];
        const lon = reading[3];
        const pm10 = reading[4];
        const pm25 = reading[5];
        const no2 = reading[6];
        
        const aqi = calculateAQI(pm10, pm25, no2);
        const color = getPollutionColor(aqi);
        
        L.circleMarker([lat, lon], {
            radius: 12,
            fillColor: color,
            color: '#fff',
            weight: 2,
            fillOpacity: 0.9
        })
        .bindPopup(`
            <strong>${sensorId}</strong><br>
            <small>${timestamp}</small><br>
            <hr style="margin: 5px 0;">
            PM10: ${pm10.toFixed(1)} µg/m³<br>
            PM2.5: ${pm25.toFixed(1)} µg/m³<br>
            NO2: ${no2.toFixed(1)} µg/m³
        `)
        .addTo(pollutionLayer);
    });
    
    if (readings.length > 0) {
        const bounds = L.latLngBounds(readings.map(r => [r[2], r[3]]));
        map.fitBounds(bounds, { padding: [50, 50] });
    }
    
    showMessage(`Found ${readings.length} pollution readings`, 'success');
}
