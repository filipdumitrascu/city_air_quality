import logging
import math
from typing import Dict, List, Tuple, Set, Optional

import sys
import os

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from config import get_config

logger = logging.getLogger(__name__)

# AQI CALCULATION - Weighted average with EPA/WHO thresholds
# Pollutant configuration: thresholds (good/moderate/unhealthy), weight
POLLUTANT_CONFIG = {
    'pm2_5':  {'thresholds': [12, 35, 55],      'weight': 3.0},
    'pm10':   {'thresholds': [54, 154, 254],    'weight': 2.0},
    'no2':    {'thresholds': [53, 100, 360],    'weight': 2.0},
    'co':     {'thresholds': [4.4, 9.4, 12.4],  'weight': 1.5},
    'pm1_0':  {'thresholds': [10, 25, 50],      'weight': 1.5},
    'co2':    {'thresholds': [600, 1000, 2000], 'weight': 1.0},
    'vocs':   {'thresholds': [250, 500, 1000],  'weight': 1.0},
    'nh3':    {'thresholds': [25, 50, 100],     'weight': 0.5},
}


def normalize_pollutant(value: float, thresholds: List[float]) -> float:
    """Normalize pollutant value to 0-100+ scale based on EPA thresholds."""
    if value <= thresholds[0]:
        # Good: 0-50
        return (value / thresholds[0]) * 50 if thresholds[0] > 0 else 0
    elif value <= thresholds[1]:
        # Moderate: 50-100
        return 50 + ((value - thresholds[0]) / (thresholds[1] - thresholds[0])) * 50
    elif value <= thresholds[2]:
        # Unhealthy: 100-150
        return 100 + ((value - thresholds[1]) / (thresholds[2] - thresholds[1])) * 50
    else:
        # Very unhealthy: 150+
        return 150 + ((value - thresholds[2]) / thresholds[2]) * 50


def calculate_aqi(data: Dict[str, float]) -> Optional[float]:
    """
    Calculate AQI from all available pollutants using weighted average.
    
    - Ignores values of -1 or None (missing data)
    - Uses EPA/WHO thresholds for normalization
    - Returns weighted average of normalized values
    - Returns None if no valid data
    """
    weighted_sum = 0.0
    total_weight = 0.0
    
    for pollutant, config in POLLUTANT_CONFIG.items():
        value = data.get(pollutant)
        if value is not None and value >= 0:
            normalized = normalize_pollutant(value, config['thresholds'])
            weighted_sum += normalized * config['weight']
            total_weight += config['weight']
    
    if total_weight == 0:
        return None
    
    return weighted_sum / total_weight


def calculate_aqi_legacy(pm10: float, pm2_5: float) -> Optional[float]:
    """Legacy function for backward compatibility."""
    return calculate_aqi({'pm10': pm10, 'pm2_5': pm2_5})


class PollutionGraph:
    """
    Weighted graph for pollution-aware pathfinding.
    
    Nodes are grid points, edges connect nearby points.
    Edge weight = distance * (1 + alpha * normalized_aqi)
    """
    
    def __init__(self, alpha: float = 0.5):
        self.config = get_config()
        self.alpha = alpha
        self.grid_resolution = self.config["grid_resolution"]
        
        self.nodes: Set[Tuple[float, float]] = set()
        self.edges: Dict[Tuple[float, float], List[Tuple[Tuple[float, float], float]]] = {}
        self.pollution_data: Dict[Tuple[float, float], Dict[str, float]] = {}
    
    def add_pollution_data(self, readings: List[Dict]):
        """
        Add pollution readings to graph.
        
        Expects list of dicts from Database Service with:
        - latitude, longitude
        - pm10, pm2_5, pm1_0, no2, co, co2, nh3, vocs (all optional)
        
        Values of -1 are kept but excluded from AQI calculation.
        """
        logger.info(f"Adding {len(readings)} pollution readings")
        
        pollutant_keys = ['pm10', 'pm2_5', 'pm1_0', 'no2', 'co', 'co2', 'nh3', 'vocs']
        
        for reading in readings:
            try:
                # Handle both dict and list formats
                if isinstance(reading, dict):
                    lat = float(reading.get("latitude", 0))
                    lon = float(reading.get("longitude", 0))
                    
                    # Extract all pollutants
                    pollutants = {}
                    for key in pollutant_keys:
                        val = reading.get(key)
                        pollutants[key] = float(val) if val is not None else -1
                else:
                    # Legacy list format - assume order matches schema
                    lat = float(reading[3])
                    lon = float(reading[4])
                    pollutants = {
                        'pm10': float(reading[5]) if len(reading) > 5 and reading[5] is not None else -1,
                        'pm2_5': float(reading[6]) if len(reading) > 6 and reading[6] is not None else -1,
                        'no2': float(reading[7]) if len(reading) > 7 and reading[7] is not None else -1,
                        'co': float(reading[8]) if len(reading) > 8 and reading[8] is not None else -1,
                        'co2': float(reading[9]) if len(reading) > 9 and reading[9] is not None else -1,
                        'pm1_0': float(reading[10]) if len(reading) > 10 and reading[10] is not None else -1,
                        'nh3': float(reading[11]) if len(reading) > 11 and reading[11] is not None else -1,
                        'vocs': float(reading[12]) if len(reading) > 12 and reading[12] is not None else -1,
                    }
                
                # Snap to grid
                grid_lat = round(lat / self.grid_resolution) * self.grid_resolution
                grid_lon = round(lon / self.grid_resolution) * self.grid_resolution
                grid_point = (grid_lat, grid_lon)
                
                # Calculate AQI using all available pollutants
                aqi = calculate_aqi(pollutants)
                
                if aqi is None:
                    aqi = 50.0  # Default neutral value
                
                # Average if multiple readings at same grid point
                if grid_point in self.pollution_data:
                    existing = self.pollution_data[grid_point]
                    
                    # Average each pollutant separately
                    merged = {}
                    for key in pollutant_keys:
                        old_val = existing.get(key, -1)
                        new_val = pollutants.get(key, -1)
                        
                        if old_val >= 0 and new_val >= 0:
                            merged[key] = (old_val + new_val) / 2
                        elif new_val >= 0:
                            merged[key] = new_val
                        else:
                            merged[key] = old_val
                    
                    merged['aqi'] = calculate_aqi(merged) or existing.get('aqi', 50)
                    self.pollution_data[grid_point] = merged
                else:
                    pollutants['aqi'] = aqi
                    self.pollution_data[grid_point] = pollutants
                
                self.nodes.add(grid_point)
                
            except Exception as e:
                logger.warning(f"Skipping invalid reading: {e}")
                continue
        
        logger.info(f"Graph has {len(self.nodes)} nodes")
    
    def build_edges(self):
        """Build edges connecting nearby nodes"""
        logger.info("Building graph edges...")
        
        # Get AQI range for normalization
        aqi_values = [
            p['aqi'] for p in self.pollution_data.values() 
            if p.get('aqi') is not None
        ]
        
        if aqi_values:
            min_aqi = min(aqi_values)
            max_aqi = max(aqi_values)
            aqi_range = max_aqi - min_aqi or 1
        else:
            min_aqi, aqi_range = 0, 1
        
        # Connect each node to k nearest neighbors (handles sparse data)
        k_neighbors = 8  # Connect to up to 8 nearest nodes
        max_edge_dist = 2.0  # Maximum 2km edge (prevents connecting across city)
        
        for node in self.nodes:
            # Sort all other nodes by distance
            others_by_dist = sorted(
                [(other, self._haversine(node, other)) for other in self.nodes if other != node],
                key=lambda x: x[1]
            )
            
            neighbors = []
            for other, distance in others_by_dist[:k_neighbors]:
                if distance > max_edge_dist:
                    break  # Don't connect if too far
                
                # Weight based on pollution at destination
                other_aqi = self.pollution_data.get(other, {}).get('aqi', 50)
                normalized_aqi = (other_aqi - min_aqi) / aqi_range
                
                weight = distance * (1 + self.alpha * normalized_aqi)
                neighbors.append((other, weight))
            
            self.edges[node] = neighbors
        
        total_edges = sum(len(n) for n in self.edges.values())
        logger.info(f"Built {total_edges} edges")
    
    def get_nearest_node(self, lat: float, lon: float) -> Tuple[float, float]:
        """Find nearest node to given coordinate"""
        if not self.nodes:
            return (
                round(lat / self.grid_resolution) * self.grid_resolution,
                round(lon / self.grid_resolution) * self.grid_resolution
            )
        
        return min(self.nodes, key=lambda n: self._haversine((lat, lon), n))
    
    def get_neighbors(self, node: Tuple[float, float]) -> List[Tuple[Tuple[float, float], float]]:
        """Get neighbors of node: [(neighbor, weight), ...]"""
        return self.edges.get(node, [])
    
    def get_pollution(self, node: Tuple[float, float]) -> Dict[str, float]:
        """Get pollution at node"""
        return self.pollution_data.get(node, {'pm10': -1, 'pm2_5': -1, 'aqi': 50})
    
    @staticmethod
    def _haversine(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
        """Distance in km"""
        lat1, lon1 = coord1
        lat2, lon2 = coord2
        
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2) ** 2)
        
        return R * 2 * math.asin(math.sqrt(a))
