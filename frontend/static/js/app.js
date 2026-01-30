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
let clickMode = null; // 'start', 'end', or null

// Custom icons
const startIcon = L.divIcon({
    className: 'custom-marker start-marker',
    html: '<div style="background:#00ff88; width:20px; height:20px; border-radius:50%; border:3px solid #fff; box-shadow: 0 2px 5px rgba(0,0,0,0.3);"></div>',
    iconSize: [20, 20],
    iconAnchor: [10, 10]
});

const endIcon = L.divIcon({
    className: 'custom-marker end-marker',
    html: '<div style="background:#ff4444; width:20px; height:20px; border-radius:50%; border:3px solid #fff; box-shadow: 0 2px 5px rgba(0,0,0,0.3);"></div>',
    iconSize: [20, 20],
    iconAnchor: [10, 10]
});

// Get pollution color based on PM10 value
function getPollutionColor(pm10) {
    if (pm10 <= 50) return '#00ff00';      // Good - green
    if (pm10 <= 100) return '#ffff00';     // Moderate - yellow
    if (pm10 <= 150) return '#ff8800';     // Unhealthy - orange
    return '#ff0000';                       // Very unhealthy - red
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
    } else if (clickMode === 'end') {
        document.getElementById('end-lat').value = e.latlng.lat.toFixed(4);
        document.getElementById('end-lon').value = e.latlng.lng.toFixed(4);
        updateEndMarker(e.latlng.lat, e.latlng.lng);
        clickMode = null;
        map.getContainer().style.cursor = '';
    }
});

// Update start marker
function updateStartMarker(lat, lon) {
    if (startMarker) {
        markersLayer.removeLayer(startMarker);
    }
    startMarker = L.marker([lat, lon], {icon: startIcon})
        .bindPopup('Start Point')
        .addTo(markersLayer);
}

// Update end marker
function updateEndMarker(lat, lon) {
    if (endMarker) {
        markersLayer.removeLayer(endMarker);
    }
    endMarker = L.marker([lat, lon], {icon: endIcon})
        .bindPopup('End Point')
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

// Calculate route
async function calculateRoute() {
    const startLat = parseFloat(document.getElementById('start-lat').value);
    const startLon = parseFloat(document.getElementById('start-lon').value);
    const endLat = parseFloat(document.getElementById('end-lat').value);
    const endLon = parseFloat(document.getElementById('end-lon').value);
    const alpha = parseFloat(document.getElementById('alpha').value);
    
    // Get sensor types
    const sensorTypes = [];
    if (document.getElementById('sensor-fixed').checked) sensorTypes.push('fixed');
    if (document.getElementById('sensor-mobile').checked) sensorTypes.push('mobile');
    
    // Validate
    if (isNaN(startLat) || isNaN(startLon) || isNaN(endLat) || isNaN(endLon)) {
        showMessage('Please enter valid coordinates', 'error');
        return;
    }
    
    // Show loading
    document.getElementById('loading').style.display = 'flex';
    
    try {
        const response = await fetch(`${API_URL}/route/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                start: { lat: startLat, lon: startLon },
                goal: { lat: endLat, lon: endLon },
                alpha: alpha,
                sensor_types: sensorTypes
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Route calculation failed');
        }
        
        const data = await response.json();
        displayRoute(data);
        
    } catch (error) {
        showMessage(`Error: ${error.message}`, 'error');
    } finally {
        document.getElementById('loading').style.display = 'none';
    }
}

// Display route on map
function displayRoute(data) {
    // Clear previous route
    routeLayer.clearLayers();
    
    const route = data.route;
    const waypoints = data.waypoints;
    const props = route.properties;
    
    // Draw route line with gradient based on pollution
    if (waypoints.length > 1) {
        for (let i = 0; i < waypoints.length - 1; i++) {
            const start = waypoints[i];
            const end = waypoints[i + 1];
            const color = getPollutionColor(start.pollution_level);
            
            L.polyline(
                [[start.lat, start.lon], [end.lat, end.lon]],
                {
                    color: color,
                    weight: 6,
                    opacity: 0.8
                }
            ).addTo(routeLayer);
        }
    } else if (route.geometry.coordinates.length > 0) {
        // Fallback: draw simple line
        const coords = route.geometry.coordinates.map(c => [c[1], c[0]]);
        L.polyline(coords, {
            color: '#00d9ff',
            weight: 6,
            opacity: 0.8
        }).addTo(routeLayer);
    }
    
    // Add waypoint markers
    waypoints.forEach((wp, index) => {
        const color = getPollutionColor(wp.pollution_level);
        
        L.circleMarker([wp.lat, wp.lon], {
            radius: 8,
            fillColor: color,
            color: '#fff',
            weight: 2,
            fillOpacity: 0.8
        })
        .bindPopup(`
            <strong>Waypoint ${index + 1}</strong><br>
            Lat: ${wp.lat.toFixed(4)}<br>
            Lon: ${wp.lon.toFixed(4)}<br>
            PM10: ${wp.pollution_level.toFixed(1)} µg/m³
        `)
        .addTo(routeLayer);
    });
    
    // Update start/end markers
    if (waypoints.length > 0) {
        updateStartMarker(waypoints[0].lat, waypoints[0].lon);
        updateEndMarker(waypoints[waypoints.length - 1].lat, waypoints[waypoints.length - 1].lon);
    }
    
    // Fit map to route
    if (route.geometry.coordinates.length > 0) {
        const bounds = L.latLngBounds(
            route.geometry.coordinates.map(c => [c[1], c[0]])
        );
        map.fitBounds(bounds, { padding: [50, 50] });
    }
    
    // Display results
    displayResults(props);
}

// Display route results
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
            <span class="result-label">Avg PM10</span>
            <span class="result-value">${props.avg_pollution_pm10.toFixed(1)} µg/m³</span>
        </div>
        <div class="result-item">
            <span class="result-label">Max PM10</span>
            <span class="result-value">${props.max_pollution_pm10.toFixed(1)} µg/m³</span>
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
    
    document.getElementById('loading').style.display = 'flex';
    
    try {
        const response = await fetch(`${API_URL}/results/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                latitude: lat,
                longitude: lon,
                radius: radius,
                layers: ['pm10', 'pm25', 'no2']
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Query failed');
        }
        
        const data = await response.json();
        displayPollutionData(data.data, lat, lon, radius);
        
    } catch (error) {
        showMessage(`Error: ${error.message}`, 'error');
    } finally {
        document.getElementById('loading').style.display = 'none';
    }
}

// Display pollution data on map
function displayPollutionData(readings, centerLat, centerLon, radius) {
    // Clear previous pollution markers
    pollutionLayer.clearLayers();
    
    // Draw query circle
    L.circle([centerLat, centerLon], {
        radius: radius * 1000, // Convert km to meters
        color: '#00d9ff',
        fillColor: '#00d9ff',
        fillOpacity: 0.1,
        weight: 2
    }).addTo(pollutionLayer);
    
    // Add pollution markers
    readings.forEach(reading => {
        // Reading format: [sensor_id, timestamp, lat, lon, pm10, pm25, no2]
        const sensorId = reading[0];
        const timestamp = reading[1];
        const lat = reading[2];
        const lon = reading[3];
        const pm10 = reading[4];
        const pm25 = reading[5];
        const no2 = reading[6];
        
        const color = getPollutionColor(pm10);
        
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
    
    // Fit map to show all markers
    if (readings.length > 0) {
        const bounds = L.latLngBounds(readings.map(r => [r[2], r[3]]));
        map.fitBounds(bounds, { padding: [50, 50] });
    }
    
    showMessage(`Found ${readings.length} pollution readings`, 'success');
}

// Initialize markers from input values
document.addEventListener('DOMContentLoaded', function() {
    const startLat = parseFloat(document.getElementById('start-lat').value);
    const startLon = parseFloat(document.getElementById('start-lon').value);
    const endLat = parseFloat(document.getElementById('end-lat').value);
    const endLon = parseFloat(document.getElementById('end-lon').value);
    
    if (!isNaN(startLat) && !isNaN(startLon)) {
        updateStartMarker(startLat, startLon);
    }
    if (!isNaN(endLat) && !isNaN(endLon)) {
        updateEndMarker(endLat, endLon);
    }
});
