from abc import ABC, abstractmethod
import heapq
from typing import Dict, List, Tuple, Optional, Callable
from collections import deque

class PathfindingAlgorithm(ABC):
    """
    Abstract base class for pathfinding algorithms.
    All algorithms inherit from this.
    """
    
    def __init__(self, graph):
        self.graph = graph
        self.visited_nodes = []
        self.stats = {}
    
    @abstractmethod
    def find_path(self, start: Tuple, goal: Tuple) -> Dict:
        """Find path from start to goal."""
        pass
    
    def _reconstruct_path(self, came_from: Dict, current: Tuple) -> List[Tuple]:
        """
        Reconstruct path from came_from dictionary.
        Fixed: Handle case where start has came_from[start] = None
        """
        path = [current]
        while current in came_from and came_from[current] is not None:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path
    
    def get_stats(self) -> Dict:
        """Return algorithm statistics."""
        return self.stats


class AStarAlgorithm(PathfindingAlgorithm):
    """
    A* algorithm with configurable heuristic.
    Finds optimal path using heuristic to guide search.
    """
    
    def __init__(self, graph, heuristic_fn: Callable = None):
        super().__init__(graph)
        self.heuristic_fn = heuristic_fn
        
        # Default to Haversine heuristic
        if self.heuristic_fn is None:
            import utils
            self.heuristic_fn = utils.haversine_heuristic
    
    def find_path(self, start: Tuple, goal: Tuple) -> Dict:
        """
        Standard A* pathfinding.
        Uses f(n) = g(n) + h(n) where:
        - g(n) = actual cost from start to n
        - h(n) = estimated cost from n to goal (heuristic)
        """
        if start not in self.graph.nodes or goal not in self.graph.nodes:
            return {'error': 'Start or goal not in graph'}
        
        # Priority queue: (f_score, counter, cell, g_score)
        counter = 0
        open_set = []
        heapq.heappush(open_set, (
            self._heuristic(start, goal),
            counter,
            start,
            0
        ))
        
        came_from = {}
        g_score = {start: 0}
        closed_set = set()
        self.visited_nodes = []
        nodes_explored = 0
        
        while open_set:
            f, _, current, current_g = heapq.heappop(open_set)
            
            if current in closed_set:
                continue
            
            closed_set.add(current)
            nodes_explored += 1
            
            # For visualization
            self.visited_nodes.append({
                'cell': current,
                'g_score': current_g,
                'f_score': f
            })
            
            # Goal check
            if current == goal:
                path = self._reconstruct_path(came_from, current)
                
                self.stats = {
                    'nodes_explored': nodes_explored,
                    'path_length': len(path),
                    'total_cost': current_g
                }
                
                return {
                    'path': path,
                    'cost': current_g,
                    'visited_nodes': self.visited_nodes,
                    'stats': self.stats
                }
            
            # Expand neighbors
            for neighbor in self.graph.get_neighbors(current):
                if neighbor in closed_set:
                    continue
                
                tentative_g = (current_g + 
                             self.graph.get_edge_cost(current, neighbor))
                
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score = tentative_g + self._heuristic(neighbor, goal)
                    
                    counter += 1
                    heapq.heappush(open_set, (
                        f_score,
                        counter,
                        neighbor,
                        tentative_g
                    ))
        
        return {'error': 'No path found'}
    
    def _heuristic(self, cell1: Tuple, cell2: Tuple) -> float:
        """Apply heuristic function."""
        return self.heuristic_fn(self.graph, cell1, cell2)


class DijkstraAlgorithm(PathfindingAlgorithm):
    """
    Dijkstra algorithm (A* with zero heuristic).
    Guarantees optimal path but explores more nodes.
    """
    
    def find_path(self, start: Tuple, goal: Tuple) -> Dict:
        if start not in self.graph.nodes or goal not in self.graph.nodes:
            return {'error': 'Start or goal not in graph'}
        
        counter = 0
        open_set = []
        heapq.heappush(open_set, (0, counter, start))
        
        came_from = {}
        cost = {start: 0}
        self.visited_nodes = []
        nodes_explored = 0
        
        while open_set:
            current_cost, _, current = heapq.heappop(open_set)
            
            nodes_explored += 1
            self.visited_nodes.append({
                'cell': current,
                'cost': current_cost
            })
            
            if current == goal:
                path = self._reconstruct_path(came_from, current)
                
                self.stats = {
                    'nodes_explored': nodes_explored,
                    'path_length': len(path),
                    'total_cost': current_cost
                }
                
                return {
                    'path': path,
                    'cost': current_cost,
                    'visited_nodes': self.visited_nodes,
                    'stats': self.stats
                }
            
            for neighbor in self.graph.get_neighbors(current):
                new_cost = cost[current] + self.graph.get_edge_cost(current, neighbor)
                
                if neighbor not in cost or new_cost < cost[neighbor]:
                    cost[neighbor] = new_cost
                    came_from[neighbor] = current
                    counter += 1
                    heapq.heappush(open_set, (new_cost, counter, neighbor))
        
        return {'error': 'No path found'}


class BFSAlgorithm(PathfindingAlgorithm):
    """
    Breadth-First Search (ignores costs, only distance in nodes).
    Finds shortest path in terms of number of steps, not cost.
    """
    
    def find_path(self, start: Tuple, goal: Tuple) -> Dict:
        if start not in self.graph.nodes or goal not in self.graph.nodes:
            return {'error': 'Start or goal not in graph'}
        
        queue = deque([start])
        came_from = {start: None}  # IMPORTANT: start has no parent
        self.visited_nodes = []
        nodes_explored = 0
        
        while queue:
            current = queue.popleft()
            nodes_explored += 1
            
            self.visited_nodes.append({
                'cell': current
            })
            
            if current == goal:
                path = self._reconstruct_path(came_from, current)
                
                self.stats = {
                    'nodes_explored': nodes_explored,
                    'path_length': len(path)
                    # BFS doesn't track cost
                }
                
                return {
                    'path': path,
                    'visited_nodes': self.visited_nodes,
                    'stats': self.stats
                }
            
            for neighbor in self.graph.get_neighbors(current):
                if neighbor not in came_from:
                    came_from[neighbor] = current
                    queue.append(neighbor)
        
        return {'error': 'No path found'}
