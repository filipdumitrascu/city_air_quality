from pydantic import BaseModel, Field
from typing import List, Literal, Optional

class Coordinate(BaseModel):
    """Geographic coordinate"""
    lat: float = Field(..., description="Latitude")
    lon: float = Field(..., description="Longitude")

class RouteRequest(BaseModel):
    """Request for route calculation"""
    start: Coordinate
    goal: Coordinate
    alpha: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Weight for pollution vs distance (0=fastest, 1=cleanest)"
    )
    sensor_types: List[Literal["fixed", "mobile"]] = Field(
        default=["fixed", "mobile"],
        description="Which sensor types to use: ['fixed'], ['mobile'], or ['fixed', 'mobile']"
    )

class RouteNode(BaseModel):
    """Single node in the route"""
    lat: float
    lon: float
    pollution_level: Optional[float] = None
    distance_from_start: Optional[float] = None

class RouteResponse(BaseModel):
    """Response with calculated route"""
    route: List[RouteNode]
    total_distance_km: float
    avg_pollution: float
    max_pollution: float
    calculation_time_ms: float
    cached: bool = False
    sensor_types_used: List[str]
    nodes_evaluated: int

class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    redis_connected: bool
    database_connected: bool
