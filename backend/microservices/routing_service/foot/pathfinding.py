import heapq
import logging
from typing import List, Tuple, Optional, Dict

from foot.graph_builder import PollutionGraph
from foot.utils import get_heuristic

logger = logging.getLogger(__name__)

class AStarPathfinder:
    """A* pathfinding on pollution graph"""
    
    def __init__(self, graph: PollutionGraph, heuristic: str = "haversine"):
        """
        Initialize pathfinder.
        
        Args:
            graph: PollutionGraph with nodes and edges
            heuristic: One of 'haversine', 'euclidean', 'manhattan', 'diagonal', 'octile'
        """
        self.graph = graph
        self.heuristic_name = heuristic
        self.heuristic_func = get_heuristic(heuristic)
        self.nodes_evaluated = 0
    
    def find_path(
        self,
        start: Tuple[float, float],
        goal: Tuple[float, float]
    ) -> Optional[List[Tuple[float, float]]]:
        """
        Find optimal path from start to goal.
        
        Returns:
            List of (lat, lon) waypoints or None if no path found
        """
        logger.info(f"Finding path: {start} -> {goal}, heuristic={self.heuristic_name}")
        
        # Snap to nearest graph nodes
        start_node = self.graph.get_nearest_node(start[0], start[1])
        goal_node = self.graph.get_nearest_node(goal[0], goal[1])
        
        logger.info(f"Snapped: {start_node} -> {goal_node}")
        
        # Priority queue: (f_score, node)
        open_set = [(0.0, start_node)]
        
        # Track path
        came_from: Dict[Tuple[float, float], Tuple[float, float]] = {}
        
        # g_score: actual cost from start
        g_score: Dict[Tuple[float, float], float] = {start_node: 0.0}
        
        # f_score: g_score + heuristic
        f_score: Dict[Tuple[float, float], float] = {
            start_node: self.heuristic_func(start_node, goal_node)
        }
        
        self.nodes_evaluated = 0
        visited = set()
        
        while open_set:
            _, current = heapq.heappop(open_set)
            
            if current in visited:
                continue
            
            visited.add(current)
            self.nodes_evaluated += 1
            
            # Goal reached
            if current == goal_node:
                path = self._reconstruct_path(came_from, current)
                logger.info(f"Path found: {len(path)} waypoints, {self.nodes_evaluated} nodes evaluated")
                return path
            
            # Explore neighbors
            for neighbor, weight in self.graph.get_neighbors(current):
                if neighbor in visited:
                    continue
                
                tentative_g = g_score[current] + weight
                
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f = tentative_g + self.heuristic_func(neighbor, goal_node)
                    f_score[neighbor] = f
                    heapq.heappush(open_set, (f, neighbor))
        
        logger.warning(f"No path found after {self.nodes_evaluated} nodes")
        return None
    
    def _reconstruct_path(
        self,
        came_from: Dict[Tuple[float, float], Tuple[float, float]],
        current: Tuple[float, float]
    ) -> List[Tuple[float, float]]:
        """Reconstruct path from came_from chain"""
        path = [current]
        
        while current in came_from:
            current = came_from[current]
            path.append(current)
        
        path.reverse()
        return path
