import math
from typing import List, Tuple, Dict, Callable

# HEURISTIC FUNCTIONS
def haversine_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """Great-circle distance (most accurate)"""
    lat1, lon1 = coord1
    lat2, lon2 = coord2

    earth_radius = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)

    return earth_radius * 2 * math.asin(math.sqrt(a))

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
# All pollutant keys for stats calculation
POLLUTANT_KEYS = ['pm10', 'pm2_5', 'pm1_0', 'no2', 'co', 'co2', 'nh3', 'vocs']

def calculate_route_stats(
    path: List[Tuple[float, float]],
    pollution_data: Dict[Tuple[float, float], Dict[str, float]]
) -> Dict:
    """
    Calculate route statistics for all pollutants.
    
    Only counts valid pollution values (>= 0).
    Returns avg and max for each pollutant that has data.
    """
    if not path or len(path) < 2:
        result = {"total_distance_km": 0.0, "avg_aqi": 0.0, "max_aqi": 0.0}
        for key in POLLUTANT_KEYS:
            result[f"avg_{key}"] = -1
            result[f"max_{key}"] = -1
        return result

    total_distance = 0.0
    aqi_values = []

    # Collect values for each pollutant
    pollutant_values = {key: [] for key in POLLUTANT_KEYS}

    for i in range(len(path)):
        if i > 0:
            total_distance += haversine_distance(path[i-1], path[i])

        pollution = pollution_data.get(path[i], {})

        # Collect AQI
        aqi = pollution.get('aqi', -1)
        if aqi >= 0:
            aqi_values.append(aqi)

        # Collect each pollutant
        for key in POLLUTANT_KEYS:
            val = pollution.get(key, -1)
            if val >= 0:
                pollutant_values[key].append(val)

    # Build result dict
    result = {
        "total_distance_km": round(total_distance, 2),
        "avg_aqi": round(sum(aqi_values) / len(aqi_values), 1) if aqi_values else 0.0,
        "max_aqi": round(max(aqi_values), 1) if aqi_values else 0.0
    }

    # Add stats for each pollutant (only if we have data)
    for key in POLLUTANT_KEYS:
        values = pollutant_values[key]
        if values:
            result[f"avg_{key}"] = round(sum(values) / len(values), 1)
            result[f"max_{key}"] = round(max(values), 1)
        else:
            result[f"avg_{key}"] = -1  # No data
            result[f"max_{key}"] = -1

    return result
