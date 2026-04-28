"""
Routing Service - Pollution-Aware Navigation for CityAirQ

Two transport modes:
- foot: A* pathfinding on pollution grid
- bicycle: Google Routes API with pollution scoring

Pollutants used for routing:
- PM10: measured by all sensors (fixed, CityAirQ, WearAware)
- PM2.5: measured by all sensors

NO2 excluded because WearAware doesn't measure it (returns -1).
Values of -1 are treated as missing and excluded from AQI calculation.
"""

from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from prometheus_fastapi_instrumentator import Instrumentator
import logging
import time

from models import (
    RouteRequest, RouteResponse, RouteNode, HealthResponse,
    GeoJSONFeature, GeoJSONGeometry, GeoJSONProperties
)
from config import get_config, ROUTING_POLLUTANTS
from cache_manager import CacheManager

# Foot mode
from foot.data_loader import PollutionDataLoader
from foot.graph_builder import PollutionGraph
from foot.pathfinding import AStarPathfinder
from foot.utils import calculate_route_stats, HEURISTICS

# Bicycle mode
from bicycle.google_routes import GoogleRoutesClient


# CONFIGURATION
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

cache_manager = None
data_loader = None
google_routes_client = None


# FASTAPI APPLICATION
@asynccontextmanager
async def lifespan(app: FastAPI):
    global cache_manager, data_loader, google_routes_client
    
    logger.info("Starting Routing Service...")
    
    cache_manager = CacheManager()
    data_loader = PollutionDataLoader()
    google_routes_client = GoogleRoutesClient()
    
    if google_routes_client.is_configured():
        logger.info("Google Routes API configured (bicycle mode available)")
    else:
        logger.warning("Google Routes API NOT configured")
    
    logger.info(f"Using pollutants: {ROUTING_POLLUTANTS}")
    logger.info("Routing Service ready")
    
    yield
    
    logger.info("Shutting down")

app = FastAPI(
    title="CityAirQ Routing Service",
    description="Pollution-aware routing: foot (A*) or bicycle (Google Routes)",
    version="2.0.0",
    lifespan=lifespan
)

Instrumentator().instrument(app).expose(app)

# HEALTH ENDPOINTS
@app.get("/")
async def root():
    return {
        "service": "routing_service",
        "version": "2.0.0",
        "modes": ["foot", "bicycle"],
        "pollutants": ROUTING_POLLUTANTS
    }

@app.get("/health", response_model=HealthResponse)
async def health_check():
    redis_ok = cache_manager.is_connected() if cache_manager else False
    
    db_ok = False
    try:
        await data_loader.fetch_pollution_data(44.43, 26.10, 1.0, ["CityAirQ", "WearAware"])
        db_ok = True
    except:
        pass
    
    google_ok = google_routes_client.is_configured() if google_routes_client else False
    
    return HealthResponse(
        status="healthy" if (redis_ok and db_ok) else "degraded",
        service="routing_service",
        redis_connected=redis_ok,
        database_connected=db_ok,
        google_routes_configured=google_ok
    )

@app.get("/heuristics")
async def list_heuristics():
    return {
        "available": list(HEURISTICS.keys()),
        "default": "haversine",
        "note": "Only used in 'foot' mode"
    }

@app.get("/transport-modes")
async def list_transport_modes():
    return {
        "available": ["foot", "bicycle"],
        "foot": "A* pathfinding on pollution grid",
        "bicycle": "Google Routes API with pollution scoring",
        "google_configured": google_routes_client.is_configured() if google_routes_client else False
    }



# ROUTE CALCULATION
@app.post("/route", response_model=RouteResponse)
async def calculate_route(request: RouteRequest):
    """
    Calculate pollution-aware route.
    
    - alpha: 0.0 = fastest, 1.0 = cleanest
    - transport_mode: 'foot' or 'bicycle'
    """
    start_time = time.time()
    
    try:
        logger.info(f"Route: {request.start} -> {request.goal}, mode={request.transport_mode}")
        
        if request.transport_mode == "bicycle":
            return await _calculate_bicycle_route(request, start_time)
        else:
            return await _calculate_foot_route(request, start_time)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Route error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def _calculate_foot_route(request: RouteRequest, start_time: float) -> RouteResponse:
    """A* pathfinding on pollution grid with forecast gap-filling"""
    
    # Check cache
    cache_key = cache_manager.generate_cache_key(
        request.start, request.goal, request.alpha,
        request.sensor_types, f"foot_{request.heuristic}"
    )
    
    cached = cache_manager.get_cached_route(cache_key)
    if cached:
        cached["route"]["properties"]["cached"] = True
        cached["route"]["properties"]["calculation_time_ms"] = round((time.time() - start_time) * 1000, 2)
        return RouteResponse(**cached)
    
    # Fetch pollution data
    config = get_config()
    bounds = config["bucharest_bounds"]
    grid_resolution = config["grid_resolution"]
    
    pollution_data = await data_loader.fetch_area_pollution(
        bounds["lat_min"], bounds["lat_max"],
        bounds["lon_min"], bounds["lon_max"],
        sensor_types=request.sensor_types
    )
    
    if not pollution_data:
        raise HTTPException(status_code=404, detail="No pollution data found")
    
    logger.info(f"Fetched {len(pollution_data)} readings from sensors")
    
    # Get existing coordinates for gap detection
    existing_coords = set()
    for reading in pollution_data:
        lat = reading.get("latitude", 0)
        lon = reading.get("longitude", 0)
        grid_lat = round(lat / grid_resolution) * grid_resolution
        grid_lon = round(lon / grid_resolution) * grid_resolution
        existing_coords.add((round(grid_lat, 6), round(grid_lon, 6)))

    # Build graph and find path
    graph = PollutionGraph(alpha=request.alpha)
    graph.add_pollution_data(pollution_data)
    graph.build_edges()
    
    pathfinder = AStarPathfinder(graph, heuristic=request.heuristic)
    path = pathfinder.find_path(
        (request.start.lat, request.start.lon),
        (request.goal.lat, request.goal.lon)
    )
    
    if not path:
        raise HTTPException(status_code=404, detail="No path found")
    
    stats = calculate_route_stats(path, graph.pollution_data)
    calc_time = round((time.time() - start_time) * 1000, 2)
    
    # Build response
    geojson_coords = [[node[1], node[0]] for node in path]
    
    waypoints = []
    for node in path:
        p = graph.get_pollution(node)
        waypoints.append(RouteNode(
            lat=node[0],
            lon=node[1],
            pm10=p.get('pm10') if p.get('pm10', -1) >= 0 else None,
            pm2_5=p.get('pm2_5') if p.get('pm2_5', -1) >= 0 else None,
            aqi=p.get('aqi')
        ))
    
    # Build properties with all pollutant stats
    props = {
        "distance_km": stats["total_distance_km"],
        "avg_aqi": stats["avg_aqi"],
        "max_aqi": stats["max_aqi"],
        "calculation_time_ms": calc_time,
        "sensor_types_used": request.sensor_types,
        "heuristic_used": request.heuristic,
        "transport_mode": "foot",
        "nodes_evaluated": pathfinder.nodes_evaluated,
        "cached": False
    }
    
    # Add individual pollutant stats (only if data available)
    pollutant_keys = ['pm10', 'pm2_5', 'pm1_0', 'no2', 'co', 'co2', 'nh3', 'vocs']
    for key in pollutant_keys:
        avg_val = stats.get(f"avg_{key}", -1)
        max_val = stats.get(f"max_{key}", -1)
        if avg_val >= 0:
            props[f"avg_{key}"] = avg_val
            props[f"max_{key}"] = max_val
    
    response_data = {
        "route": GeoJSONFeature(
            geometry=GeoJSONGeometry(coordinates=geojson_coords),
            properties=GeoJSONProperties(**props)
        ).model_dump(),
        "waypoints": [w.model_dump() for w in waypoints]
    }
    
    cache_manager.cache_route(cache_key, response_data)
    
    logger.info(f"Foot route: {len(path)} points, {stats['total_distance_km']}km, {calc_time}ms")
    
    return RouteResponse(**response_data)

async def _calculate_bicycle_route(request: RouteRequest, start_time: float) -> RouteResponse:
    """Google Routes API with pollution scoring"""
    
    if not google_routes_client or not google_routes_client.is_configured():
        raise HTTPException(status_code=503, detail="Google Routes not configured")
    
    # Check cache
    cache_key = cache_manager.generate_cache_key(
        request.start, request.goal, request.alpha,
        request.sensor_types, "bicycle"
    )
    
    cached = cache_manager.get_cached_route(cache_key)
    if cached:
        cached["route"]["properties"]["cached"] = True
        cached["route"]["properties"]["calculation_time_ms"] = round((time.time() - start_time) * 1000, 2)
        return RouteResponse(**cached)
    
    # Fetch pollution data for route corridor
    pollution_data = await data_loader.fetch_route_pollution(
        (request.start.lat, request.start.lon),
        (request.goal.lat, request.goal.lon),
        sensor_types=request.sensor_types
    )
    
    if not pollution_data:
        raise HTTPException(status_code=404, detail="No pollution data found")
    
    # Get routes and score by pollution
    config = get_config()
    best_route, all_routes = await google_routes_client.get_routes_with_pollution(
        start=(request.start.lat, request.start.lon),
        goal=(request.goal.lat, request.goal.lon),
        pollution_data=pollution_data,
        alpha=request.alpha,
        sample_distance_m=config["waypoint_sample_distance_m"]
    )
    
    calc_time = round((time.time() - start_time) * 1000, 2)
    
    # Build response
    geojson_coords = [[lon, lat] for lat, lon in best_route["path"]]
    pollution_stats = best_route["pollution"]
    
    waypoints = []
    for lat, lon in best_route["sampled_waypoints"]:
        p = google_routes_client.get_pollution_at_point(lat, lon, pollution_data)
        waypoints.append(RouteNode(
            lat=lat,
            lon=lon,
            pm10=p.get('pm10') if p.get('pm10', -1) >= 0 else None,
            pm2_5=p.get('pm2_5') if p.get('pm2_5', -1) >= 0 else None,
            aqi=p.get('aqi')
        ))
    
    # Build properties with all pollutant stats
    props = {
        "distance_km": round(best_route["distance_km"], 2),
        "duration_minutes": round(best_route["duration_minutes"], 1),
        "avg_aqi": pollution_stats["avg_aqi"],
        "max_aqi": pollution_stats["max_aqi"],
        "calculation_time_ms": calc_time,
        "sensor_types_used": request.sensor_types,
        "transport_mode": "bicycle",
        "google_routes_considered": len(all_routes),
        "cached": False
    }
    
    # Add individual pollutant stats (only if data available)
    pollutant_keys = ['pm10', 'pm2_5', 'pm1_0', 'no2', 'co', 'co2', 'nh3', 'vocs']
    for key in pollutant_keys:
        avg_val = pollution_stats.get(f"avg_{key}", -1)
        max_val = pollution_stats.get(f"max_{key}", -1)
        if avg_val >= 0:
            props[f"avg_{key}"] = avg_val
            props[f"max_{key}"] = max_val
    
    response_data = {
        "route": GeoJSONFeature(
            geometry=GeoJSONGeometry(coordinates=geojson_coords),
            properties=GeoJSONProperties(**props)
        ).model_dump(),
        "waypoints": [w.model_dump() for w in waypoints]
    }
    
    cache_manager.cache_route(cache_key, response_data)
    
    logger.info(f"Bicycle route: {best_route['distance_km']:.2f}km, {calc_time}ms")
    
    return RouteResponse(**response_data)



# CACHE MANAGEMENT
@app.get("/cache/stats")
async def cache_stats():
    if not cache_manager or not cache_manager.is_connected():
        return {"connected": False}
    
    try:
        info = cache_manager.redis_client.info("stats")
        route_keys = len(cache_manager.redis_client.keys("route:*"))
        
        return {
            "connected": True,
            "cached_routes": route_keys,
            "hits": info.get("keyspace_hits", 0),
            "misses": info.get("keyspace_misses", 0)
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}

@app.delete("/cache/clear")
async def clear_cache():
    if not cache_manager or not cache_manager.is_connected():
        raise HTTPException(status_code=503, detail="Redis not connected")
    
    try:
        keys = cache_manager.redis_client.keys("route:*")
        if keys:
            cache_manager.redis_client.delete(*keys)
            return {"cleared": len(keys)}
        return {"cleared": 0}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
