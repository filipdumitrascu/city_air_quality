import pytest
import sys
import os
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock Redis
mock_redis = MagicMock()
mock_redis.ping.return_value = True
mock_redis.get.return_value = None
mock_redis.setex = MagicMock()
mock_redis.keys.return_value = []
mock_redis.info.return_value = {"total_commands_processed": 0, "keyspace_hits": 0}
sys.modules['redis'] = MagicMock()
sys.modules['redis'].Redis.return_value = mock_redis

from httpx import AsyncClient


# TEST DATA (pollution_data schema, only pm10 and pm2_5)
MOCK_POLLUTION_DATA = [
    {"sensor_id": "001", "sensor_type": "CityAirQ", "latitude": 44.4268, "longitude": 26.1025, "pm10": 45.3, "pm2_5": 25.2},
    {"sensor_id": "002", "sensor_type": "CityAirQ", "latitude": 44.4270, "longitude": 26.1027, "pm10": 42.1, "pm2_5": 22.8},
    {"sensor_id": "003", "sensor_type": "CityAirQ", "latitude": 44.4272, "longitude": 26.1030, "pm10": 38.7, "pm2_5": 20.5},
    {"sensor_id": "004", "sensor_type": "CityAirQ", "latitude": 44.4275, "longitude": 26.1035, "pm10": 40.2, "pm2_5": 21.1},
    {"sensor_id": "005", "sensor_type": "CityAirQ", "latitude": 44.4278, "longitude": 26.1040, "pm10": 37.5, "pm2_5": 19.8},
    {"sensor_id": "006", "sensor_type": "CityAirQ", "latitude": 44.4280, "longitude": 26.1045, "pm10": 35.2, "pm2_5": 18.3},
    {"sensor_id": "0066A", "sensor_type": "SPO-RO", "latitude": 44.4286, "longitude": 26.1302, "pm10": 50.0, "pm2_5": 30.0},
]

# WearAware sensors (don't measure NO2, but that's fine since we don't use it)
MOCK_POLLUTION_WEARAWARE = [
    {"sensor_id": "001", "sensor_type": "WearAware", "latitude": 44.4269, "longitude": 26.1026, "pm10": 48.0, "pm2_5": 27.0},
    {"sensor_id": "002", "sensor_type": "WearAware", "latitude": 44.4271, "longitude": 26.1029, "pm10": 44.0, "pm2_5": 24.0},
]

# Mixed data with -1 values (should be ignored)
MOCK_POLLUTION_WITH_MISSING = [
    {"sensor_id": "001", "sensor_type": "CityAirQ", "latitude": 44.4268, "longitude": 26.1025, "pm10": 45.3, "pm2_5": -1},  # pm2_5 missing
    {"sensor_id": "002", "sensor_type": "CityAirQ", "latitude": 44.4270, "longitude": 26.1027, "pm10": -1, "pm2_5": 22.8},  # pm10 missing
    {"sensor_id": "003", "sensor_type": "CityAirQ", "latitude": 44.4272, "longitude": 26.1030, "pm10": 38.7, "pm2_5": 20.5},  # Both valid
]

ROUTE_REQUEST_FOOT = {
    "start": {"lat": 44.4268, "lon": 26.1025},
    "goal": {"lat": 44.4280, "lon": 26.1045},
    "alpha": 0.5,
    "sensor_types": ["CityAirQ", "WearAware"],
    "transport_mode": "foot",
    "heuristic": "haversine"
}

ROUTE_REQUEST_BICYCLE = {
    "start": {"lat": 44.4268, "lon": 26.1025},
    "goal": {"lat": 44.4368, "lon": 26.0925},
    "alpha": 0.7,
    "sensor_types": ["SPO-RO", "CityAirQ", "WearAware"],
    "transport_mode": "bicycle"
}


# FIXTURE
@pytest.fixture
def mock_services():
    """Mock external services"""
    with patch('routing_service.data_loader') as mock_loader, \
         patch('routing_service.cache_manager') as mock_cache, \
         patch('routing_service.google_routes_client') as mock_google:
        
        mock_cache.is_connected.return_value = True
        mock_cache.get_cached_route.return_value = None
        mock_cache.generate_cache_key.return_value = "route:test123"
        mock_cache.cache_route = MagicMock()
        mock_cache.redis_client = mock_redis
        
        mock_loader.fetch_area_pollution = AsyncMock(return_value=MOCK_POLLUTION_DATA)
        mock_loader.fetch_route_pollution = AsyncMock(return_value=MOCK_POLLUTION_DATA)
        mock_loader.fetch_pollution_data = AsyncMock(return_value=MOCK_POLLUTION_DATA)
        
        mock_google.is_configured.return_value = True
        mock_google.get_routes_with_pollution = AsyncMock(return_value=(
            {
                "index": 0,
                "path": [(44.4268, 26.1025), (44.4300, 26.1000), (44.4368, 26.0925)],
                "distance_km": 1.5,
                "duration_minutes": 8.0,
                "sampled_waypoints": [(44.4268, 26.1025), (44.4368, 26.0925)],
                "pollution": {
                    "avg_pm10": 42.0, "max_pm10": 50.0,
                    "avg_pm2_5": 23.0, "max_pm2_5": 30.0,
                    "avg_aqi": 45.0, "max_aqi": 55.0
                },
                "score": 0.5
            },
            [{"index": 0}, {"index": 1}]
        ))
        mock_google.get_pollution_at_point = MagicMock(return_value={"pm10": 40, "pm2_5": 22, "aqi": 45})
        
        yield mock_loader, mock_cache, mock_google


# HEALTH ENDPOINT TESTS
@pytest.mark.asyncio
async def test_root_endpoint(mock_services):
    from routing_service import app
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/")
    
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "routing_service"
    assert "foot" in data["modes"]
    assert "bicycle" in data["modes"]

@pytest.mark.asyncio
async def test_health_check(mock_services):
    from routing_service import app
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "routing_service"
    assert "redis_connected" in data
    assert "database_connected" in data

@pytest.mark.asyncio
async def test_heuristics_endpoint(mock_services):
    from routing_service import app
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/heuristics")
    
    assert response.status_code == 200
    data = response.json()
    assert "haversine" in data["available"]
    assert "euclidean" in data["available"]

@pytest.mark.asyncio
async def test_transport_modes_endpoint(mock_services):
    from routing_service import app
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/transport-modes")
    
    assert response.status_code == 200
    data = response.json()
    assert "foot" in data["available"]
    assert "bicycle" in data["available"]


# FOOT MODE TESTS
@pytest.mark.asyncio
async def test_foot_route_success(mock_services):
    from routing_service import app
    mock_loader, _, _ = mock_services
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/route", json=ROUTE_REQUEST_FOOT)
    
    assert response.status_code == 200
    data = response.json()
    
    # GeoJSON structure
    assert data["route"]["type"] == "Feature"
    assert data["route"]["geometry"]["type"] == "LineString"
    assert len(data["route"]["geometry"]["coordinates"]) >= 1
    
    # Properties
    props = data["route"]["properties"]
    assert props["transport_mode"] == "foot"
    assert props["distance_km"] >= 0
    assert "avg_pm10" in props
    assert "avg_pm2_5" in props
    assert props["heuristic_used"] == "haversine"
    
    # Waypoints
    assert len(data["waypoints"]) >= 1

@pytest.mark.asyncio
async def test_foot_route_no_data(mock_services):
    from routing_service import app
    mock_loader, _, _ = mock_services
    mock_loader.fetch_area_pollution.return_value = []
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/route", json=ROUTE_REQUEST_FOOT)
    
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_foot_route_different_heuristic(mock_services):
    from routing_service import app
    
    request = ROUTE_REQUEST_FOOT.copy()
    request["heuristic"] = "euclidean"
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/route", json=request)
    
    assert response.status_code == 200
    assert response.json()["route"]["properties"]["heuristic_used"] == "euclidean"


# BICYCLE MODE TESTS
@pytest.mark.asyncio
async def test_bicycle_route_success(mock_services):
    from routing_service import app
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/route", json=ROUTE_REQUEST_BICYCLE)
    
    assert response.status_code == 200
    data = response.json()
    
    props = data["route"]["properties"]
    assert props["transport_mode"] == "bicycle"
    assert props["google_routes_considered"] == 2
    assert props["duration_minutes"] == 8.0

@pytest.mark.asyncio
async def test_bicycle_route_google_not_configured(mock_services):
    from routing_service import app
    _, _, mock_google = mock_services
    mock_google.is_configured.return_value = False
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/route", json=ROUTE_REQUEST_BICYCLE)
    
    assert response.status_code == 503


# POLLUTION DATA HANDLING TESTS
@pytest.mark.asyncio
async def test_missing_values_ignored(mock_services):
    """Test that -1 values are ignored in AQI calculation"""
    from routing_service import app
    mock_loader, _, _ = mock_services
    mock_loader.fetch_area_pollution.return_value = MOCK_POLLUTION_WITH_MISSING
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/route", json=ROUTE_REQUEST_FOOT)
    
    # Should still work even with missing values
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_wearaware_sensors(mock_services):
    """Test that WearAware sensors work (they measure PM10, PM2.5 but not NO2)"""
    from routing_service import app
    mock_loader, _, _ = mock_services
    mock_loader.fetch_area_pollution.return_value = MOCK_POLLUTION_WEARAWARE
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/route", json=ROUTE_REQUEST_FOOT)
    
    assert response.status_code == 200


# CACHE TESTS
@pytest.mark.asyncio
async def test_cache_stats(mock_services):
    from routing_service import app
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/cache/stats")
    
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] == True

@pytest.mark.asyncio
async def test_cache_clear(mock_services):
    from routing_service import app
    mock_redis.keys.return_value = ["route:abc", "route:def"]
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.delete("/cache/clear")
    
    assert response.status_code == 200
    assert response.json()["cleared"] == 2


# GRAPH AND PATHFINDING TESTS
def test_pollution_graph_add_data():
    """Test adding pollution data to graph"""
    from foot.graph_builder import PollutionGraph
    
    graph = PollutionGraph(alpha=0.5)
    graph.add_pollution_data(MOCK_POLLUTION_DATA)
    
    assert len(graph.nodes) > 0
    assert len(graph.pollution_data) > 0

def test_pollution_graph_ignores_negative():
    """Test that -1 values are handled correctly"""
    from foot.graph_builder import PollutionGraph
    
    graph = PollutionGraph(alpha=0.5)
    graph.add_pollution_data(MOCK_POLLUTION_WITH_MISSING)
    
    # Should still create nodes
    assert len(graph.nodes) > 0

def test_astar_pathfinding():
    """Test A* finds path"""
    from foot.graph_builder import PollutionGraph
    from foot.pathfinding import AStarPathfinder
    
    graph = PollutionGraph(alpha=0.5)
    graph.add_pollution_data(MOCK_POLLUTION_DATA)
    graph.build_edges()
    
    pathfinder = AStarPathfinder(graph, heuristic="haversine")
    path = pathfinder.find_path(
        (44.4268, 26.1025),
        (44.4280, 26.1045)
    )
    
    assert path is not None
    assert len(path) >= 1
    assert pathfinder.nodes_evaluated > 0

def test_heuristic_functions():
    """Test all heuristic functions"""
    from foot.utils import HEURISTICS, get_heuristic
    
    coord1 = (44.4268, 26.1025)
    coord2 = (44.4368, 26.1125)
    
    for name, func in HEURISTICS.items():
        dist = func(coord1, coord2)
        assert dist > 0
        assert dist < 50  # Should be less than 50km for these coords
    
    # Test get_heuristic
    h = get_heuristic("haversine")
    assert h == HEURISTICS["haversine"]
    
    with pytest.raises(ValueError):
        get_heuristic("invalid")

def test_calculate_route_stats():
    """Test route statistics calculation"""
    from foot.utils import calculate_route_stats
    
    path = [(44.4268, 26.1025), (44.4270, 26.1027), (44.4280, 26.1045)]
    pollution = {
        (44.4268, 26.1025): {"pm10": 40, "pm2_5": 20, "aqi": 35},
        (44.4270, 26.1027): {"pm10": 45, "pm2_5": 22, "aqi": 38},
        (44.4280, 26.1045): {"pm10": 35, "pm2_5": 18, "aqi": 30},
    }
    
    stats = calculate_route_stats(path, pollution)
    
    assert stats["total_distance_km"] > 0
    assert stats["avg_pm10"] == 40.0  # (40+45+35)/3
    assert stats["max_pm10"] == 45.0
    assert stats["avg_pm2_5"] == 20.0  # (20+22+18)/3
