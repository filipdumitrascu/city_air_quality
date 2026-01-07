# routing_service/src/routing_service.py
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
import logging
import time
import os

from .models import RouteRequest, RouteResponse, RouteNode, HealthResponse
from .config import get_config
from .data_loader import PollutionDataLoader
from .graph_builder import PollutionGraph
from .pathfinding import AStarPathfinder
from .cache_manager import CacheManager
from .utils import calculate_route_stats

# Setup logging
log_dir = os.path.join(os.path.dirname(__file__), "../logs")
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'routing_service.log')),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Global instances
cache_manager = None
data_loader = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize on startup"""
    global cache_manager, data_loader
    
    logger.info("Starting Routing Service...")
    
    # Initialize components
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
    
    # Test database connection
    db_ok = False
    try:
        # Quick ping to database service
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

@app.post("/route", response_model=RouteResponse, tags=["routing"])
async def calculate_route(request: RouteRequest):
    """
    Calculate pollution-aware route from start to goal
    
    Parameters:
    - **start**: Starting coordinate
    - **goal**: Destination coordinate  
    - **alpha**: Pollution weight (0.0 = fastest, 1.0 = cleanest)
    - **sensor_types**: Which sensors to use (["fixed"], ["mobile"], or ["fixed", "mobile"])
    
    Returns optimal route with statistics
    """
    start_time = time.time()
    
    try:
        logger.info(f"Route request: {request.start} → {request.goal}, alpha={request.alpha}, sensors={request.sensor_types}")
        
        # Check cache first
        cache_key = cache_manager.generate_cache_key(
            request.start,
            request.goal,
            request.alpha,
            request.sensor_types
        )
        
        cached_route = cache_manager.get_cached_route(cache_key)
        if cached_route:
            cached_route["cached"] = True
            cached_route["calculation_time_ms"] = round((time.time() - start_time) * 1000, 2)
            logger.info(f"Returning cached route (took {cached_route['calculation_time_ms']}ms)")
            return RouteResponse(**cached_route)
        
        # Fetch pollution data
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
        
        # Build graph
        graph = PollutionGraph(alpha=request.alpha)
        graph.add_pollution_data(pollution_data)
        graph.build_edges()
        
        # Find path
        pathfinder = AStarPathfinder(graph)
        path = pathfinder.find_path(
            (request.start.lat, request.start.lon),
            (request.goal.lat, request.goal.lon)
        )
        
        if not path:
            raise HTTPException(
                status_code=404,
                detail="No path found between start and goal"
            )
        
        # Calculate stats
        stats = calculate_route_stats(path, graph.pollution_data)
        
        # Build response
        route_nodes = [
            RouteNode(
                lat=node[0],
                lon=node[1],
                pollution_level=graph.get_pollution(node)
            )
            for node in path
        ]
        
        calculation_time = round((time.time() - start_time) * 1000, 2)
        
        response_data = {
            "route": route_nodes,
            "total_distance_km": stats["total_distance_km"],
            "avg_pollution": stats["avg_pollution"],
            "max_pollution": stats["max_pollution"],
            "calculation_time_ms": calculation_time,
            "cached": False,
            "sensor_types_used": request.sensor_types,
            "nodes_evaluated": pathfinder.nodes_evaluated
        }
        
        # Cache result
        cache_manager.cache_route(cache_key, response_data)
        
        logger.info(f"Route calculated: {len(path)} waypoints, {stats['total_distance_km']}km, {calculation_time}ms")
        
        return RouteResponse(**response_data)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating route: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

@app.get("/cache/stats", tags=["cache"])
async def cache_stats():
    """Get cache statistics"""
    if not cache_manager.is_connected():
        return {"error": "Redis not connected"}
    
    try:
        info = cache_manager.redis_client.info("stats")
        return {
            "total_commands_processed": info.get("total_commands_processed", 0),
            "keyspace_hits": info.get("keyspace_hits", 0),
            "keyspace_misses": info.get("keyspace_misses", 0),
            "connected_clients": info.get("connected_clients", 0)
        }
    except Exception as e:
        return {"error": str(e)}
