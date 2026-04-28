from pydantic import BaseModel, Field
from typing import List, Literal, Optional

class Coordinate(BaseModel):
    """Geographic coordinate"""
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)

class RouteRequest(BaseModel):
    """Request for route calculation"""
    start: Coordinate
    goal: Coordinate
    alpha: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Pollution weight: 0=fastest, 1=cleanest"
    )
    sensor_types: List[Literal["CityAirQ", "WearAware", "SPO-RO", "Forecast"]] = Field(
        default=["CityAirQ", "WearAware", "SPO-RO", "Forecast"],
        description="Sensor types: 'CityAirQ', 'WearAware', 'SPO-RO', 'Forecast'"
    )
    heuristic: Literal["haversine", "euclidean", "manhattan", "diagonal", "octile"] = Field(
        default="haversine",
        description="A* heuristic (foot mode only)"
    )
    transport_mode: Literal["foot", "bicycle"] = Field(
        default="bicycle",
        description="'foot' = A* on pollution grid, 'bicycle' = Google Routes API"
    )

class RouteNode(BaseModel):
    """Single waypoint with pollution values"""
    lat: float
    lon: float
    pm10: Optional[float] = None
    pm2_5: Optional[float] = None
    aqi: Optional[float] = None

class GeoJSONGeometry(BaseModel):
    """GeoJSON LineString"""
    type: str = "LineString"
    coordinates: List[List[float]]  # [[lon, lat], ...]

class GeoJSONProperties(BaseModel):
    """Route properties with pollution stats for all 8 pollutants"""
    distance_km: float
    duration_minutes: Optional[float] = None
    
    # Combined AQI (always present)
    avg_aqi: float
    max_aqi: float
    
    # Individual pollutants (Optional - only present if data available)
    # Values of -1 mean no data for that pollutant on this route
    avg_pm10: Optional[float] = None
    max_pm10: Optional[float] = None
    avg_pm2_5: Optional[float] = None
    max_pm2_5: Optional[float] = None
    avg_pm1_0: Optional[float] = None
    max_pm1_0: Optional[float] = None
    avg_no2: Optional[float] = None
    max_no2: Optional[float] = None
    avg_co: Optional[float] = None
    max_co: Optional[float] = None
    avg_co2: Optional[float] = None
    max_co2: Optional[float] = None
    avg_nh3: Optional[float] = None
    max_nh3: Optional[float] = None
    avg_vocs: Optional[float] = None
    max_vocs: Optional[float] = None
    
    # Metadata
    calculation_time_ms: float
    sensor_types_used: List[str]
    heuristic_used: Optional[str] = None
    transport_mode: str
    nodes_evaluated: Optional[int] = None
    google_routes_considered: Optional[int] = None
    cached: bool = False

class GeoJSONFeature(BaseModel):
    """GeoJSON Feature"""
    type: str = "Feature"
    geometry: GeoJSONGeometry
    properties: GeoJSONProperties

class RouteResponse(BaseModel):
    """Route response with GeoJSON and waypoints"""
    route: GeoJSONFeature
    waypoints: List[RouteNode]

class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    redis_connected: bool
    database_connected: bool
    google_routes_configured: Optional[bool] = None
