import heapq
import logging
import math
from typing import List, Tuple, Optional, Dict
from .graph_builder import PollutionGraph
from .utils import get_heuristic

logger = logging.getLogger(__name__)

class AStarPathfinder:
    """A* pathfinding algorithm for pollution-aware routing"""
    
    def __init__(self, graph: PollutionGraph, heuristic: str = "haversine"):
        """
        Initialize pathfinder with graph and heuristic.
        
        Args:
            graph: PollutionGraph with nodes and edges
            heuristic: Heuristic function name 
                       ('haversine', 'euclidean', 'manhattan', 'diagonal', 'octile')
        """
        self.graph = graph
        self.nodes_evaluated = 0
        self.heuristic_name = heuristic
        self.heuristic_func = get_heuristic(heuristic)
        logger.info(f"Pathfinder initialized with heuristic: {heuristic}")
    
    def find_path(
        self,
        start: Tuple[float, float],
        goal: Tuple[float, float]
    ) -> Optional[List[Tuple[float, float]]]:
        """
        Find optimal path from start to goal using A* algorithm
        
        Args:
            start: (lat, lon) start coordinate
            goal: (lat, lon) goal coordinate
        
        Returns:
            List of (lat, lon) waypoints or None if no path found
        """
        logger.info(f"Finding path from {start} to {goal} using {self.heuristic_name} heuristic")
        
        # Snap to nearest graph nodes
        start_node = self.graph.get_nearest_node(start[0], start[1])
        goal_node = self.graph.get_nearest_node(goal[0], goal[1])
        
        logger.info(f"Snapped to: {start_node} -> {goal_node}")
        
        # Priority queue: (f_score, node)
        open_set = [(0, start_node)]
        
        # Track came_from for path reconstruction
        came_from: Dict[Tuple[float, float], Tuple[float, float]] = {}
        
        # g_score: cost from start to node
        g_score: Dict[Tuple[float, float], float] = {start_node: 0}
        
        # f_score: g_score + heuristic
        f_score: Dict[Tuple[float, float], float] = {
            start_node: self._heuristic(start_node, goal_node)
        }
        
        self.nodes_evaluated = 0
        
        while open_set:
            self.nodes_evaluated += 1
            
            # Get node with lowest f_score
            current_f, current = heapq.heappop(open_set)
            
            # Goal reached
            if current == goal_node:
                logger.info(f"Path found! Evaluated {self.nodes_evaluated} nodes with {self.heuristic_name}")
                return self._reconstruct_path(came_from, current)
            
            # Explore neighbors
            for neighbor, weight, pollution in self.graph.get_neighbors(current):
                tentative_g = g_score[current] + weight
                
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    # Better path found
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score[neighbor] = tentative_g + self._heuristic(neighbor, goal_node)
                    
                    # Add to open set
                    heapq.heappush(open_set, (f_score[neighbor], neighbor))
        
        logger.warning(f"No path found after evaluating {self.nodes_evaluated} nodes")
        return None
    
    def _heuristic(self, node: Tuple[float, float], goal: Tuple[float, float]) -> float:
        """
        Heuristic function for A* - uses configured heuristic
        
        Args:
            node: Current node
            goal: Goal node
        
        Returns:
            Estimated cost to goal
        """
        return self.heuristic_func(node, goal)
    
    def _reconstruct_path(
        self,
        came_from: Dict[Tuple[float, float], Tuple[float, float]],
        current: Tuple[float, float]
    ) -> List[Tuple[float, float]]:
        """
        Reconstruct path from came_from chain
        
        Args:
            came_from: Dictionary of node -> previous node
            current: Goal node
        
        Returns:
            List of waypoints from start to goal
        """
        path = [current]
        
        while current in came_from:
            current = came_from[current]
            path.append(current)
        
        path.reverse()
        return path
