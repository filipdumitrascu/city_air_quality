import sys
import os
from unittest.mock import patch, AsyncMock, MagicMock
import pytest

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

mock_redis_client = MagicMock()
mock_redis_client.ping = MagicMock(return_value=True)
mock_redis_client.get = MagicMock(return_value=None)
mock_redis_client.setex = MagicMock()
mock_redis_client.keys = MagicMock(return_value=[])
mock_redis_client.info = MagicMock(return_value={"total_commands_processed": 0, "used_memory": 0})
mock_redis_client.delete = MagicMock()

sys.modules['redis'] = MagicMock()

# Mock cache_manager and data_loader BEFORE importing app
mock_cache_manager = MagicMock()
mock_cache_manager.generate_cache_key = MagicMock(return_value="route:test123")
mock_cache_manager.get_cached_route = MagicMock(return_value=None)
mock_cache_manager.cache_route = MagicMock()
mock_cache_manager.is_connected = MagicMock(return_value=True)
mock_cache_manager.redis_client = mock_redis_client

mock_data_loader = MagicMock()

with patch('redis.Redis', return_value=mock_redis_client):
    from routing_service.src.routing_service import app
    from routing_service.src.graph_builder import PollutionGraph
    from routing_service.src.pathfinding import AStarPathfinder
    
    # Inject mocks into module
    import routing_service.src.routing_service as routing_module
    routing_module.cache_manager = mock_cache_manager
    routing_module.data_loader = mock_data_loader

from httpx import AsyncClient


# Test data
MOCK_POLLUTION_DATA_FIXED = [
    ["F001", "2025-01-11T08:00:00", 44.4268, 26.1025, 45.3, 25.2, 30.5],
    ["F002", "2025-01-11T08:00:00", 44.4270, 26.1027, 42.1, 22.8, 28.3],
    ["F003", "2025-01-11T08:00:00", 44.4272, 26.1030, 38.7, 20.5, 26.1],
    ["F004", "2025-01-11T08:00:00", 44.4275, 26.1035, 40.2, 21.1, 27.3],
    ["F005", "2025-01-11T08:00:00", 44.4278, 26.1040, 37.5, 19.8, 25.8],
    ["F006", "2025-01-11T08:00:00", 44.4280, 26.1045, 35.2, 18.3, 24.5],
]

MOCK_POLLUTION_DATA_MOBILE = [
    ["M001", "2025-01-11T08:00:00", 44.4270, 26.1028, 50.2, 28.1, 35.2],
    ["M002", "2025-01-11T08:00:00", 44.4276, 26.1038, 48.5, 26.5, 33.1],
]

MOCK_POLLUTION_DATA_ALL = MOCK_POLLUTION_DATA_FIXED + MOCK_POLLUTION_DATA_MOBILE

ROUTE_REQUEST = {
    "start": {"lat": 44.4268, "lon": 26.1025},
    "goal": {"lat": 44.4280, "lon": 26.1045},
    "alpha": 0.5,
    "sensor_types": ["fixed", "mobile"]
}


# Test health endpoints
@pytest.mark.asyncio
async def test_root_endpoint():
    """Test root endpoint returns service info"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/")
    
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "routing_service"
    assert data["status"] == "running"

@pytest.mark.asyncio
async def test_health_check():
    """Test health check endpoint"""
    mock_data_loader.fetch_pollution_data = AsyncMock(return_value=MOCK_POLLUTION_DATA_FIXED)
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "routing_service"
    assert "redis_connected" in data


# Route calculation
@pytest.mark.asyncio
async def test_calculate_route_success():
    """Test successful route calculation"""
    mock_data_loader.fetch_area_pollution = AsyncMock(return_value=MOCK_POLLUTION_DATA_ALL)
    mock_cache_manager.get_cached_route.return_value = None
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/route", json=ROUTE_REQUEST)
    
    assert response.status_code == 200
    data = response.json()
    
    # Check GeoJSON structure
    assert "route" in data
    assert data["route"]["type"] == "Feature"
    assert data["route"]["geometry"]["type"] == "LineString"
    assert len(data["route"]["geometry"]["coordinates"]) >= 1
    
    # Check properties
    props = data["route"]["properties"]
    assert props["distance_km"] >= 0
    assert props["sensor_types_used"] == ["fixed", "mobile"]
    
    # Check waypoints
    assert "waypoints" in data
    assert len(data["waypoints"]) >= 1

@pytest.mark.asyncio
async def test_calculate_route_fixed_only():
    """Test route with fixed sensors only"""
    request_fixed = ROUTE_REQUEST.copy()
    request_fixed["sensor_types"] = ["fixed"]
    
    mock_data_loader.fetch_area_pollution = AsyncMock(return_value=MOCK_POLLUTION_DATA_FIXED)
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/route", json=request_fixed)
    
    assert response.status_code == 200
    data = response.json()
    assert data["route"]["properties"]["sensor_types_used"] == ["fixed"]

@pytest.mark.asyncio
async def test_calculate_route_no_data():
    """Test when no pollution data available"""
    mock_data_loader.fetch_area_pollution = AsyncMock(return_value=[])
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/route", json=ROUTE_REQUEST)
    
    assert response.status_code == 404

# Cache endpoints
@pytest.mark.asyncio
async def test_cache_stats():
    """Test cache stats endpoint"""
    mock_redis_client.info.return_value = {
        "total_commands_processed": 100,
        "keyspace_hits": 60,
        "used_memory": 1024 * 1024
    }
    mock_redis_client.keys.return_value = ["route:abc", "route:def"]
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/cache/stats")
    
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] == True

@pytest.mark.asyncio
async def test_cache_clear():
    """Test cache clear endpoint"""
    mock_redis_client.keys.return_value = ["route:abc123", "route:def456"]
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.delete("/cache/clear")
    
    assert response.status_code == 200
    data = response.json()
    assert data["cleared"] == 2


# Graph and path finding
def test_graph_add_pollution_data():
    """Test adding pollution data to graph"""
    graph = PollutionGraph(alpha=0.5)
    graph.add_pollution_data(MOCK_POLLUTION_DATA_FIXED)
    
    assert len(graph.nodes) > 0
    assert len(graph.pollution_data) > 0

def test_graph_build_edges():
    """Test building graph edges"""
    graph = PollutionGraph(alpha=0.5)
    graph.add_pollution_data(MOCK_POLLUTION_DATA_FIXED)
    graph.build_edges()
    
    assert len(graph.edges) > 0

def test_graph_get_nearest_node():
    """Test finding nearest node"""
    graph = PollutionGraph(alpha=0.5)
    graph.add_pollution_data(MOCK_POLLUTION_DATA_FIXED)
    
    nearest = graph.get_nearest_node(44.4268, 26.1025)
    assert nearest is not None
    assert isinstance(nearest, tuple)

def test_pathfinding_finds_path():
    """Test A* pathfinding"""
    graph = PollutionGraph(alpha=0.5)
    graph.add_pollution_data(MOCK_POLLUTION_DATA_FIXED)
    graph.build_edges()
    
    pathfinder = AStarPathfinder(graph)
    path = pathfinder.find_path(
        (44.4268, 26.1025),
        (44.4280, 26.1045)
    )
    
    # Path might be just 2 nodes (start + goal) if they're close
    assert path is not None
    assert len(path) >= 1
    assert pathfinder.nodes_evaluated > 0
