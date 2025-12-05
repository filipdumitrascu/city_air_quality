from typing import Dict, List, Tuple
import numpy as np
import utils

class PollutionGraph:
    """
    Grid graph over Bucharest.
    Nodes: grid cells (lat, lon)
    Edges: 8-connectivity with cost based on pollution and distance
    """
    
    def __init__(self, resolution: float = 0.001, alpha: float = 0.7):
        self.resolution = resolution
        self.alpha = alpha  # Pollution weight (0.7 = 70% pollution, 30% distance)
        self.nodes = {}
        self.edges = {}
        
        # Bucharest bounding box
        self.lat_min = 44.35
        self.lat_max = 44.50
        self.lon_min = 25.95
        self.lon_max = 26.20

    def build_graph(self, pollution_data: List[Dict]) -> None:
        """
        Build graph from pollution data points.
        Updated method name for consistency.
        """
        print(f"Building graph with resolution {self.resolution}...")
        print(f"Alpha (pollution weight): {self.alpha}")
        print(f"Beta (distance weight): {1-self.alpha}")
        
        # Create grid
        lat_range = np.arange(self.lat_min, self.lat_max, self.resolution)
        lon_range = np.arange(self.lon_min, self.lon_max, self.resolution)
        
        print(f"Grid dimensions: {len(lat_range)} x {len(lon_range)}")
        
        # Initialize nodes
        for lat in lat_range:
            for lon in lon_range:
                cell = utils.get_grid_cell(lat, lon, self.resolution)
                self.nodes[cell] = {
                    'lat': float(lat),
                    'lon': float(lon),
                    'pollution': {'pm10': 0, 'pm25': 0, 'no2': 0},
                    'has_data': False
                }
        
        # Populate with real data
        data_count = 0
        for data_point in pollution_data:
            cell = utils.get_grid_cell(
                data_point['lat'], 
                data_point['lon'],
                self.resolution
            )
            if cell in self.nodes:
                self.nodes[cell]['pollution'] = {
                    'pm10': data_point.get('pm10', 0),
                    'pm25': data_point.get('pm25', data_point.get('pm2_5', 0)),
                    'no2': data_point.get('no2', 0)
                }
                self.nodes[cell]['has_data'] = True
                data_count += 1
        
        print(f"Populated {data_count} cells with real data")
        
        # Interpolate missing data
        print("Interpolating missing values...")
        self._interpolate_missing_data()
        
        # Build edges
        print("Building edges...")
        self._build_edges()
        
        print(f"Graph ready: {len(self.nodes)} nodes, {sum(len(v) for v in self.edges.values())} edges")
    
    def _interpolate_missing_data(self):
        """Simple IDW interpolation for nodes without data."""
        nodes_with_data = [
            (cell, data) for cell, data in self.nodes.items() 
            if data['has_data']
        ]
        
        if not nodes_with_data:
            print("Warning: No real data points for interpolation")
            return
        
        interpolated_count = 0
        for cell, node_data in self.nodes.items():
            if node_data['has_data']:
                continue
            
            # Find 3 nearest nodes with data
            distances = []
            for data_cell, data_node in nodes_with_data:
                dist = utils.haversine_distance(
                    node_data['lat'], node_data['lon'],
                    data_node['lat'], data_node['lon']
                )
                distances.append((dist, data_node))
            
            distances.sort(key=lambda x: x[0])
            nearest = distances[:min(3, len(distances))]
            
            if not nearest:
                continue
            
            # IDW interpolation
            total_weight = 0
            weighted_pollution = {'pm10': 0, 'pm25': 0, 'no2': 0}
            
            for dist, neighbor in nearest:
                if dist < 0.0001:
                    node_data['pollution'] = neighbor['pollution'].copy()
                    break
                
                weight = 1 / (dist ** 2)
                total_weight += weight
                
                for pollutant in ['pm10', 'pm25', 'no2']:
                    weighted_pollution[pollutant] += (
                        neighbor['pollution'][pollutant] * weight
                    )
            
            if total_weight > 0:
                for pollutant in weighted_pollution:
                    weighted_pollution[pollutant] /= total_weight
                node_data['pollution'] = weighted_pollution
                interpolated_count += 1
        
        print(f"Interpolated {interpolated_count} cells")
    
    def _build_edges(self):
        """Build 8-connectivity edges."""
        directions = [
            (-1, 0), (1, 0), (0, -1), (0, 1),
            (-1, -1), (-1, 1), (1, -1), (1, 1)
        ]
        
        for cell in self.nodes:
            neighbors = []
            for dx, dy in directions:
                neighbor = (cell[0] + dx, cell[1] + dy)
                if neighbor in self.nodes:
                    neighbors.append(neighbor)
            self.edges[cell] = neighbors
    
    def get_edge_cost(self, from_cell: Tuple, to_cell: Tuple) -> float:
        """
        Calculate edge cost using stored alpha.
        Cost = alpha * pollution + (1-alpha) * distance
        
        Alpha (stored in self.alpha):
            - 0.7 (default) = 70% pollution weight, 30% distance weight
            - Higher alpha = prefer cleaner routes even if longer
            - Lower alpha = prefer shorter routes even if more polluted
        """
        from_node = self.nodes[from_cell]
        to_node = self.nodes[to_cell]
        
        # Distance component (in km)
        dist = utils.haversine_distance(
            from_node['lat'], from_node['lon'],
            to_node['lat'], to_node['lon']
        )
        
        # Pollution component (normalized score 0-1)
        from_pollution = utils.calculate_pollution_score(**from_node['pollution'])
        to_pollution = utils.calculate_pollution_score(**to_node['pollution'])
        avg_pollution = (from_pollution + to_pollution) / 2
        
        # Combined cost
        cost = self.alpha * avg_pollution + (1 - self.alpha) * dist
        
        return cost
    
    def get_neighbors(self, cell: Tuple) -> List[Tuple]:
        """Get neighbors of a cell."""
        return self.edges.get(cell, [])
