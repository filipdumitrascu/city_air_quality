import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.animation as animation
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
import numpy as np
from typing import List, Tuple, Dict
import os

class BucharestMapVisualizer:
    """
    Visualization overlaid on real Bucharest map image.
    """
    
    def __init__(self, graph, map_image_path=None):
        self.graph = graph
        
        # Bucharest bounding box (matches our graph)
        self.bbox = {
            'lat_min': 44.35,
            'lat_max': 44.50,
            'lon_min': 25.95,
            'lon_max': 26.20
        }
        
        # Try to load map image
        self.map_image = None
        if map_image_path and os.path.exists(map_image_path):
            self.map_image = plt.imread(map_image_path)
            print(f"Loaded map image: {map_image_path}")
        else:
            print("No map image found, using plain background")
    
    def plot_algorithm_on_map(self, algorithm, start: Tuple, goal: Tuple,
                             title: str = "Pathfinding on Bucharest",
                             output_file: str = None, show: bool = True):
        """
        Plot algorithm result overlaid on real Bucharest map.
        """
        result = algorithm.find_path(start, goal)
        
        if 'error' in result:
            print(f"Error: {result['error']}")
            return
        
        fig, ax = plt.subplots(figsize=(16, 12))
        
        # 1. Show base map if available
        if self.map_image is not None:
            ax.imshow(self.map_image, extent=[
                self.bbox['lon_min'], self.bbox['lon_max'],
                self.bbox['lat_min'], self.bbox['lat_max']
            ], aspect='auto', alpha=0.7, zorder=0)
        else:
            ax.set_facecolor('#e8e8e8')
            self._draw_grid_background(ax)
        
        # 2. Draw pollution heatmap (semi-transparent)
        self._draw_pollution_overlay(ax, alpha=0.3)
        
        # 3. Draw explored nodes
        visited = result['visited_nodes']
        if visited:
            visited_coords = [self._cell_to_coords(v['cell']) for v in visited]
            v_lat = [c[0] for c in visited_coords]
            v_lon = [c[1] for c in visited_coords]
            ax.scatter(v_lon, v_lat, c='cyan', s=8, alpha=0.4, 
                      label=f'Explored ({len(visited)} nodes)', zorder=3,
                      edgecolors='blue', linewidths=0.3)
        
        # 4. Draw final path (thick highlighted line)
        path = result['path']
        if path:
            path_coords = [self._cell_to_coords(c) for c in path]
            p_lat = [c[0] for c in path_coords]
            p_lon = [c[1] for c in path_coords]
            
            # Draw path with glow effect
            ax.plot(p_lon, p_lat, 'yellow', linewidth=8, alpha=0.3, 
                   solid_capstyle='round', zorder=4)
            ax.plot(p_lon, p_lat, 'gold', linewidth=4, 
                   label='Optimal Route', solid_capstyle='round', zorder=5)
        
        # 5. Mark start and goal
        start_coords = self._cell_to_coords(start)
        goal_coords = self._cell_to_coords(goal)
        
        ax.scatter([start_coords[1]], [start_coords[0]], c='lime', s=500, 
                  marker='o', label='START', zorder=6, 
                  edgecolors='darkgreen', linewidths=3)
        ax.scatter([goal_coords[1]], [goal_coords[0]], c='red', s=600, 
                  marker='*', label='GOAL', zorder=6,
                  edgecolors='darkred', linewidths=3)
        
        # Add text annotations
        ax.text(start_coords[1], start_coords[0] + 0.01, 'START',
               ha='center', fontsize=11, fontweight='bold', color='darkgreen',
               bbox=dict(boxstyle='round,pad=0.4', facecolor='white', alpha=0.9),
               zorder=7)
        ax.text(goal_coords[1], goal_coords[0] - 0.01, 'GOAL',
               ha='center', fontsize=11, fontweight='bold', color='darkred',
               bbox=dict(boxstyle='round,pad=0.4', facecolor='white', alpha=0.9),
               zorder=7)
        
        # 6. Add statistics box
        stats = algorithm.get_stats()
        stats_text = (
            f"{algorithm.__class__.__name__}\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"Nodes explored: {stats['nodes_explored']}\n"
            f"Path length: {stats['path_length']} nodes\n"
        )
        if 'total_cost' in stats:
            stats_text += f"Total cost: {stats['total_cost']:.4f}\n"
        
        # Calculate distance
        if path:
            import utils
            total_dist = 0
            for i in range(1, len(path)):
                c1 = self._cell_to_coords(path[i-1])
                c2 = self._cell_to_coords(path[i])
                total_dist += utils.haversine_distance(c1[0], c1[1], c2[0], c2[1])
            stats_text += f"Distance: {total_dist:.2f} km"
        
        ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
               fontsize=10, verticalalignment='top', family='monospace',
               bbox=dict(boxstyle='round', facecolor='white', alpha=0.95,
                        edgecolor='black', linewidth=2), zorder=8)
        
        # 7. Add pollution scale
        self._add_pollution_legend(ax)
        
        # Styling
        ax.set_xlim(self.bbox['lon_min'], self.bbox['lon_max'])
        ax.set_ylim(self.bbox['lat_min'], self.bbox['lat_max'])
        ax.set_xlabel('Longitude', fontsize=12, fontweight='bold')
        ax.set_ylabel('Latitude', fontsize=12, fontweight='bold')
        ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
        ax.legend(loc='upper right', fontsize=10, framealpha=0.95,
                 edgecolor='black', fancybox=True)
        ax.grid(True, alpha=0.2, linestyle=':', linewidth=0.5)
        
        plt.tight_layout()
        
        if output_file:
            save_path = os.path.join('..', 'images', output_file)
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f" Saved: {save_path}")
        
        if show:
            plt.show()
        else:
            plt.close()
    
    def animate_algorithm(self, algorithm, start: Tuple, goal: Tuple,
                         output_file: str = 'algorithm_animation.mp4',
                         interval: int = 50, show_cost: bool = True):
        """
        Create animation showing algorithm exploration on real map.
        """
        print(f"Running {algorithm.__class__.__name__}...")
        result = algorithm.find_path(start, goal)
        
        if 'error' in result:
            print(f"Error: {result['error']}")
            return
        
        visited_nodes = result['visited_nodes']
        final_path = result['path']
        
        print(f"Creating animation with {len(visited_nodes)} frames...")
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 9))
        
        # Get coordinates
        start_coords = self._cell_to_coords(start)
        goal_coords = self._cell_to_coords(goal)
        
        def animate_frame(frame):
            ax1.clear()
            ax2.clear()
            
            # LEFT: Map with exploration
            if self.map_image is not None:
                ax1.imshow(self.map_image, extent=[
                    self.bbox['lon_min'], self.bbox['lon_max'],
                    self.bbox['lat_min'], self.bbox['lat_max']
                ], aspect='auto', alpha=0.6, zorder=0)
            else:
                ax1.set_facecolor('#e8e8e8')
            
            # Draw pollution
            self._draw_pollution_overlay(ax1, alpha=0.2)
            
            # Explored nodes up to current frame
            current_visited = visited_nodes[:frame+1]
            if current_visited:
                coords = [self._cell_to_coords(v['cell']) for v in current_visited]
                v_lat = [c[0] for c in coords]
                v_lon = [c[1] for c in coords]
                
                # Color by order
                colors = np.arange(len(current_visited))
                ax1.scatter(v_lon, v_lat, c=colors, cmap='plasma', 
                          s=15, alpha=0.6, zorder=3)
            
            # Current node (large pulsing marker)
            if frame < len(visited_nodes):
                current_cell = visited_nodes[frame]['cell']
                current_coords = self._cell_to_coords(current_cell)
                ax1.scatter([current_coords[1]], [current_coords[0]], 
                          c='cyan', s=200, marker='o', zorder=5,
                          edgecolors='blue', linewidths=3)
            
            # Draw final path if reached goal
            if frame == len(visited_nodes) - 1 and final_path:
                path_coords = [self._cell_to_coords(c) for c in final_path]
                p_lat = [c[0] for c in path_coords]
                p_lon = [c[1] for c in path_coords]
                ax1.plot(p_lon, p_lat, 'yellow', linewidth=6, alpha=0.5, zorder=4)
                ax1.plot(p_lon, p_lat, 'gold', linewidth=3, zorder=5)
            
            # Start and goal
            ax1.scatter([start_coords[1]], [start_coords[0]], c='lime', 
                       s=400, marker='o', zorder=6, edgecolors='darkgreen', linewidths=3)
            ax1.scatter([goal_coords[1]], [goal_coords[0]], c='red', 
                       s=500, marker='*', zorder=6, edgecolors='darkred', linewidths=3)
            
            ax1.set_xlim(self.bbox['lon_min'], self.bbox['lon_max'])
            ax1.set_ylim(self.bbox['lat_min'], self.bbox['lat_max'])
            ax1.set_title(f'{algorithm.__class__.__name__} - Frame {frame+1}/{len(visited_nodes)}',
                         fontsize=14, fontweight='bold')
            ax1.set_xlabel('Longitude')
            ax1.set_ylabel('Latitude')
            ax1.grid(True, alpha=0.2)
            
            # RIGHT: Cost evolution graph
            if show_cost and current_visited and 'g_score' in current_visited[0]:
                g_scores = [v['g_score'] for v in current_visited]
                f_scores = [v['f_score'] for v in current_visited]
                
                ax2.plot(g_scores, 'b-', label='g(n) - Actual Cost', linewidth=2)
                ax2.plot(f_scores, 'r-', label='f(n) - Estimated Total', linewidth=2)
                ax2.axhline(y=g_scores[-1], color='g', linestyle='--', 
                           label='Current Cost', alpha=0.7)
                
                ax2.set_xlabel('Exploration Order', fontsize=11)
                ax2.set_ylabel('Cost', fontsize=11)
                ax2.set_title('Cost Evolution', fontsize=13, fontweight='bold')
                ax2.legend(loc='upper left')
                ax2.grid(True, alpha=0.3)
                
                # Show current stats
                stats_text = (
                    f"Nodes explored: {len(current_visited)}\n"
                    f"Current cost: {g_scores[-1]:.4f}"
                )
                ax2.text(0.98, 0.98, stats_text, transform=ax2.transAxes,
                        ha='right', va='top', fontsize=10,
                        bbox=dict(boxstyle='round', facecolor='white', alpha=0.9))
            
            plt.tight_layout()
        
        print("Rendering animation...")
        anim = animation.FuncAnimation(
            fig, animate_frame, frames=len(visited_nodes),
            interval=interval, repeat=False, blit=False)
        
        save_path = os.path.join('..', 'images', output_file)
        anim.save(save_path, writer='ffmpeg', fps=20, dpi=150,
                 metadata={'artist': 'CityAirQ'})
        plt.close()
        
        print(f" Animation saved: {save_path}")
    
    def _cell_to_coords(self, cell: Tuple) -> Tuple[float, float]:
        """Convert grid cell to real coordinates."""
        lat = cell[0] * self.graph.resolution
        lon = cell[1] * self.graph.resolution
        return (lat, lon)
    
    def _draw_pollution_overlay(self, ax, alpha=0.4):
        """Draw pollution heatmap overlay."""
        sample_cells = list(self.graph.nodes.keys())[::8]
        
        for cell in sample_cells:
            node = self.graph.nodes[cell]
            lat, lon = node['lat'], node['lon']
            
            pollution = (
                node['pollution']['pm10'] / 50.0 * 0.4 +
                node['pollution']['pm25'] / 25.0 * 0.4 +
                node['pollution']['no2'] / 40.0 * 0.2
            )
            
            if pollution < 0.3:
                color = (0, 1, 0, alpha * 0.5)  # Green
            elif pollution < 0.7:
                color = (1, 1, 0, alpha * 0.7)  # Yellow
            else:
                color = (1, 0, 0, alpha)  # Red
            
            size = 0.003
            rect = mpatches.Rectangle(
                (lon - size/2, lat - size/2), size, size,
                facecolor=color, edgecolor='none', zorder=1
            )
            ax.add_patch(rect)
    
    def _draw_grid_background(self, ax):
        """Draw simple grid when no map image."""
        for lat in np.arange(self.bbox['lat_min'], self.bbox['lat_max'], 0.02):
            ax.axhline(y=lat, color='gray', alpha=0.2, linewidth=0.5)
        for lon in np.arange(self.bbox['lon_min'], self.bbox['lon_max'], 0.02):
            ax.axvline(x=lon, color='gray', alpha=0.2, linewidth=0.5)
    
    def _add_pollution_legend(self, ax):
        """Add pollution color legend."""
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor='green', alpha=0.6, label='Low pollution'),
            Patch(facecolor='yellow', alpha=0.6, label='Medium pollution'),
            Patch(facecolor='red', alpha=0.6, label='High pollution'),
        ]
        
        ax.add_artist(ax.legend(handles=legend_elements, loc='lower left',
                               title='Pollution Level', framealpha=0.9,
                               fontsize=9))
