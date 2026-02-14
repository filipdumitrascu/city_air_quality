from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Dict, Any

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
    heuristic: Literal["haversine", "euclidean", "manhattan", "diagonal", "octile"] = Field(
        default="haversine",
        description="Heuristic function for A* pathfinding"
    )

class RouteNode(BaseModel):
    """Single node in the route with all pollution values"""
    lat: float
    lon: float
    pm10: Optional[float] = None
    pm25: Optional[float] = None
    no2: Optional[float] = None
    aqi: Optional[float] = None  # Combined Air Quality Index

class GeoJSONGeometry(BaseModel):
    """GeoJSON LineString geometry"""
    type: str = "LineString"
    coordinates: List[List[float]]  # [[lon, lat], ...]

class GeoJSONProperties(BaseModel):
    """GeoJSON properties with all pollution metrics"""
    distance_km: float
    # PM10
    avg_pollution_pm10: float
    max_pollution_pm10: float
    # PM2.5
    avg_pollution_pm25: float
    max_pollution_pm25: float
    # NO2
    avg_pollution_no2: float
    max_pollution_no2: float
    # Combined AQI
    avg_aqi: float
    max_aqi: float
    # Metadata
    calculation_time_ms: float
    sensor_types_used: List[str]
    heuristic_used: str
    nodes_evaluated: int
    cached: bool

class GeoJSONFeature(BaseModel):
    """GeoJSON Feature"""
    type: str = "Feature"
    geometry: GeoJSONGeometry
    properties: GeoJSONProperties

class RouteResponse(BaseModel):
    """Response with calculated route in GeoJSON format"""
    route: GeoJSONFeature
    waypoints: List[RouteNode]

class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    redis_connected: bool
    database_connected: bool
