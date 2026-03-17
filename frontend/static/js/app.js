// API URL - use proxy endpoints
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

// Map click mode: 'start', 'end', 'query-center', or null
let clickMode = null;

// Custom icons
const startIcon = L.divIcon({
    className: 'custom-marker',
    html: '<div style="width:28px; height:28px; background:#00cc66; border:3px solid #fff; border-radius:4px; box-shadow:0 2px 6px rgba(0,0,0,0.4); display:flex; align-items:center; justify-content:center; color:#fff; font-weight:bold; font-size:14px;">S</div>',
    iconSize: [28, 28],
    iconAnchor: [14, 14]
});

const endIcon = L.divIcon({
    className: 'custom-marker',
    html: '<div style="width:28px; height:28px; background:#ff4444; border:3px solid #fff; border-radius:4px; box-shadow:0 2px 6px rgba(0,0,0,0.4); display:flex; align-items:center; justify-content:center; color:#fff; font-weight:bold; font-size:18px;">&#10005;</div>',
    iconSize: [28, 28],
    iconAnchor: [14, 14]
});

// Calculate combined Air Quality Index (PM10 + PM2.5 only)
function calculateAQI(pm10, pm2_5) {
    const pm10Val = (pm10 && pm10 >= 0) ? pm10 : 0;
    const pm25Val = (pm2_5 && pm2_5 >= 0) ? pm2_5 * 1.5 : 0;
    
    if (pm10Val === 0 && pm25Val === 0) return 50; // Default
    
    const count = (pm10Val > 0 ? 1 : 0) + (pm25Val > 0 ? 1 : 0);
    return (pm10Val + pm25Val) / count;
}

// Get pollution color based on AQI
function getPollutionColor(aqi) {
    if (aqi <= 50) return '#00ff00';
    if (aqi <= 100) return '#ffff00';
    if (aqi <= 150) return '#ff8800';
    return '#ff0000';
}

// Get selected transport mode
function getTransportMode() {
    const selected = document.querySelector('input[name="transport-mode"]:checked');
    return selected ? selected.value : 'bicycle';
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

// Set query center from map click
function setQueryCenterFromMap() {
    clickMode = 'query-center';
    map.getContainer().style.cursor = 'crosshair';
    showMessage('Click on the map to set query center', 'info');
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
    } else if (clickMode === 'query-center') {
        document.getElementById('query-lat').value = e.latlng.lat.toFixed(4);
        document.getElementById('query-lon').value = e.latlng.lng.toFixed(4);
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

// Show message in Results section
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

// Clear route from map
function clearRoute() {
    routeLayer.clearLayers();
    markersLayer.clearLayers();
    startMarker = null;
    endMarker = null;
    document.getElementById('results-section').style.display = 'none';
}

// Clear pollution data from map and results
function clearPollutionData() {
    pollutionLayer.clearLayers();
    document.getElementById('results-section').style.display = 'none';
}

// Get selected sensor types for route
function getRouteSensorTypes() {
    const sensorTypes = [];
    if (document.getElementById('sensor-fixed').checked) sensorTypes.push('fixed');
    if (document.getElementById('sensor-mobile').checked) sensorTypes.push('mobile');
    return sensorTypes;
}

// Get selected sensor types for query
function getQuerySensorTypes() {
    const sensorTypes = [];
    if (document.getElementById('query-sensor-fixed').checked) sensorTypes.push('fixed');
    if (document.getElementById('query-sensor-mobile').checked) sensorTypes.push('mobile');
    return sensorTypes;
}

// Calculate route
async function calculateRoute() {
    // Validate sensor types
    const sensorTypes = getRouteSensorTypes();
    if (sensorTypes.length === 0) {
        showMessage('Please select at least one sensor type (Fixed or Mobile)', 'info');
        return;
    }
    
    const startLat = parseFloat(document.getElementById('start-lat').value);
    const startLon = parseFloat(document.getElementById('start-lon').value);
    const endLat = parseFloat(document.getElementById('end-lat').value);
    const endLon = parseFloat(document.getElementById('end-lon').value);
    const alpha = parseFloat(document.getElementById('alpha').value);
    const transportMode = getTransportMode();
    
    if (isNaN(startLat) || isNaN(startLon) || isNaN(endLat) || isNaN(endLon)) {
        showMessage('Please enter valid coordinates', 'error');
        return;
    }
    
    const originalStart = { lat: startLat, lon: startLon };
    const originalEnd = { lat: endLat, lon: endLon };
    
    const modeText = transportMode === 'bicycle' ? 'Calculating cycling route...' : 'Calculating walking route...';
    document.getElementById('loading-text').textContent = modeText;
    document.getElementById('loading').style.display = 'flex';
    
    try {
        const response = await fetch(`${API_URL}/route/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                start: { lat: startLat, lon: startLon },
                goal: { lat: endLat, lon: endLon },
                alpha: alpha,
                sensor_types: sensorTypes,
                heuristic: 'haversine',
                transport_mode: transportMode
            })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            const errorMsg = data.detail || 'Route calculation failed';
            if (errorMsg.includes('No pollution data') || errorMsg.includes('No path found')) {
                showMessage('Not enough pollution data in the selected area to calculate a route.', 'error');
            } else if (errorMsg.includes('Google Routes') || errorMsg.includes('not configured')) {
                showMessage('Bicycle routing is not available. Please try "By Foot" mode.', 'error');
            } else {
                showMessage(`Error: ${errorMsg}`, 'error');
            }
            return;
        }
        
        if (!data.route || !data.route.properties || !data.waypoints || data.waypoints.length === 0) {
            showMessage('Not enough pollution data in the selected area to calculate a route.', 'error');
            return;
        }
        
        displayRoute(data, originalStart, originalEnd);
        
    } catch (error) {
        console.error('Route error:', error);
        showMessage('Cannot connect to server. Please check your connection.', 'error');
    } finally {
        document.getElementById('loading').style.display = 'none';
    }
}

// Display route on map
function displayRoute(data, originalStart, originalEnd) {
    routeLayer.clearLayers();
    
    const route = data.route;
    const waypoints = data.waypoints;
    const props = route.properties;
    const isBicycleMode = props.transport_mode === 'bicycle';
    
    const firstWaypoint = waypoints[0];
    const lastWaypoint = waypoints[waypoints.length - 1];
    
    // Get colors for first and last waypoints
    const firstAqi = firstWaypoint.aqi || calculateAQI(firstWaypoint.pm10, firstWaypoint.pm2_5);
    const firstColor = getPollutionColor(firstAqi);
    
    const lastAqi = lastWaypoint.aqi || calculateAQI(lastWaypoint.pm10, lastWaypoint.pm2_5);
    const lastColor = getPollutionColor(lastAqi);
    
    // For bicycle mode, draw the full route from Google (real roads)
    if (isBicycleMode && route.geometry && route.geometry.coordinates) {
        // Convert GeoJSON coordinates [lon, lat] to Leaflet [lat, lon]
        const routeCoords = route.geometry.coordinates.map(c => [c[1], c[0]]);
        
        // Draw route with gradient based on AQI
        const avgAqi = props.avg_aqi || 50;
        const routeColor = getPollutionColor(avgAqi);
        
        L.polyline(routeCoords, {
            color: routeColor,
            weight: 6,
            opacity: 0.8
        }).addTo(routeLayer);
        
        // Add waypoint markers for sampled points
        waypoints.forEach((wp, index) => {
            if (index === 0 || index === waypoints.length - 1) return;
            
            const aqi = wp.aqi || calculateAQI(wp.pm10, wp.pm2_5);
            const color = getPollutionColor(aqi);
            
            L.circleMarker([wp.lat, wp.lon], {
                radius: 6,
                fillColor: color,
                color: '#fff',
                weight: 1,
                fillOpacity: 0.8
            })
            .bindPopup(`
                <strong>Sample Point ${index}</strong><br>
                <hr style="margin: 5px 0;">
                PM10: ${formatValue(wp.pm10)} ug/m3<br>
                PM2.5: ${formatValue(wp.pm2_5)} ug/m3<br>
                <strong>AQI: ${(wp.aqi || aqi).toFixed(0)}</strong>
            `)
            .addTo(routeLayer);
        });
    } else {
        // Foot mode - original behavior with grid-based routing
        
        // Line from original start to first waypoint
        if (Math.abs(originalStart.lat - firstWaypoint.lat) > 0.0001 || 
            Math.abs(originalStart.lon - firstWaypoint.lon) > 0.0001) {
            L.polyline(
                [[originalStart.lat, originalStart.lon], [firstWaypoint.lat, firstWaypoint.lon]],
                { color: firstColor, weight: 8, opacity: 0.9 }
            ).addTo(routeLayer);
        }
        
        // Line from last waypoint to original end
        if (Math.abs(originalEnd.lat - lastWaypoint.lat) > 0.0001 || 
            Math.abs(originalEnd.lon - lastWaypoint.lon) > 0.0001) {
            L.polyline(
                [[lastWaypoint.lat, lastWaypoint.lon], [originalEnd.lat, originalEnd.lon]],
                { color: lastColor, weight: 8, opacity: 0.9 }
            ).addTo(routeLayer);
        }
        
        // Main route with pollution colors
        if (waypoints.length > 1) {
            for (let i = 0; i < waypoints.length - 1; i++) {
                const start = waypoints[i];
                const end = waypoints[i + 1];
                const aqi = start.aqi || calculateAQI(start.pm10, start.pm2_5);
                const color = getPollutionColor(aqi);
                
                L.polyline([[start.lat, start.lon], [end.lat, end.lon]], {
                    color: color,
                    weight: 8,
                    opacity: 0.9
                }).addTo(routeLayer);
            }
        }
        
        // Waypoint markers
        waypoints.forEach((wp, index) => {
            if (index === 0 || index === waypoints.length - 1) return;
            
            const aqi = wp.aqi || calculateAQI(wp.pm10, wp.pm2_5);
            const color = getPollutionColor(aqi);
            
            L.circleMarker([wp.lat, wp.lon], {
                radius: 10,
                fillColor: color,
                color: '#fff',
                weight: 2,
                fillOpacity: 0.9
            })
            .bindPopup(`
                <strong>Waypoint ${index}</strong><br>
                <hr style="margin: 5px 0;">
                PM10: ${formatValue(wp.pm10)} ug/m3<br>
                PM2.5: ${formatValue(wp.pm2_5)} ug/m3<br>
                <strong>AQI: ${(wp.aqi || aqi).toFixed(0)}</strong>
            `)
            .addTo(routeLayer);
        });
    }
    
    updateStartMarker(originalStart.lat, originalStart.lon);
    updateEndMarker(originalEnd.lat, originalEnd.lon);
    
    const allPoints = [
        [originalStart.lat, originalStart.lon],
        [originalEnd.lat, originalEnd.lon],
        ...route.geometry.coordinates.map(c => [c[1], c[0]])
    ];
    const bounds = L.latLngBounds(allPoints);
    map.fitBounds(bounds, { padding: [50, 50] });
    
    displayRouteResults(props);
}

// Format pollution value (handle null/-1)
function formatValue(val) {
    if (val === null || val === undefined || val < 0) return 'N/A';
    return val.toFixed(1);
}

// Display route results
function displayRouteResults(props) {
    const resultsSection = document.getElementById('results-section');
    const resultsDiv = document.getElementById('route-results');
    
    resultsSection.style.display = 'block';
    
    const isBicycleMode = props.transport_mode === 'bicycle';
    const modeClass = isBicycleMode ? 'bicycle-mode' : 'foot-mode';
    const modeLabel = isBicycleMode ? 'BICYCLE' : 'FOOT';    
    
    let resultsHtml = `
        <div class="result-item">
            <span class="result-label">Mode</span>
            <span class="result-value ${modeClass}">${modeLabel}</span>
        </div>
        <div class="result-item">
            <span class="result-label">Distance</span>
            <span class="result-value">${props.distance_km.toFixed(2)} km</span>
        </div>
    `;
    
    // Show duration only for bicycle mode
    if (isBicycleMode && props.duration_minutes) {
        resultsHtml += `
        <div class="result-item">
            <span class="result-label">Duration</span>
            <span class="result-value">${props.duration_minutes.toFixed(1)} min</span>
        </div>
        `;
    }
    
    resultsHtml += `
        <div class="result-item">
            <span class="result-label">Avg AQI</span>
            <span class="result-value">${(props.avg_aqi || 0).toFixed(0)}</span>
        </div>
        <div class="result-item">
            <span class="result-label">Avg PM10</span>
            <span class="result-value">${(props.avg_pm10 || 0).toFixed(1)} ug/m3</span>
        </div>
        <div class="result-item">
            <span class="result-label">Avg PM2.5</span>
            <span class="result-value">${(props.avg_pm2_5 || 0).toFixed(1)} ug/m3</span>
        </div>
        <div class="result-item">
            <span class="result-label">Calculation Time</span>
            <span class="result-value">${props.calculation_time_ms.toFixed(0)} ms</span>
        </div>
    `;
    
    // Show nodes evaluated for foot mode, routes considered for bicycle mode
    if (isBicycleMode && props.google_routes_considered) {
        resultsHtml += `
        <div class="result-item">
            <span class="result-label">Routes Compared</span>
            <span class="result-value">${props.google_routes_considered}</span>
        </div>
        `;
    } else if (props.nodes_evaluated) {
        resultsHtml += `
        <div class="result-item">
            <span class="result-label">Nodes Evaluated</span>
            <span class="result-value">${props.nodes_evaluated}</span>
        </div>
        `;
    }
    
    resultsHtml += `
        <div class="result-item">
            <span class="result-label">Cache HIT</span>
            <span class="result-value ${props.cached ? 'cached' : ''}">${props.cached ? 'Yes' : 'No'}</span>
        </div>
    `;
    
    resultsDiv.innerHTML = resultsHtml;
}

// Query pollution data
async function queryPollutionData() {
    // Validate sensor types FIRST
    const sensorTypes = getQuerySensorTypes();
    if (sensorTypes.length === 0) {
        showMessage('Please select at least one sensor type (Fixed or Mobile)', 'info');
        return;
    }
    
    const lat = parseFloat(document.getElementById('query-lat').value);
    const lon = parseFloat(document.getElementById('query-lon').value);
    const radius = parseFloat(document.getElementById('query-radius').value);
    
    if (isNaN(lat) || isNaN(lon) || isNaN(radius)) {
        showMessage('Please enter valid coordinates and radius', 'error');
        return;
    }
    
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
                layers: ['pm10', 'pm2_5'],
                sensor_types: sensorTypes
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

// Display pollution data
function displayPollutionData(readings, centerLat, centerLon, radius) {
    pollutionLayer.clearLayers();
    
    L.circle([centerLat, centerLon], {
        radius: radius * 1000,
        color: '#00d9ff',
        fillColor: '#00d9ff',
        fillOpacity: 0.1,
        weight: 2
    }).addTo(pollutionLayer);
    
    let fixedCount = 0;
    let mobileCount = 0;
    
    readings.forEach(reading => {
        // Handle both dict and array formats
        let sensorId, timestamp, lat, lon, pm10, pm2_5;
        
        if (Array.isArray(reading)) {
            sensorId = reading[0];
            timestamp = reading[1];
            lat = reading[2];
            lon = reading[3];
            pm10 = reading[4];
            pm2_5 = reading[5];
        } else {
            sensorId = reading.sensor_id;
            timestamp = reading.timestamp;
            lat = reading.latitude;
            lon = reading.longitude;
            pm10 = reading.pm10;
            pm2_5 = reading.pm2_5;
        }
        
        const sensorType = sensorId.startsWith('F') ? 'Fixed' : 'Mobile';
        if (sensorType === 'Mobile') mobileCount++;
        else fixedCount++;
        
        const aqi = calculateAQI(pm10, pm2_5);
        const color = getPollutionColor(aqi);
        
        const markerOptions = {
            radius: sensorType === 'Fixed' ? 12 : 10,
            fillColor: color,
            color: sensorType === 'Fixed' ? '#fff' : '#333',
            weight: sensorType === 'Fixed' ? 2 : 3,
            fillOpacity: 0.9
        };
        
        L.circleMarker([lat, lon], markerOptions)
        .bindPopup(`
            <strong>${sensorId}</strong> <em>(${sensorType})</em><br>
            <small>${timestamp}</small><br>
            <hr style="margin: 5px 0;">
            PM10: ${formatValue(pm10)} ug/m3<br>
            PM2.5: ${formatValue(pm2_5)} ug/m3<br>
            <strong>AQI: ${aqi.toFixed(0)}</strong>
        `)
        .addTo(pollutionLayer);
    });
    
    if (readings.length > 0) {
        const getCoords = r => Array.isArray(r) ? [r[2], r[3]] : [r.latitude, r.longitude];
        const bounds = L.latLngBounds(readings.map(getCoords));
        map.fitBounds(bounds, { padding: [50, 50] });
    }
    
    showMessage(`Found ${readings.length} readings (${fixedCount} fixed, ${mobileCount} mobile)`, 'success');
}
