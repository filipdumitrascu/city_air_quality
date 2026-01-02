from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime

class RouteRequest(BaseModel):
    """Request model for route calculation."""
    start_lat: float = Field(..., ge=44.3, le=44.5, description="Start latitude in Bucharest")
    start_lon: float = Field(..., ge=25.9, le=26.2, description="Start longitude in Bucharest")
    end_lat: float = Field(..., ge=44.3, le=44.5, description="End latitude in Bucharest")
    end_lon: float = Field(..., ge=25.9, le=26.2, description="End longitude in Bucharest")
    algorithm: str = Field(default="astar", description="Algorithm: astar, dijkstra, bfs")
    heuristic: str = Field(default="haversine", description="Heuristic: haversine, euclidean, manhattan")
    time_window_hours: int = Field(default=1, ge=1, le=24, description="Data time window in hours")
    alpha: float = Field(default=0.7, ge=0.0, le=1.0, description="Pollution weight (0=distance only, 1=pollution only)")

class NodeInfo(BaseModel):
    """Information about a graph node."""
    cell: tuple
    lat: float
    lon: float
    pollution: Dict[str, float]

class RouteResponse(BaseModel):
    """Response model for calculated route."""
    path: List[Dict]
    total_distance_km: float
    avg_pollution_score: float
    estimated_time_minutes: float
    nodes_explored: int
    algorithm_used: str
    stats: Dict

class ComparisonRequest(BaseModel):
    """Request for comparing multiple algorithms."""
    start_lat: float = Field(..., ge=44.3, le=44.5)
    start_lon: float = Field(..., ge=25.9, le=26.2)
    end_lat: float = Field(..., ge=44.3, le=44.5)
    end_lon: float = Field(..., ge=25.9, le=26.2)
    algorithms: List[str] = Field(default=["astar", "dijkstra", "bfs"])
    time_window_hours: int = Field(default=1, ge=1, le=24)

class ComparisonResponse(BaseModel):
    """Response for algorithm comparison."""
    results: Dict[str, Dict]
    best_algorithm: str
    comparison_metrics: Dict
