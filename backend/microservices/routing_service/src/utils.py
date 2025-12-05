import math
from typing import Tuple, Callable

def haversine_distance(lat1: float, lon1: float, 
                       lat2: float, lon2: float) -> float:
    """
    Calculate distance between two points in km using Haversine formula.
    """
    R = 6371  # Earth radius in km
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = (math.sin(dlat / 2) ** 2 + 
         math.cos(lat1_rad) * math.cos(lat2_rad) * 
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c


def euclidean_distance(x1: float, y1: float, 
                      x2: float, y2: float) -> float:
    """Euclidean distance in 2D grid."""
    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)


def manhattan_distance(x1: float, y1: float,
                      x2: float, y2: float) -> float:
    """Manhattan distance in grid."""
    return abs(x2 - x1) + abs(y2 - y1)


def calculate_pollution_score(pm10: float, pm25: float, no2: float) -> float:
    """
    Calculate pollution score based on WHO guidelines.
    PM10 limit: 50 μg/m³
    PM2.5 limit: 25 μg/m³
    NO2 limit: 40 μg/m³
    """
    score = (
        (pm10 / 50.0) * 0.4 +
        (pm25 / 25.0) * 0.4 +
        (no2 / 40.0) * 0.2
    )
    return max(0.0, score)


def get_grid_cell(lat: float, lon: float, resolution: float = 0.001) -> Tuple[int, int]:
    """
    Map coordinates to grid cell.
    Resolution 0.001 ≈ 100m in Bucharest.
    """
    cell_lat = int(lat / resolution)
    cell_lon = int(lon / resolution)
    return (cell_lat, cell_lon)


def cell_to_coords(cell: Tuple[int, int], resolution: float = 0.001) -> Tuple[float, float]:
    """Convert grid cell back to coordinates."""
    lat = cell[0] * resolution
    lon = cell[1] * resolution
    return (lat, lon)


# Heuristics for A*
def haversine_heuristic(graph, cell1: Tuple, cell2: Tuple) -> float:
    """Haversine heuristic (admissible)."""
    node1 = graph.nodes[cell1]
    node2 = graph.nodes[cell2]
    return haversine_distance(
        node1['lat'], node1['lon'],
        node2['lat'], node2['lon']
    )


def euclidean_heuristic(graph, cell1: Tuple, cell2: Tuple) -> float:
    """Euclidean heuristic in 2D space."""
    return euclidean_distance(cell1[0], cell1[1], cell2[0], cell2[1]) * 0.001


def manhattan_heuristic(graph, cell1: Tuple, cell2: Tuple) -> float:
    """Manhattan heuristic."""
    return manhattan_distance(cell1[0], cell1[1], cell2[0], cell2[1]) * 0.001


def zero_heuristic(graph, cell1: Tuple, cell2: Tuple) -> float:
    """Zero heuristic (transforms A* into Dijkstra)."""
    return 0.0
