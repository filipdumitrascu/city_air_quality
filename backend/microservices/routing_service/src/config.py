import os
from typing import Dict

def get_config() -> Dict:
    """Get service configuration from environment variables"""
    return {
        # Redis configuration
        "redis_host": os.getenv("REDIS_HOST", "redis"),
        "redis_port": int(os.getenv("REDIS_PORT", 6379)),
        "redis_db": int(os.getenv("REDIS_DB", 0)),
        "cache_ttl": int(os.getenv("CACHE_TTL", 3600)),  # 1 hour
        
        # Database Service URL
        "database_service_url": os.getenv("DATABASE_SERVICE_URL", "http://database-service:8000"),
        
        # Routing parameters
        "grid_resolution": float(os.getenv("GRID_RESOLUTION", 0.01)),  # ~1km in lat/lon
        "pollution_weight_multiplier": float(os.getenv("POLLUTION_WEIGHT", 10.0)),
        
        # Bucharest bounds (for grid generation)
        "bucharest_bounds": {
            "lat_min": 44.35,
            "lat_max": 44.50,
            "lon_min": 26.00,
            "lon_max": 26.20
        },
        
        # Query radius for pollution data (km)
        "query_radius_km": float(os.getenv("QUERY_RADIUS", 2.0)),
    }
