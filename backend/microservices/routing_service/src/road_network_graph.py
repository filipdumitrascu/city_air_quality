"""
Road Network Graph Builder for Bucharest
Uses real road intersections instead of uniform grid.
"""

from typing import Dict, List, Tuple, Set
import numpy as np
import utils

class RoadNetworkGraph:
    """
    Graph based on real Bucharest road network.
    Nodes = intersections
    Edges = actual roads connecting them
    """
    
    def __init__(self, alpha: float = 0.7):
        self.alpha = alpha
        self.nodes = {}  # intersection_id -> {lat, lon, pollution}
        self.edges = {}  # intersection_id -> [(neighbor_id, road_type)]
        
        # Road types with different speeds/preferences
        self.road_types = {
            'highway': {'speed_km_h': 90, 'preference': 1.0},
            'primary': {'speed_km_h': 60, 'preference': 0.9},
            'secondary': {'speed_km_h': 50, 'preference': 0.8},
            'residential': {'speed_km_h': 30, 'preference': 0.7},
        }
    
    def build_from_bucharest_roads(self):
        """
        Build graph from simplified Bucharest road network.
        Major intersections and roads only.
        """
        print("Building road network graph...")
        
        # Define major intersections (simplified)
        intersections = self._get_bucharest_intersections()
        
        # Define road connections
        road_connections = self._get_bucharest_roads()
        
        # Create nodes
        for int_id, data in intersections.items():
            self.nodes[int_id] = {
                'lat': data['lat'],
                'lon': data['lon'],
                'name': data['name'],
                'pollution': {'pm10': 0, 'pm25': 0, 'no2': 0},
                'has_data': False
            }
        
        # Create edges
        for int_id in self.nodes:
            self.edges[int_id] = []
        
        for conn in road_connections:
            from_id, to_id, road_type = conn
            if from_id in self.nodes and to_id in self.nodes:
                self.edges[from_id].append((to_id, road_type))
                self.edges[to_id].append((from_id, road_type))  # Bidirectional
        
        print(f"Created {len(self.nodes)} intersections")
        print(f"Created {sum(len(v) for v in self.edges.values()) // 2} roads")
        
        return self
    
    def _get_bucharest_intersections(self) -> Dict:
        """
        Major intersections in Bucharest (simplified).
        IDs: descriptive names for debugging.
        """
        return {
            # North
            'herastrau': {'lat': 44.4650, 'lon': 26.0850, 'name': 'Herăstrău Park'},
            'aviatorilor': {'lat': 44.4550, 'lon': 26.0850, 'name': 'Piața Aviatorilor'},
            'victoriei': {'lat': 44.4478, 'lon': 26.0975, 'name': 'Piața Victoriei'},
            'romana': {'lat': 44.4358, 'lon': 26.1028, 'name': 'Piața Romană'},
            
            # Center
            'universitate': {'lat': 44.4365, 'lon': 26.1025, 'name': 'Piața Universității'},
            'unirii': {'lat': 44.4268, 'lon': 26.1025, 'name': 'Piața Unirii'},
            'cismigiu': {'lat': 44.4367, 'lon': 26.0897, 'name': 'Cișmigiu'},
            
            # West
            'cotroceni': {'lat': 44.4320, 'lon': 26.0580, 'name': 'Cotroceni'},
            'militari': {'lat': 44.4350, 'lon': 26.0450, 'name': 'Militari'},
            'drumul_taberei': {'lat': 44.4250, 'lon': 26.0350, 'name': 'Drumul Taberei'},
            
            # East
            'obor': {'lat': 44.4350, 'lon': 26.1250, 'name': 'Obor'},
            'pantelimon': {'lat': 44.4150, 'lon': 26.1450, 'name': 'Pantelimon'},
            'titan': {'lat': 44.4100, 'lon': 26.1300, 'name': 'Titan'},
            'colentina': {'lat': 44.4450, 'lon': 26.1400, 'name': 'Colentina'},
            
            # South
            'piata_sudului': {'lat': 44.4100, 'lon': 26.0950, 'name': 'Piața Sudului'},
            'berceni': {'lat': 44.3950, 'lon': 26.1050, 'name': 'Berceni'},
            'progresul': {'lat': 44.4020, 'lon': 26.0850, 'name': 'Progresul'},
            
            # Outer ring
            'pipera': {'lat': 44.4850, 'lon': 26.1300, 'name': 'Pipera'},
            'baneasa': {'lat': 44.4780, 'lon': 26.0750, 'name': 'Băneasa'},
        }
    
    def _get_bucharest_roads(self) -> List[Tuple]:
        """
        Major road connections: (from, to, type)
        Simplified network of main arteries.
        """
        return [
            # North-South main axis (Kiseleff - Unirii - Sud)
            ('baneasa', 'herastrau', 'highway'),
            ('herastrau', 'aviatorilor', 'primary'),
            ('aviatorilor', 'victoriei', 'primary'),
            ('victoriei', 'romana', 'primary'),
            ('romana', 'universitate', 'primary'),
            ('universitate', 'unirii', 'primary'),
            ('unirii', 'piata_sudului', 'primary'),
            ('piata_sudului', 'berceni', 'secondary'),
            
            # West-East axis (Cotroceni - Centru - Pantelimon)
            ('militari', 'drumul_taberei', 'secondary'),
            ('drumul_taberei', 'cotroceni', 'primary'),
            ('cotroceni', 'cismigiu', 'primary'),
            ('cismigiu', 'universitate', 'primary'),
            ('universitate', 'obor', 'primary'),
            ('obor', 'colentina', 'primary'),
            ('colentina', 'pantelimon', 'secondary'),
            
            # Inner ring (centura mica)
            ('victoriei', 'cismigiu', 'secondary'),
            ('cismigiu', 'progresul', 'secondary'),
            ('progresul', 'piata_sudului', 'secondary'),
            ('piata_sudului', 'titan', 'secondary'),
            ('titan', 'obor', 'secondary'),
            ('obor', 'romana', 'secondary'),
            
            # Diagonal connections
            ('unirii', 'titan', 'primary'),
            ('unirii', 'progresul', 'secondary'),
            ('romana', 'obor', 'primary'),
            ('victoriei', 'aviatorilor', 'primary'),
            
            # North connections
            ('aviatorilor', 'pipera', 'primary'),
            ('pipera', 'colentina', 'primary'),
            ('baneasa', 'pipera', 'highway'),
            
            # Residential shortcuts
            ('cotroceni', 'unirii', 'residential'),
            ('progresul', 'berceni', 'residential'),
            ('colentina', 'titan', 'residential'),
        ]
    
    def populate_pollution(self, pollution_data: List[Dict]):
        """
        Assign pollution to nearest intersections.
        """
        print("Assigning pollution to intersections...")
        
        for data_point in pollution_data:
            # Find nearest intersection
            min_dist = float('inf')
            nearest_id = None
            
            for int_id, node in self.nodes.items():
                dist = utils.haversine_distance(
                    data_point['lat'], data_point['lon'],
                    node['lat'], node['lon']
                )
                if dist < min_dist:
                    min_dist = dist
                    nearest_id = int_id
            
            # Assign pollution
            if nearest_id and min_dist < 1.0:  # Within 1km
                self.nodes[nearest_id]['pollution'] = {
                    'pm10': data_point.get('pm10', 0),
                    'pm25': data_point.get('pm25', data_point.get('pm2_5', 0)),
                    'no2': data_point.get('no2', 0)
                }
                self.nodes[nearest_id]['has_data'] = True
        
        # Interpolate missing
        self._interpolate_missing()
        
        print(f"Assigned pollution to {sum(1 for n in self.nodes.values() if n['has_data'])} intersections")
    
    def _interpolate_missing(self):
        """IDW interpolation for intersections without data."""
        nodes_with_data = [
            (id, node) for id, node in self.nodes.items() 
            if node['has_data']
        ]
        
        if not nodes_with_data:
            return
        
        for int_id, node in self.nodes.items():
            if node['has_data']:
                continue
            
            # Find 3 nearest with data
            distances = []
            for data_id, data_node in nodes_with_data:
                dist = utils.haversine_distance(
                    node['lat'], node['lon'],
                    data_node['lat'], data_node['lon']
                )
                distances.append((dist, data_node))
            
            distances.sort(key=lambda x: x[0])
            nearest = distances[:3]
            
            # IDW
            total_weight = 0
            weighted_pollution = {'pm10': 0, 'pm25': 0, 'no2': 0}
            
            for dist, neighbor in nearest:
                if dist < 0.001:
                    node['pollution'] = neighbor['pollution'].copy()
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
                node['pollution'] = weighted_pollution
    
    def get_edge_cost(self, from_id: str, to_id: str, road_type: str = 'primary') -> float:
        """
        Calculate edge cost considering:
        - Distance
        - Pollution (average of endpoints)
        - Road type (speed limit, preference)
        """
        from_node = self.nodes[from_id]
        to_node = self.nodes[to_id]
        
        # Distance
        dist = utils.haversine_distance(
            from_node['lat'], from_node['lon'],
            to_node['lat'], to_node['lon']
        )
        
        # Pollution
        from_pollution = utils.calculate_pollution_score(**from_node['pollution'])
        to_pollution = utils.calculate_pollution_score(**to_node['pollution'])
        avg_pollution = (from_pollution + to_pollution) / 2
        
        # Road type factor
        road_info = self.road_types.get(road_type, self.road_types['secondary'])
        road_penalty = 2.0 - road_info['preference']  # Lower preference = higher penalty
        
        # Combined cost
        # Cost = alpha * pollution + (1-alpha) * (distance * road_penalty)
        cost = self.alpha * avg_pollution + (1 - self.alpha) * dist * road_penalty
        
        return cost
    
    def get_neighbors(self, node_id: str) -> List[str]:
        """Get neighbor intersections."""
        return [neighbor_id for neighbor_id, _ in self.edges.get(node_id, [])]
    
    def get_neighbor_with_road_type(self, node_id: str, neighbor_id: str) -> str:
        """Get road type between two intersections."""
        for n_id, road_type in self.edges.get(node_id, []):
            if n_id == neighbor_id:
                return road_type
        return 'secondary'  # Default
