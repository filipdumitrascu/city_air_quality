import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.patches import Rectangle
import numpy as np
from typing import Dict, List, Tuple

class PathfindingVisualizer:
    """
    Visualization for pathfinding algorithms.
    Takes algorithm as parameter.
    """
    
    def __init__(self, graph):
        self.graph = graph
    
    def visualize_path(self, 
                      algorithm,
                      start: Tuple,
                      goal: Tuple,
                      output_file: str = None,
                      show: bool = True):
        """
        Static visualization of found path.
        """
        result = algorithm.find_path(start, goal)
        
        if 'error' in result:
            print(f"Error: {result['error']}")
            return
        
        fig, ax = plt.subplots(figsize=(12, 10))
        
        # Draw grid (sample for performance)
        self._draw_grid(ax)
        
        # Draw visited nodes
        visited_cells = [v['cell'] for v in result['visited_nodes']]
        if visited_cells:
            visited_x = [c[1] for c in visited_cells]
            visited_y = [c[0] for c in visited_cells]
            ax.scatter(visited_x, visited_y, c='lightblue', 
                      s=5, alpha=0.5, label='Visited')
        
        # Draw final path
        path = result['path']
        if path:
            path_x = [c[1] for c in path]
            path_y = [c[0] for c in path]
            ax.plot(path_x, path_y, 'r-', linewidth=2, label='Final path')
        
        # Start and goal
        ax.scatter([start[1]], [start[0]], c='green', 
                  s=100, marker='o', label='Start', zorder=5)
        ax.scatter([goal[1]], [goal[0]], c='red', 
                  s=100, marker='*', label='Goal', zorder=5)
        
        # Title with statistics
        stats = algorithm.get_stats()
        title = f"{algorithm.__class__.__name__}\n"
        title += f"Nodes explored: {stats.get('nodes_explored', 0)}, "
        title += f"Path length: {stats.get('path_length', 0)}"
        if 'total_cost' in stats:
            title += f", Cost: {stats['total_cost']:.2f}"
        
        ax.set_title(title)
        ax.legend()
        ax.set_xlabel('Longitude (grid)')
        ax.set_ylabel('Latitude (grid)')
        
        if output_file:
            plt.savefig(output_file, dpi=150, bbox_inches='tight')
            print(f"Saved: {output_file}")
        
        if show:
            plt.show()
        else:
            plt.close()
    
    def animate_search(self,
                      algorithm,
                      start: Tuple,
                      goal: Tuple,
                      output_file: str = 'search_animation.mp4',
                      interval: int = 50):
        """
        Animation showing how algorithm explores the graph.
        """
        result = algorithm.find_path(start, goal)
        
        if 'error' in result:
            print(f"Error: {result['error']}")
            return
        
        visited_nodes = result['visited_nodes']
        final_path = result['path']
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
        
        def animate(frame):
            ax1.clear()
            ax2.clear()
            
            # Graph 1: Grid exploration
            self._draw_grid(ax1)
            
            # Visited nodes up to current frame
            current_visited = visited_nodes[:frame+1]
            if current_visited:
                visited_x = [v['cell'][1] for v in current_visited]
                visited_y = [v['cell'][0] for v in current_visited]
                
                # Color by exploration order
                colors = range(len(current_visited))
                ax1.scatter(visited_x, visited_y, c=colors, 
                          cmap='viridis', s=10, alpha=0.7)
            
            # Start and goal
            ax1.scatter([start[1]], [start[0]], c='green', 
                       s=100, marker='o', label='Start', zorder=5)
            ax1.scatter([goal[1]], [goal[0]], c='red', 
                       s=100, marker='*', label='Goal', zorder=5)
            
            # Final path if reached
            if frame == len(visited_nodes) - 1 and final_path:
                path_x = [c[1] for c in final_path]
                path_y = [c[0] for c in final_path]
                ax1.plot(path_x, path_y, 'r-', linewidth=2, label='Path')
            
            ax1.set_title(f'{algorithm.__class__.__name__} - Frame {frame+1}/{len(visited_nodes)}')
            ax1.legend()
            ax1.set_xlabel('Longitude (grid)')
            ax1.set_ylabel('Latitude (grid)')
            
            # Graph 2: Statistics
            if current_visited and 'g_score' in current_visited[0]:
                g_scores = [v['g_score'] for v in current_visited]
                f_scores = [v['f_score'] for v in current_visited]
                
                ax2.plot(g_scores, label='g(n)', color='blue')
                ax2.plot(f_scores, label='f(n)', color='red')
                ax2.legend()
                ax2.set_xlabel('Exploration order')
                ax2.set_ylabel('Cost')
                ax2.set_title('Cost evolution')
            
        anim = animation.FuncAnimation(
            fig, animate, frames=len(visited_nodes),
            interval=interval, repeat=False)
        
        anim.save(output_file, writer='ffmpeg', fps=20)
        plt.close()
        print(f"Animation saved: {output_file}")
    
    def compare_algorithms(self,
                          algorithms: List,
                          start: Tuple,
                          goal: Tuple,
                          output_file: str = None):
        """
        Compare multiple algorithms on same graph.
        """
        results = []
        for algo in algorithms:
            result = algo.find_path(start, goal)
            if 'error' not in result:
                results.append((algo.__class__.__name__, result, algo.get_stats()))
            else:
                print(f"{algo.__class__.__name__} failed: {result['error']}")
        
        if not results:
            print("No algorithm found a path")
            return
        
        # Create subplots
        n_results = len(results)
        fig, axes = plt.subplots(1, n_results, figsize=(6*n_results, 5))
        
        # Handle single algorithm case
        if n_results == 1:
            axes = [axes]
        
        for idx, (name, result, stats) in enumerate(results):
            ax = axes[idx]
            self._draw_grid(ax)
            
            # Visited nodes
            visited = [v['cell'] for v in result['visited_nodes']]
            if visited:
                v_x = [c[1] for c in visited]
                v_y = [c[0] for c in visited]
                ax.scatter(v_x, v_y, c='lightblue', s=5, alpha=0.5)
            
            # Path - FIX HERE
            path = result['path']
            if path:  # Check if path exists and is not empty
                path_x = [c[1] for c in path]
                path_y = [c[0] for c in path]
                ax.plot(path_x, path_y, 'r-', linewidth=2)
            
            # Start and goal
            ax.scatter([start[1]], [start[0]], c='green', s=100, marker='o')
            ax.scatter([goal[1]], [goal[0]], c='red', s=100, marker='*')
            
            # Title
            title = f"{name}\n"
            title += f"Explored: {stats['nodes_explored']}\n"
            title += f"Path length: {stats['path_length']}"
            if 'total_cost' in stats:
                title += f"\nCost: {stats['total_cost']:.2f}"
            
            ax.set_title(title)
            ax.set_xlabel('Longitude (grid)')
            ax.set_ylabel('Latitude (grid)')
        
        plt.tight_layout()
        
        if output_file:
            plt.savefig(output_file, dpi=150, bbox_inches='tight')
            print(f"Saved: {output_file}")
        
        plt.show()
    
    def _draw_grid(self, ax):
        """Draw background grid (sampled for performance)."""
        # Sample only subset of nodes for visualization
        sample_cells = list(self.graph.nodes.keys())[::20]  # Every 20th node
        
        for cell in sample_cells:
            node = self.graph.nodes[cell]
            
            # Calculate pollution score for coloring
            pollution_score = (
                node['pollution']['pm10'] / 50.0 * 0.4 +
                node['pollution']['pm25'] / 25.0 * 0.4 +
                node['pollution']['no2'] / 40.0 * 0.2
            )
            
            # Color: green (low) to red (high)
            color = plt.cm.RdYlGn_r(min(pollution_score, 1.0))
            
            # Draw cell
            ax.add_patch(Rectangle(
                (cell[1]-0.5, cell[0]-0.5), 1, 1,
                facecolor=color, alpha=0.2, edgecolor='none'
            ))
