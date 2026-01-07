import math
from typing import List, Tuple

def calculate_route_stats(
    path: List[Tuple[float, float]],
    pollution_data: dict
) -> dict:
    """
    Calculate statistics for a route
    
    Args:
        path: List of (lat, lon) waypoints
        pollution_data: Dictionary mapping coordinates to pollution levels
    
    Returns:
        Dictionary with total_distance, avg_pollution, max_pollution
    """
    if not path or len(path) < 2:
        return {
            "total_distance_km": 0.0,
            "avg_pollution": 0.0,
            "max_pollution": 0.0
        }
    
    total_distance = 0.0
    pollution_values = []
    
    for i in range(len(path) - 1):
        # Calculate distance
        dist = haversine_distance(path[i], path[i + 1])
        total_distance += dist
        
        # Get pollution at waypoint
        pollution = pollution_data.get(path[i], 50.0)
        pollution_values.append(pollution)
    
    # Include final waypoint pollution
    pollution_values.append(pollution_data.get(path[-1], 50.0))
    
    avg_pollution = sum(pollution_values) / len(pollution_values)
    max_pollution = max(pollution_values)
    
    return {
        "total_distance_km": round(total_distance, 2),
        "avg_pollution": round(avg_pollution, 1),
        "max_pollution": round(max_pollution, 1)
    }

def haversine_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """Calculate distance between coordinates in km"""
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    
    R = 6371  # Earth radius in km
    
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = (
        math.sin(dlat / 2) ** 2 +
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
        math.sin(dlon / 2) ** 2
    )
    
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c
