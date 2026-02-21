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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize components on startup"""
    global cache_manager, data_loader
    
    logger.info("Starting Routing Service...")
    
    cache_manager = CacheManager()
    data_loader = PollutionDataLoader()
    
    logger.info("Routing Service ready")
    yield
    
    logger.info("Shutting down Routing Service")

app = FastAPI(
    title="Routing Service API",
    description="Calculate pollution-aware routes using A* pathfinding with Redis caching",
    version="1.0.0",
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
        "version": "1.0.0"
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
    
    return HealthResponse(
        status="healthy" if (redis_ok and db_ok) else "degraded",
        service="routing_service",
        redis_connected=redis_ok,
        database_connected=db_ok
    )


@app.get("/heuristics", tags=["routing"])
async def list_heuristics():
    """List available heuristic functions"""
    return {
        "available_heuristics": list(HEURISTICS.keys()),
        "default": "haversine",
        "descriptions": {
            "haversine": "Great-circle distance on a sphere (most accurate for geographic coordinates)",
            "euclidean": "Straight-line distance (fast, less accurate for large distances)",
            "manhattan": "Sum of absolute differences (grid-based, L1 norm)",
            "diagonal": "Maximum of lat/lon differences (Chebyshev distance)",
            "octile": "Combination of diagonal and straight movement (good for 8-directional grids)"
        }
    }


@app.post("/route", response_model=RouteResponse, tags=["routing"])
async def calculate_route(request: RouteRequest):
    """
    Calculate pollution-aware route from start to goal
    
    **Parameters:**
    - **start**: Starting coordinate (lat, lon)
    - **goal**: Destination coordinate (lat, lon)
    - **alpha**: Pollution weight (0.0 = fastest route, 1.0 = cleanest route)
    - **sensor_types**: Sensor types to use
    - **heuristic**: Heuristic function for A* ('haversine', 'euclidean', 'manhattan', 'diagonal', 'octile')
    
    **Optimization:**
    Instead of querying all Bucharest pollution data, the service queries only
    a circle centered between start and goal with radius = distance * 0.75.
    This significantly reduces data transfer and graph size.
    
    **Returns:**
    - GeoJSON route with all pollution statistics (PM10, PM2.5, NO2, AQI)
    - List of waypoints with pollution levels
    """
    start_time = time.time()
    
    try:
        logger.info(f"Route request: {request.start} -> {request.goal}, alpha={request.alpha}, sensors={request.sensor_types}, heuristic={request.heuristic}")
        
        # Redis cache check (include heuristic in cache key)
        cache_key = cache_manager.generate_cache_key(
            request.start,
            request.goal,
            request.alpha,
            request.sensor_types,
            request.heuristic
        )
        
        cached_route = cache_manager.get_cached_route(cache_key)
        if cached_route:
            calculation_time = round((time.time() - start_time) * 1000, 2)
            cached_route["route"]["properties"]["calculation_time_ms"] = calculation_time
            cached_route["route"]["properties"]["cached"] = True
            logger.info(f"Cache HIT: Returning cached route ({calculation_time}ms)")
            return RouteResponse(**cached_route)
        
        config = get_config()
        bounds = config["bucharest_bounds"]
        
        # Fetch pollution data for entire Bucharest area
        pollution_data = await data_loader.fetch_area_pollution(
            bounds["lat_min"],
            bounds["lat_max"],
            bounds["lon_min"],
            bounds["lon_max"],
            sensor_types=request.sensor_types
        )

        # TODO: Re-enable fetch_route_pollution optimization when more data is available
        # pollution_data = await data_loader.fetch_route_pollution(
        #     start=(request.start.lat, request.start.lon),
        #     goal=(request.goal.lat, request.goal.lon),
        #     sensor_types=request.sensor_types,
        #     buffer_factor=0.75  # 50% extra on each side for detours
        # )
        
        if not pollution_data:
            raise HTTPException(
                status_code=404,
                detail=f"No pollution data found for sensor types: {request.sensor_types}"
            )
        
        logger.info(f"Fetched {len(pollution_data)} pollution readings (optimized query)")
        
        # Build graph
        graph = PollutionGraph(alpha=request.alpha)
        graph.add_pollution_data(pollution_data)
        graph.build_edges()
        
        # Find path with specified heuristic
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
        
        # Calculate stats with all pollutants
        stats = calculate_route_stats(path, graph.pollution_data)
        calculation_time = round((time.time() - start_time) * 1000, 2)
        
        # Build GeoJSON response
        # GeoJSON coordinates are [lon, lat] (NOT [lat, lon]!)
        geojson_coords = [[node[1], node[0]] for node in path]
        
        # Waypoints with all pollution values
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
        
        # Build GeoJSON Feature with all pollution metrics
        geojson_feature = GeoJSONFeature(
            type="Feature",
            geometry=GeoJSONGeometry(
                type="LineString",
                coordinates=geojson_coords
            ),
            properties=GeoJSONProperties(
                distance_km=stats["total_distance_km"],
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
                nodes_evaluated=pathfinder.nodes_evaluated,
                cached=False
            )
        )
        
        response_data = {
            "route": geojson_feature.model_dump(),
            "waypoints": [w.model_dump() for w in waypoints]
        }
        
        # Cache result
        cache_manager.cache_route(cache_key, response_data)
        
        logger.info(f"Route calculated: {len(path)} waypoints, {stats['total_distance_km']}km, AQI={stats['avg_aqi']}, heuristic={request.heuristic}, {calculation_time}ms")
        
        return RouteResponse(**response_data)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating route: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


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
