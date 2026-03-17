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


def calculate_aqi(pm10: float, pm2_5: float) -> Optional[float]:
    """
    Calculate AQI from PM10 and PM2.5.
    
    - Ignores values of -1 (missing data)
    - PM2.5 weighted 1.5x (more harmful to health)
    - Returns None if no valid data
    """
    valid_values = []
    
    if pm10 is not None and pm10 >= 0:
        valid_values.append(pm10)
    
    if pm2_5 is not None and pm2_5 >= 0:
        valid_values.append(pm2_5 * 1.5)  # PM2.5 weighted higher
    
    if not valid_values:
        return None
    
    return sum(valid_values) / len(valid_values)


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
        - latitude, longitude, pm10, pm2_5
        
        Values of -1 are kept but excluded from AQI calculation.
        """
        logger.info(f"Adding {len(readings)} pollution readings")
        
        for reading in readings:
            try:
                # Handle both dict and list formats
                if isinstance(reading, dict):
                    lat = float(reading.get("latitude", 0))
                    lon = float(reading.get("longitude", 0))
                    pm10 = reading.get("pm10")
                    pm2_5 = reading.get("pm2_5")
                else:
                    # Legacy list format [sensor_id, sensor_type, ts, lat, lon, ...]
                    lat = float(reading[3])
                    lon = float(reading[4])
                    pm10 = reading[5] if len(reading) > 5 else None
                    pm2_5 = reading[6] if len(reading) > 6 else None
                
                # Convert to float, handling None
                pm10 = float(pm10) if pm10 is not None else -1
                pm2_5 = float(pm2_5) if pm2_5 is not None else -1
                
                # Snap to grid
                grid_lat = round(lat / self.grid_resolution) * self.grid_resolution
                grid_lon = round(lon / self.grid_resolution) * self.grid_resolution
                grid_point = (grid_lat, grid_lon)
                
                # Calculate AQI (ignores -1 values)
                aqi = calculate_aqi(pm10, pm2_5)
                
                if aqi is None:
                    # No valid pollution data at this point
                    aqi = 50.0  # Default neutral value
                
                # Average if multiple readings at same grid point
                if grid_point in self.pollution_data:
                    existing = self.pollution_data[grid_point]
                    
                    # Average only valid values
                    new_pm10 = pm10 if pm10 >= 0 else existing.get('pm10', -1)
                    new_pm2_5 = pm2_5 if pm2_5 >= 0 else existing.get('pm2_5', -1)
                    
                    if existing.get('pm10', -1) >= 0 and pm10 >= 0:
                        new_pm10 = (existing['pm10'] + pm10) / 2
                    if existing.get('pm2_5', -1) >= 0 and pm2_5 >= 0:
                        new_pm2_5 = (existing['pm2_5'] + pm2_5) / 2
                    
                    new_aqi = calculate_aqi(new_pm10, new_pm2_5) or existing.get('aqi', 50)
                    
                    self.pollution_data[grid_point] = {
                        'pm10': new_pm10,
                        'pm2_5': new_pm2_5,
                        'aqi': new_aqi
                    }
                else:
                    self.pollution_data[grid_point] = {
                        'pm10': pm10,
                        'pm2_5': pm2_5,
                        'aqi': aqi
                    }
                
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
        
        # Max edge distance (diagonal of grid cell)
        max_edge_dist = self.grid_resolution * 111 * 1.5  # ~330m
        
        for node in self.nodes:
            neighbors = []
            
            for other in self.nodes:
                if node == other:
                    continue
                
                distance = self._haversine(node, other)
                
                if distance <= max_edge_dist:
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
