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
        """
        Initialize graph
        
        Args:
            alpha: Weight for pollution (0=ignore pollution, 1=only pollution)
        """
        self.config = get_config()
        self.alpha = alpha
        self.nodes: Set[Tuple[float, float]] = set()
        self.edges: Dict[Tuple[float, float], List[Tuple[float, float, float]]] = {}
        self.pollution_data: Dict[Tuple[float, float], float] = {}
        self.grid_resolution = self.config["grid_resolution"]
    
    def add_pollution_data(self, pollution_readings: List[Dict]):
        """
        Add pollution data to graph
        
        Args:
            pollution_readings: List of readings from Database Service
        """
        logger.info(f"Adding {len(pollution_readings)} pollution readings to graph")
        
        for reading in pollution_readings:
            try:
                lat = float(reading.get("latitude") or reading.get("Latitude"))
                lon = float(reading.get("longitude") or reading.get("Longitude"))
                
                # Get pollution value (PM10 as primary metric)
                pollution = float(
                    reading.get("pm10") or 
                    reading.get("PM10") or 
                    reading.get("PM1_0") or 
                    0
                )
                
                # Snap to grid
                grid_lat = round(lat / self.grid_resolution) * self.grid_resolution
                grid_lon = round(lon / self.grid_resolution) * self.grid_resolution
                
                grid_point = (grid_lat, grid_lon)
                
                # Average if multiple readings at same grid point
                if grid_point in self.pollution_data:
                    self.pollution_data[grid_point] = (
                        self.pollution_data[grid_point] + pollution
                    ) / 2
                else:
                    self.pollution_data[grid_point] = pollution
                
                self.nodes.add(grid_point)
                
            except Exception as e:
                logger.warning(f"Skipping invalid reading: {e}")
                continue
        
        logger.info(f"Graph has {len(self.nodes)} nodes with pollution data")
    
    def build_edges(self):
        """Build edges connecting nearby nodes"""
        logger.info("Building graph edges...")
        
        # Normalize pollution values
        if self.pollution_data:
            min_pollution = min(self.pollution_data.values())
            max_pollution = max(self.pollution_data.values())
            pollution_range = max_pollution - min_pollution or 1
        else:
            min_pollution = 0
            pollution_range = 1
        
        # For each node, connect to nearby nodes
        for node in self.nodes:
            neighbors = []
            
            for other in self.nodes:
                if node == other:
                    continue
                
                distance = self._haversine_distance(node, other)
                
                # Only connect if within reasonable distance
                if distance <= self.grid_resolution * 111 * 1.5:  # ~1.5 grid cells
                    # Get pollution at destination
                    pollution = self.pollution_data.get(other, 50.0)  # Default 50 if unknown
                    normalized_pollution = (pollution - min_pollution) / pollution_range
                    
                    # Weight = distance * (1 + alpha * pollution)
                    weight = distance * (1 + self.alpha * normalized_pollution)
                    
                    neighbors.append((other, weight, pollution))
            
            self.edges[node] = neighbors
        
        total_edges = sum(len(neighbors) for neighbors in self.edges.values())
        logger.info(f"Built {total_edges} edges for {len(self.nodes)} nodes")
    
    def get_nearest_node(self, lat: float, lon: float) -> Tuple[float, float]:
        """Find nearest node in graph to given coordinate"""
        if not self.nodes:
            # Return snapped grid point if no nodes exist yet
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
        """Get neighbors of a node with (neighbor, weight, pollution)"""
        return self.edges.get(node, [])
    
    def get_pollution(self, node: Tuple[float, float]) -> float:
        """Get pollution level at node"""
        return self.pollution_data.get(node, 50.0)
    
    @staticmethod
    def _haversine_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
        """
        Calculate distance between two coordinates in km using Haversine formula
        
        Args:
            coord1: (lat, lon) tuple
            coord2: (lat, lon) tuple
        
        Returns:
            Distance in kilometers
        """
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
