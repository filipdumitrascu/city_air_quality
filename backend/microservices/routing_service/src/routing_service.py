from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import os
import logging
from datetime import datetime, timedelta
from typing import List

from .models import (
    RouteRequest, 
    RouteResponse, 
    ComparisonRequest,
    ComparisonResponse
)
from .graph_builder import PollutionGraph
from .pathfinding import AStarAlgorithm, DijkstraAlgorithm, BFSAlgorithm
from .cache_manager import CacheManager
from .utils import (
    get_grid_cell,
    haversine_heuristic,
    euclidean_heuristic,
    manhattan_heuristic,
    zero_heuristic,
    haversine_distance,
    calculate_pollution_score
)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/routing_service.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="Routing Service API",
    description="Pathfinding algorithms for least polluted routes",
    version="1.0.0"
)

# Initialize cache
cache = CacheManager(
    redis_host=os.getenv("REDIS_HOST", "redis"),
    redis_port=int(os.getenv("REDIS_PORT", 6379))
)

# Heuristic mapping
HEURISTICS = {
    "haversine": haversine_heuristic,
    "euclidean": euclidean_heuristic,
    "manhattan": manhattan_heuristic,
    "zero": zero_heuristic
}

# Algorithm mapping
def get_algorithm_instance(algo_name: str, graph, heuristic_fn=None):
    """Factory for algorithm instances."""
    algo_name = algo_name.lower()
    
    if algo_name == "astar":
        return AStarAlgorithm(graph, heuristic_fn=heuristic_fn)
    elif algo_name == "dijkstra":
        return DijkstraAlgorithm(graph)
    elif algo_name == "bfs":
        return BFSAlgorithm(graph)
    else:
        raise ValueError(f"Unknown algorithm: {algo_name}")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "CityAirQ Routing Service",
        "version": "0.1.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """Health check for Kubernetes."""
    cache_status = "connected" if cache.redis_client else "disconnected"
    return {
        "status": "healthy",
        "service": "routing-service",
        "cache": cache_status
    }

@app.post("/route/optimal", response_model=RouteResponse)
async def calculate_optimal_route(request: RouteRequest):
    """
    Calculate optimal route between two points.
    
    Flow:
    1. Check cache
    2. If miss: fetch pollution data, build graph, run algorithm
    3. Cache result
    4. Return route
    """
    try:
        logger.info(f"Route request: {request.algorithm} from ({request.start_lat}, {request.start_lon}) to ({request.end_lat}, {request.end_lon})")
        
        # Check cache
        cached_route = cache.get_cached_route(
            request.start_lat, request.start_lon,
            request.end_lat, request.end_lon,
            request.algorithm,
            request.time_window_hours
        )
        
        if cached_route:
            logger.info("Returning cached route")
            return JSONResponse(cached_route)
        
        # Cache miss - compute route
        logger.info("Cache miss - computing route")
        
        # Fetch pollution data
        pollution_data = await fetch_pollution_data(request.time_window_hours)
        
        if not pollution_data:
            raise HTTPException(status_code=404, detail="No pollution data available")
        
        # Build graph
        graph = PollutionGraph(resolution=0.001)
        graph.build_from_pollution_data(pollution_data)
        
        # Get algorithm instance
        heuristic_fn = HEURISTICS.get(request.heuristic, haversine_heuristic)
        algorithm = get_algorithm_instance(request.algorithm, graph, heuristic_fn)
        
        # Convert coordinates to grid cells
        start_cell = get_grid_cell(request.start_lat, request.start_lon)
        end_cell = get_grid_cell(request.end_lat, request.end_lon)
        
        # Find path
        result = algorithm.find_path(start_cell, end_cell)
        
        if 'error' in result:
            raise HTTPException(status_code=404, detail=result['error'])
        
        # Convert to response format
        response = convert_to_response(result, graph, request.algorithm, algorithm.get_stats())
        
        # Cache result
        cache.cache_route(
            request.start_lat, request.start_lon,
            request.end_lat, request.end_lon,
            request.algorithm,
            request.time_window_hours,
            response,
            ttl_minutes=15
        )
        
        logger.info(f"Route computed: {len(result['path'])} nodes, {algorithm.get_stats()['nodes_explored']} explored")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in calculate_optimal_route: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/route/compare", response_model=ComparisonResponse)
async def compare_algorithms(request: ComparisonRequest):
    """
    Compare multiple algorithms on the same route.
    KEY ENDPOINT FOR THESIS!
    """
    try:
        logger.info(f"Comparison request: {request.algorithms}")
        
        # Fetch pollution data
        pollution_data = await fetch_pollution_data(request.time_window_hours)
        
        if not pollution_data:
            raise HTTPException(status_code=404, detail="No pollution data available")
        
        # Build graph
        graph = PollutionGraph(resolution=0.001)
        graph.build_from_pollution_data(pollution_data)
        
        # Convert coordinates
        start_cell = get_grid_cell(request.start_lat, request.start_lon)
        end_cell = get_grid_cell(request.end_lat, request.end_lon)
        
        # Run all algorithms
        results = {}
        best_score = float('inf')
        best_algo = None
        
        for algo_name in request.algorithms:
            try:
                algorithm = get_algorithm_instance(algo_name, graph)
                result = algorithm.find_path(start_cell, end_cell)
                
                if 'error' not in result:
                    stats = algorithm.get_stats()
                    results[algo_name] = {
                        "path_length": stats['path_length'],
                        "nodes_explored": stats['nodes_explored'],
                        "total_cost": stats.get('total_cost', 0),
                        "path": result['path'][:10]  # First 10 nodes for brevity
                    }
                    
                    # Determine best (lowest cost)
                    if stats.get('total_cost', float('inf')) < best_score:
                        best_score = stats.get('total_cost', float('inf'))
                        best_algo = algo_name
                        
            except Exception as e:
                logger.error(f"Error running {algo_name}: {e}")
                results[algo_name] = {"error": str(e)}
        
        # Calculate comparison metrics
        comparison_metrics = {
            "fastest_exploration": min(results.items(), key=lambda x: x[1].get('nodes_explored', float('inf')))[0],
            "shortest_path": min(results.items(), key=lambda x: x[1].get('path_length', float('inf')))[0],
            "lowest_cost": best_algo
        }
        
        return {
            "results": results,
            "best_algorithm": best_algo,
            "comparison_metrics": comparison_metrics
        }
        
    except Exception as e:
        logger.error(f"Error in compare_algorithms: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/cache/stats")
async def get_cache_stats():
    """Get cache statistics."""
    return cache.get_stats()

@app.delete("/cache/clear")
async def clear_cache():
    """Clear all cache (admin endpoint)."""
    cache.clear_cache()
    return {"message": "Cache cleared"}


async def fetch_pollution_data(time_window_hours: int) -> List[dict]:
    """
    Fetch pollution data from database service.
    TODO: Implement actual HTTP call to database-service.
    For now, returns mock data for testing.
    """
    # Mock data for development
    mock_data = [
        {'latitude': 44.4268, 'longitude': 26.1025, 'pm10': 30, 'pm2_5': 15, 'no2': 20},
        {'latitude': 44.4320, 'longitude': 26.1050, 'pm10': 45, 'pm2_5': 22, 'no2': 35},
        {'latitude': 44.4380, 'longitude': 26.1100, 'pm10': 25, 'pm2_5': 12, 'no2': 18},
        {'latitude': 44.4400, 'longitude': 26.1150, 'pm10': 50, 'pm2_5': 28, 'no2': 40},
        {'latitude': 44.4450, 'longitude': 26.1200, 'pm10': 35, 'pm2_5': 18, 'no2': 25},
    ]
    
    logger.info(f"Fetching pollution data (time_window: {time_window_hours}h)")
    
    # TODO: Replace with actual database call
    # database_url = os.getenv('DATABASE_SERVICE_URL', 'http://database-service:8000')
    # async with httpx.AsyncClient() as client:
    #     response = await client.post(
    #         f"{database_url}/query",
    #         json={"time_window_hours": time_window_hours}
    #     )
    #     return response.json()
    
    return mock_data


def convert_to_response(result: dict, graph, algorithm_name: str, stats: dict) -> dict:
    """Convert internal result format to API response."""
    path_nodes = []
    total_distance = 0
    total_pollution = 0
    
    for i, cell in enumerate(result['path']):
        node = graph.nodes[cell]
        path_nodes.append({
            'cell': cell,
            'lat': node['lat'],
            'lon': node['lon'],
            'pollution': node['pollution']
        })
        
        # Calculate distance
        if i > 0:
            prev_cell = result['path'][i-1]
            prev_node = graph.nodes[prev_cell]
            total_distance += haversine_distance(
                prev_node['lat'], prev_node['lon'],
                node['lat'], node['lon']
            )
        
        # Accumulate pollution
        total_pollution += calculate_pollution_score(**node['pollution'])
    
    avg_pollution = total_pollution / len(result['path']) if result['path'] else 0
    
    # Estimate time (assuming 15 km/h cycling speed)
    estimated_time = (total_distance / 15) * 60  # minutes
    
    return {
        'path': path_nodes,
        'total_distance_km': round(total_distance, 2),
        'avg_pollution_score': round(avg_pollution, 3),
        'estimated_time_minutes': round(estimated_time, 1),
        'nodes_explored': stats['nodes_explored'],
        'algorithm_used': algorithm_name,
        'stats': stats
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
