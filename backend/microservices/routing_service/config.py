import os
from typing import Dict

def get_config() -> Dict:
    """Get service configuration from environment variables"""
    return {
        # Redis
        "redis_host": os.getenv("REDIS_HOST", "redis-service"),
        "redis_port": int(os.getenv("REDIS_PORT", 6379)),
        "redis_db": int(os.getenv("REDIS_DB", 0)),
        "cache_ttl": int(os.getenv("CACHE_TTL", 3600)),
        
        # Database Service
        "database_service_url": os.getenv("DATABASE_SERVICE_URL", "http://database-service:8000"),
        
        # Google Maps API
        "google_maps_api_key": os.getenv("GOOGLE_MAPS_API_KEY", ""),
        
        # Grid parameters
        "grid_resolution": float(os.getenv("GRID_RESOLUTION", 0.002)),  # ~220m
        
        # Bucharest bounds
        "bucharest_bounds": {
            "lat_min": 44.35,
            "lat_max": 44.50,
            "lon_min": 26.00,
            "lon_max": 26.20
        },
        
        # Google Routes
        "waypoint_sample_distance_m": int(os.getenv("WAYPOINT_SAMPLE_DISTANCE", 200)),
    }


ROUTING_POLLUTANTS = ["pm10", "pm2_5", "pm1_0", "no2", "co", "co2", "nh3", "vocs"]
