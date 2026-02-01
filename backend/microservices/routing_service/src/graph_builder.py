import logging
import math
from typing import Dict, List, Tuple, Set
from .config import get_config

logger = logging.getLogger(__name__)

class PollutionGraph:
    """
    Weighted graph where:
    - Nodes = geographic coordinates (grid points)
    - Edges = connections between nearby points
    - Weights = distance * (1 + alpha * normalized_pollution)
    """
    
    def __init__(self, alpha: float = 0.5):
        self.config = get_config()
        self.alpha = alpha
        self.nodes: Set[Tuple[float, float]] = set()
        self.edges: Dict[Tuple[float, float], List[Tuple[Tuple[float, float], float, float]]] = {}
        
        # Store all pollution data per node
        self.pollution_data: Dict[Tuple[float, float], Dict[str, float]] = {}
        self.sensor_types: Dict[Tuple[float, float], str] = {}
        self.grid_resolution = self.config["grid_resolution"]
    
    def calculate_aqi(self, pm10: float, pm25: float, no2: float) -> float:
        """
        Calculate combined Air Quality Index.
        PM2.5 is weighted higher as it's more harmful to health.
        """
        pm10_idx = pm10 if pm10 else 0
        pm25_idx = (pm25 if pm25 else 0) * 1.5  # PM2.5 weighted 1.5x
        no2_idx = (no2 if no2 else 0) * 0.8     # NO2 weighted 0.8x
        
        return (pm10_idx + pm25_idx + no2_idx) / 3.3
    
    def add_pollution_data(self, pollution_readings: List):
        """
        Add pollution data to graph.
        
        Args:
            pollution_readings: List of readings from Database Service
                               Schema: [sensor_id, timestamp, lat, lon, pm10, pm25, no2]
        """
        logger.info(f"Adding {len(pollution_readings)} pollution readings to graph")
        
        for reading in pollution_readings:
            try:
                if isinstance(reading, (list, tuple)):
                    sensor_id = reading[0]
                    lat = float(reading[2])
                    lon = float(reading[3])
                    pm10 = float(reading[4]) if len(reading) > 4 and reading[4] is not None else 0.0
                    pm25 = float(reading[5]) if len(reading) > 5 and reading[5] is not None else 0.0
                    no2 = float(reading[6]) if len(reading) > 6 and reading[6] is not None else 0.0
                    
                    sensor_type = "mobile" if sensor_id.startswith("M") else "fixed"
                else:
                    lat = float(reading.get("latitude", 0))
                    lon = float(reading.get("longitude", 0))
                    pm10 = float(reading.get("pm10", 0))
                    pm25 = float(reading.get("pm25", 0))
                    no2 = float(reading.get("no2", 0))
                    sensor_type = reading.get("sensor_type", "unknown")
                
                # Snap to grid
                grid_lat = round(lat / self.grid_resolution) * self.grid_resolution
                grid_lon = round(lon / self.grid_resolution) * self.grid_resolution
                grid_point = (grid_lat, grid_lon)
                
                # Calculate AQI
                aqi = self.calculate_aqi(pm10, pm25, no2)
                
                # Average if multiple readings at same grid point
                if grid_point in self.pollution_data:
                    existing = self.pollution_data[grid_point]
                    self.pollution_data[grid_point] = {
                        'pm10': (existing['pm10'] + pm10) / 2,
                        'pm25': (existing['pm25'] + pm25) / 2,
                        'no2': (existing['no2'] + no2) / 2,
                        'aqi': (existing['aqi'] + aqi) / 2
                    }
                else:
                    self.pollution_data[grid_point] = {
                        'pm10': pm10,
                        'pm25': pm25,
                        'no2': no2,
                        'aqi': aqi
                    }
                    self.sensor_types[grid_point] = sensor_type
                
                self.nodes.add(grid_point)
                
            except Exception as e:
                logger.warning(f"Skipping invalid reading: {e}")
                continue
        
        logger.info(f"Graph has {len(self.nodes)} nodes with pollution data")
    
    def build_edges(self):
        """Build edges connecting nearby nodes"""
        logger.info("Building graph edges...")
        
        # Get AQI values for normalization
        if self.pollution_data:
            aqi_values = [p['aqi'] for p in self.pollution_data.values()]
            min_aqi = min(aqi_values)
            max_aqi = max(aqi_values)
            aqi_range = max_aqi - min_aqi or 1
        else:
            min_aqi = 0
            aqi_range = 1
        
        # For each node, connect to nearby nodes
        for node in self.nodes:
            neighbors = []
            
            for other in self.nodes:
                if node == other:
                    continue
                
                distance = self._haversine_distance(node, other)
                
                # Only connect if within reasonable distance
                if distance <= self.grid_resolution * 111 * 1.5:
                    # Get AQI at destination for edge weight
                    other_data = self.pollution_data.get(other, {'aqi': 50})
                    aqi = other_data['aqi']
                    normalized_aqi = (aqi - min_aqi) / aqi_range
                    
                    # Weight = distance * (1 + alpha * aqi)
                    weight = distance * (1 + self.alpha * normalized_aqi)
                    
                    neighbors.append((other, weight, aqi))
            
            self.edges[node] = neighbors
        
        total_edges = sum(len(neighbors) for neighbors in self.edges.values())
        logger.info(f"Built {total_edges} edges for {len(self.nodes)} nodes")
    
    def get_nearest_node(self, lat: float, lon: float) -> Tuple[float, float]:
        """Find nearest node in graph to given coordinate"""
        if not self.nodes:
            return (
                round(lat / self.grid_resolution) * self.grid_resolution,
                round(lon / self.grid_resolution) * self.grid_resolution
            )
        
        nearest = min(
            self.nodes,
            key=lambda node: self._haversine_distance((lat, lon), node)
        )
        return nearest
    
    def get_neighbors(self, node: Tuple[float, float]) -> List[Tuple[Tuple[float, float], float, float]]:
        """Get neighbors of a node with (neighbor, weight, aqi)"""
        return self.edges.get(node, [])
    
    def get_pollution(self, node: Tuple[float, float]) -> Dict[str, float]:
        """Get all pollution values at node"""
        return self.pollution_data.get(node, {'pm10': 0, 'pm25': 0, 'no2': 0, 'aqi': 0})
    
    @staticmethod
    def _haversine_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
        """Calculate distance in km using Haversine formula"""
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
