import math
from typing import List, Tuple, Dict, Callable

# HEURISTIC FUNCTIONS
def haversine_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """Great-circle distance (most accurate)"""
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    
    return R * 2 * math.asin(math.sqrt(a))

def euclidean_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """Straight-line distance (fast, approximate)"""
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    
    lat_km = (lat2 - lat1) * 111.0
    lon_km = (lon2 - lon1) * 111.0 * math.cos(math.radians((lat1 + lat2) / 2))
    
    return math.sqrt(lat_km ** 2 + lon_km ** 2)

def manhattan_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """Grid-based (taxicab) distance"""
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    
    lat_km = abs(lat2 - lat1) * 111.0
    lon_km = abs(lon2 - lon1) * 111.0 * math.cos(math.radians((lat1 + lat2) / 2))
    
    return lat_km + lon_km

def diagonal_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """Chebyshev distance"""
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    
    lat_km = abs(lat2 - lat1) * 111.0
    lon_km = abs(lon2 - lon1) * 111.0 * math.cos(math.radians((lat1 + lat2) / 2))
    
    return max(lat_km, lon_km)

def octile_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """8-directional movement"""
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    
    lat_km = abs(lat2 - lat1) * 111.0
    lon_km = abs(lon2 - lon1) * 111.0 * math.cos(math.radians((lat1 + lat2) / 2))
    
    sqrt2 = math.sqrt(2)
    return max(lat_km, lon_km) + (sqrt2 - 1) * min(lat_km, lon_km)


HEURISTICS: Dict[str, Callable] = {
    "haversine": haversine_distance,
    "euclidean": euclidean_distance,
    "manhattan": manhattan_distance,
    "diagonal": diagonal_distance,
    "octile": octile_distance,
}

def get_heuristic(name: str) -> Callable:
    """Get heuristic function by name"""
    name = name.lower()
    if name not in HEURISTICS:
        raise ValueError(f"Unknown heuristic: {name}. Available: {list(HEURISTICS.keys())}")
    return HEURISTICS[name]


# ROUTE STATISTICS
def calculate_route_stats(
    path: List[Tuple[float, float]],
    pollution_data: Dict[Tuple[float, float], Dict[str, float]]
) -> Dict:
    """
    Calculate route statistics.
    
    Only counts valid pollution values (>= 0).
    """
    if not path or len(path) < 2:
        return {
            "total_distance_km": 0.0,
            "avg_pm10": 0.0, "max_pm10": 0.0,
            "avg_pm2_5": 0.0, "max_pm2_5": 0.0,
            "avg_aqi": 0.0, "max_aqi": 0.0
        }
    
    total_distance = 0.0
    pm10_values = []
    pm2_5_values = []
    aqi_values = []
    
    for i in range(len(path)):
        if i > 0:
            total_distance += haversine_distance(path[i-1], path[i])
        
        pollution = pollution_data.get(path[i], {})
        
        # Only include valid values (not -1)
        pm10 = pollution.get('pm10', -1)
        pm2_5 = pollution.get('pm2_5', -1)
        aqi = pollution.get('aqi', -1)
        
        if pm10 >= 0:
            pm10_values.append(pm10)
        if pm2_5 >= 0:
            pm2_5_values.append(pm2_5)
        if aqi >= 0:
            aqi_values.append(aqi)
    
    return {
        "total_distance_km": round(total_distance, 2),
        "avg_pm10": round(sum(pm10_values) / len(pm10_values), 1) if pm10_values else 0.0,
        "max_pm10": round(max(pm10_values), 1) if pm10_values else 0.0,
        "avg_pm2_5": round(sum(pm2_5_values) / len(pm2_5_values), 1) if pm2_5_values else 0.0,
        "max_pm2_5": round(max(pm2_5_values), 1) if pm2_5_values else 0.0,
        "avg_aqi": round(sum(aqi_values) / len(aqi_values), 1) if aqi_values else 0.0,
        "max_aqi": round(max(aqi_values), 1) if aqi_values else 0.0
    }
