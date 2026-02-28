from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
import logging
import time
import os

from .models import (
    RouteRequest, RouteResponse, RouteNode, HealthResponse,
    GeoJSONFeature, GeoJSONGeometry, GeoJSONProperties
)
from .config import get_config
from .data_loader import PollutionDataLoader
from .graph_builder import PollutionGraph
from .pathfinding import AStarPathfinder
from .google_routes import GoogleRoutesClient
from .cache_manager import CacheManager
from .utils import calculate_route_stats, HEURISTICS
from prometheus_fastapi_instrumentator import Instrumentator


log_dir = os.path.join(os.path.dirname(__file__), "../logs")
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'routing_service.log'), mode='w')
    ]
)

logger = logging.getLogger(__name__)

cache_manager = None
data_loader = None
google_routes_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize components on startup"""
    global cache_manager, data_loader, google_routes_client
    
    logger.info("Starting Routing Service...")
    
    cache_manager = CacheManager()
    data_loader = PollutionDataLoader()
    google_routes_client = GoogleRoutesClient()
    
    if google_routes_client.is_configured():
        logger.info("Google Routes API configured")
    else:
        logger.warning("Google Routes API NOT configured - car mode will not work")
    
    logger.info("Routing Service ready")
    yield
    
    logger.info("Shutting down Routing Service")


app = FastAPI(
    title="Routing Service API",
    description="Calculate pollution-aware routes using A* (foot) or Google Routes (car)",
    version="2.0.0",
    lifespan=lifespan
)

# Prometheus metrics for monitoring
Instrumentator().instrument(app).expose(app)


@app.get("/", tags=["health"])
async def root():
    """Root endpoint"""
    return {
        "service": "routing_service",
        "status": "running",
        "version": "2.0.0",
        "modes": ["foot", "car"]
    }


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    """Health check endpoint"""
    redis_ok = cache_manager.is_connected() if cache_manager else False
    
    db_ok = False
    try:
        await data_loader.fetch_pollution_data(44.43, 26.10, 1.0, ["fixed"])
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


@app.get("/heuristics", tags=["routing"])
async def list_heuristics():
    """List available heuristic functions (for foot mode)"""
    return {
        "available_heuristics": list(HEURISTICS.keys()),
        "default": "haversine",
        "note": "Heuristics are only used in 'foot' mode. 'car' mode uses Google Routes.",
        "descriptions": {
            "haversine": "Great-circle distance (most accurate for geographic coordinates)",
            "euclidean": "Straight-line distance (fast, less accurate)",
            "manhattan": "Sum of absolute differences (grid-based)",
            "diagonal": "Maximum of lat/lon differences (Chebyshev)",
            "octile": "Combination of diagonal and straight movement"
        }
    }


@app.get("/transport-modes", tags=["routing"])
async def list_transport_modes():
    """List available transport modes"""
    return {
        "available_modes": ["foot", "car"],
        "descriptions": {
            "foot": "Walking route using A* pathfinding on pollution grid. "
                   "Route follows grid points, not actual roads.",
            "car": "Driving route using Google Routes API. "
                  "Returns real road routes with pollution scoring."
        },
        "google_routes_configured": google_routes_client.is_configured() if google_routes_client else False
    }


@app.post("/route", response_model=RouteResponse, tags=["routing"])
async def calculate_route(request: RouteRequest):
    """
    Calculate pollution-aware route from start to goal.
    
    **Transport Modes:**
    - **foot**: Uses A* pathfinding on pollution grid (your implementation)
    - **car**: Uses Google Routes API with pollution scoring
    
    **Parameters:**
    - **start**: Starting coordinate (lat, lon)
    - **goal**: Destination coordinate (lat, lon)
    - **alpha**: Pollution weight (0.0 = fastest, 1.0 = cleanest)
    - **sensor_types**: Sensor types to use
    - **heuristic**: Heuristic for A* (only for foot mode)
    - **transport_mode**: 'foot' or 'car'
    """
    start_time = time.time()
    
    try:
        logger.info(
            f"Route request: {request.start} -> {request.goal}, "
            f"mode={request.transport_mode}, alpha={request.alpha}"
        )
        
        if request.transport_mode == "car":
            return await _calculate_car_route(request, start_time)
        else:
            return await _calculate_foot_route(request, start_time)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating route: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


async def _calculate_foot_route(request: RouteRequest, start_time: float) -> RouteResponse:
    """Calculate route using A* pathfinding (original implementation)"""
    
    cache_key = cache_manager.generate_cache_key(
        request.start,
        request.goal,
        request.alpha,
        request.sensor_types,
        f"foot_{request.heuristic}"
    )
    
    cached_route = cache_manager.get_cached_route(cache_key)
    if cached_route:
        calculation_time = round((time.time() - start_time) * 1000, 2)
        cached_route["route"]["properties"]["calculation_time_ms"] = calculation_time
        cached_route["route"]["properties"]["cached"] = True
        logger.info(f"Cache HIT (foot): Returning cached route ({calculation_time}ms)")
        return RouteResponse(**cached_route)
    
    config = get_config()
    bounds = config["bucharest_bounds"]
    
    pollution_data = await data_loader.fetch_area_pollution(
        bounds["lat_min"],
        bounds["lat_max"],
        bounds["lon_min"],
        bounds["lon_max"],
        sensor_types=request.sensor_types
    )
    
    if not pollution_data:
        raise HTTPException(
            status_code=404,
            detail=f"No pollution data found for sensor types: {request.sensor_types}"
        )
    
    logger.info(f"Fetched {len(pollution_data)} pollution readings")
    
    graph = PollutionGraph(alpha=request.alpha)
    graph.add_pollution_data(pollution_data)
    graph.build_edges()
    
    pathfinder = AStarPathfinder(graph, heuristic=request.heuristic)
    path = pathfinder.find_path(
        (request.start.lat, request.start.lon),
        (request.goal.lat, request.goal.lon)
    )
    
    if not path:
        raise HTTPException(
            status_code=404,
            detail="No path found between start and goal"
        )
    
    stats = calculate_route_stats(path, graph.pollution_data)
    calculation_time = round((time.time() - start_time) * 1000, 2)
    
    geojson_coords = [[node[1], node[0]] for node in path]
    
    waypoints = []
    for node in path:
        pollution = graph.get_pollution(node)
        waypoints.append(RouteNode(
            lat=node[0],
            lon=node[1],
            pm10=pollution.get('pm10', 0),
            pm25=pollution.get('pm25', 0),
            no2=pollution.get('no2', 0),
            aqi=pollution.get('aqi', 0)
        ))
    
    geojson_feature = GeoJSONFeature(
        type="Feature",
        geometry=GeoJSONGeometry(
            type="LineString",
            coordinates=geojson_coords
        ),
        properties=GeoJSONProperties(
            distance_km=stats["total_distance_km"],
            duration_minutes=None,
            avg_pollution_pm10=stats["avg_pm10"],
            max_pollution_pm10=stats["max_pm10"],
            avg_pollution_pm25=stats["avg_pm25"],
            max_pollution_pm25=stats["max_pm25"],
            avg_pollution_no2=stats["avg_no2"],
            max_pollution_no2=stats["max_no2"],
            avg_aqi=stats["avg_aqi"],
            max_aqi=stats["max_aqi"],
            calculation_time_ms=calculation_time,
            sensor_types_used=request.sensor_types,
            heuristic_used=request.heuristic,
            transport_mode="foot",
            nodes_evaluated=pathfinder.nodes_evaluated,
            google_routes_considered=None,
            cached=False
        )
    )
    
    response_data = {
        "route": geojson_feature.model_dump(),
        "waypoints": [w.model_dump() for w in waypoints]
    }
    
    cache_manager.cache_route(cache_key, response_data)
    
    logger.info(
        f"Foot route calculated: {len(path)} waypoints, "
        f"{stats['total_distance_km']}km, AQI={stats['avg_aqi']}, {calculation_time}ms"
    )
    
    return RouteResponse(**response_data)


async def _calculate_car_route(request: RouteRequest, start_time: float) -> RouteResponse:
    """Calculate route using Google Routes API with pollution scoring"""
    
    if not google_routes_client or not google_routes_client.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Google Routes API not configured. Car mode unavailable."
        )
    
    cache_key = cache_manager.generate_cache_key(
        request.start,
        request.goal,
        request.alpha,
        request.sensor_types,
        "car_google"
    )
    
    cached_route = cache_manager.get_cached_route(cache_key)
    if cached_route:
        calculation_time = round((time.time() - start_time) * 1000, 2)
        cached_route["route"]["properties"]["calculation_time_ms"] = calculation_time
        cached_route["route"]["properties"]["cached"] = True
        logger.info(f"Cache HIT (car): Returning cached route ({calculation_time}ms)")
        return RouteResponse(**cached_route)
    
    config = get_config()
    bounds = config["bucharest_bounds"]
    
    pollution_data = await data_loader.fetch_area_pollution(
        bounds["lat_min"],
        bounds["lat_max"],
        bounds["lon_min"],
        bounds["lon_max"],
        sensor_types=request.sensor_types
    )
    
    if not pollution_data:
        raise HTTPException(
            status_code=404,
            detail=f"No pollution data found for sensor types: {request.sensor_types}"
        )
    
    best_route, all_routes = await google_routes_client.get_routes_with_pollution(
        start=(request.start.lat, request.start.lon),
        goal=(request.goal.lat, request.goal.lon),
        pollution_data=pollution_data,
        alpha=request.alpha,
        sample_distance_m=config["waypoint_sample_distance_m"]
    )
    
    calculation_time = round((time.time() - start_time) * 1000, 2)
    
    geojson_coords = [[lon, lat] for lat, lon in best_route["path"]]
    
    waypoints = []
    pollution_grid = google_routes_client._build_pollution_grid(pollution_data)
    
    for lat, lon in best_route["sampled_waypoints"]:
        grid_lat = round(lat / 0.002) * 0.002
        grid_lon = round(lon / 0.002) * 0.002
        pollution = pollution_grid.get(
            (grid_lat, grid_lon), 
            {'pm10': 0, 'pm25': 0, 'no2': 0, 'aqi': 50}
        )
        waypoints.append(RouteNode(
            lat=lat,
            lon=lon,
            pm10=pollution.get('pm10', 0),
            pm25=pollution.get('pm25', 0),
            no2=pollution.get('no2', 0),
            aqi=pollution.get('aqi', 50)
        ))
    
    pollution_stats = best_route["pollution"]
    
    geojson_feature = GeoJSONFeature(
        type="Feature",
        geometry=GeoJSONGeometry(
            type="LineString",
            coordinates=geojson_coords
        ),
        properties=GeoJSONProperties(
            distance_km=round(best_route["distance_km"], 2),
            duration_minutes=round(best_route["duration_minutes"], 1),
            avg_pollution_pm10=pollution_stats["avg_pm10"],
            max_pollution_pm10=pollution_stats["max_pm10"],
            avg_pollution_pm25=pollution_stats["avg_pm25"],
            max_pollution_pm25=pollution_stats["max_pm25"],
            avg_pollution_no2=pollution_stats["avg_no2"],
            max_pollution_no2=pollution_stats["max_no2"],
            avg_aqi=pollution_stats["avg_aqi"],
            max_aqi=pollution_stats["max_aqi"],
            calculation_time_ms=calculation_time,
            sensor_types_used=request.sensor_types,
            heuristic_used=None,
            transport_mode="car",
            nodes_evaluated=None,
            google_routes_considered=len(all_routes),
            cached=False
        )
    )
    
    response_data = {
        "route": geojson_feature.model_dump(),
        "waypoints": [w.model_dump() for w in waypoints]
    }
    
    cache_manager.cache_route(cache_key, response_data)
    
    logger.info(
        f"Car route calculated: {best_route['distance_km']:.2f}km, "
        f"{best_route['duration_minutes']:.1f}min, AQI={pollution_stats['avg_aqi']}, "
        f"selected from {len(all_routes)} routes, {calculation_time}ms"
    )
    
    return RouteResponse(**response_data)


@app.get("/cache/stats", tags=["cache"])
async def cache_stats():
    """Get Redis cache statistics"""
    if not cache_manager or not cache_manager.is_connected():
        return {"connected": False, "error": "Redis not connected"}
    
    try:
        info = cache_manager.redis_client.info("stats")
        memory = cache_manager.redis_client.info("memory")
        route_keys = len(cache_manager.redis_client.keys("route:*"))
        
        return {
            "connected": True,
            "total_commands": info.get("total_commands_processed", 0),
            "hits": info.get("keyspace_hits", 0),
            "misses": info.get("keyspace_misses", 0),
            "hit_rate_percent": round(
                (info.get("keyspace_hits", 0) / max(info.get("total_commands_processed", 1), 1)) * 100,
                2
            ),
            "cached_routes": route_keys,
            "memory_used_mb": round(memory.get("used_memory", 0) / 1024 / 1024, 2)
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}


@app.delete("/cache/clear", tags=["cache"])
async def clear_cache():
    """Clear all cached routes"""
    if not cache_manager or not cache_manager.is_connected():
        raise HTTPException(status_code=503, detail="Redis not connected")
    
    try:
        keys = cache_manager.redis_client.keys("route:*")
        if keys:
            cache_manager.redis_client.delete(*keys)
            logger.info(f"Cleared {len(keys)} cached routes")
            return {"cleared": len(keys), "message": f"Cleared {len(keys)} cached routes"}
        return {"cleared": 0, "message": "No cached routes to clear"}
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=f"Error clearing cache: {str(e)}")
