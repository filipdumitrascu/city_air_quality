import math
from typing import List, Tuple, Dict

def calculate_route_stats(
    path: List[Tuple[float, float]],
    pollution_data: Dict[Tuple[float, float], Dict[str, float]]
) -> Dict:
    """
    Calculate statistics for a route including all pollutants.
    
    Args:
        path: List of (lat, lon) waypoints
        pollution_data: Dictionary mapping coordinates to pollution dict
    
    Returns:
        Dictionary with distance and pollution statistics
    """
    if not path or len(path) < 2:
        return {
            "total_distance_km": 0.0,
            "avg_pm10": 0.0, "max_pm10": 0.0,
            "avg_pm25": 0.0, "max_pm25": 0.0,
            "avg_no2": 0.0, "max_no2": 0.0,
            "avg_aqi": 0.0, "max_aqi": 0.0
        }
    
    total_distance = 0.0
    pm10_values = []
    pm25_values = []
    no2_values = []
    aqi_values = []
    
    for i in range(len(path) - 1):
        dist = haversine_distance(path[i], path[i + 1])
        total_distance += dist
        
        pollution = pollution_data.get(path[i], {'pm10': 0, 'pm25': 0, 'no2': 0, 'aqi': 0})
        pm10_values.append(pollution.get('pm10', 0))
        pm25_values.append(pollution.get('pm25', 0))
        no2_values.append(pollution.get('no2', 0))
        aqi_values.append(pollution.get('aqi', 0))
    
    # Include final waypoint
    pollution = pollution_data.get(path[-1], {'pm10': 0, 'pm25': 0, 'no2': 0, 'aqi': 0})
    pm10_values.append(pollution.get('pm10', 0))
    pm25_values.append(pollution.get('pm25', 0))
    no2_values.append(pollution.get('no2', 0))
    aqi_values.append(pollution.get('aqi', 0))
    
    return {
        "total_distance_km": round(total_distance, 2),
        "avg_pm10": round(sum(pm10_values) / len(pm10_values), 1),
        "max_pm10": round(max(pm10_values), 1),
        "avg_pm25": round(sum(pm25_values) / len(pm25_values), 1),
        "max_pm25": round(max(pm25_values), 1),
        "avg_no2": round(sum(no2_values) / len(no2_values), 1),
        "max_no2": round(max(no2_values), 1),
        "avg_aqi": round(sum(aqi_values) / len(aqi_values), 1),
        "max_aqi": round(max(aqi_values), 1)
    }

def haversine_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """Calculate distance between coordinates in km"""
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    
    R = 6371
    
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = (
        math.sin(dlat / 2) ** 2 +
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
        math.sin(dlon / 2) ** 2
    )
    
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c
