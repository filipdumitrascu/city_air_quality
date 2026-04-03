"""
Forecast Service Client for Routing Service

Requests pollution predictions for grid points that lack sensor data.
"""

import httpx
import logging
from typing import List, Dict, Tuple, Set

import sys
import os

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from config import get_config

logger = logging.getLogger(__name__)


class ForecastClient:
    """Client for requesting pollution predictions from Forecast Service."""
    
    def __init__(self):
        self.config = get_config()
        self.forecast_url = self.config["forecast_service_url"]
        self.enabled = self.config["enable_forecasting"]
        self.grid_resolution = self.config["grid_resolution"]
    
    async def fill_gaps(
        self,
        existing_coords: Set[Tuple[float, float]],
        route_bounds: Dict[str, float],
    ) -> List[Dict]:
        """
        Request predictions for grid points not covered by existing data.
        
        Args:
            existing_coords: Set of (lat, lon) tuples that have sensor data
            route_bounds: Dict with lat_min, lat_max, lon_min, lon_max
        
        Returns:
            List of predictions as dicts with lat, lon, pm10, pm2_5, no2, co
        """
        if not self.enabled:
            logger.debug("Forecasting disabled")
            return []
        
        # Generate grid points within route bounds
        gap_points = []
        lat = route_bounds["lat_min"]
        while lat <= route_bounds["lat_max"]:
            lon = route_bounds["lon_min"]
            while lon <= route_bounds["lon_max"]:
                grid_lat = round(lat / self.grid_resolution) * self.grid_resolution
                grid_lon = round(lon / self.grid_resolution) * self.grid_resolution
                grid_point = (round(grid_lat, 6), round(grid_lon, 6))
                
                if grid_point not in existing_coords:
                    gap_points.append({"lat": grid_point[0], "lon": grid_point[1]})
                
                lon += self.grid_resolution
            lat += self.grid_resolution
        
        if not gap_points:
            logger.debug("No gaps to fill - all grid points have data")
            return []
        
        logger.info(f"Requesting predictions for {len(gap_points)} gap points")
        
        # Limit to avoid overwhelming forecast service
        if len(gap_points) > 200:
            logger.warning(f"Too many gaps ({len(gap_points)}), limiting to 200")
            gap_points = gap_points[:200]
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.forecast_url}/predict",
                    json={
                        "points": gap_points,
                        "insert_to_db": True  # Save predictions for future queries
                    }
                )
                
                if response.status_code != 200:
                    logger.warning(f"Forecast service error: {response.status_code}")
                    return []
                
                data = response.json()
                predictions = data.get("predictions", [])
                
                logger.info(f"Received {len(predictions)} predictions from forecast service")
                return predictions
                
        except httpx.ConnectError:
            logger.warning("Forecast service not available")
            return []
        except Exception as e:
            logger.warning(f"Forecast request failed: {e}")
            return []
    
    async def predict_for_route(
        self,
        start: Tuple[float, float],
        goal: Tuple[float, float],
        existing_coords: Set[Tuple[float, float]],
        buffer_factor: float = 0.3
    ) -> List[Dict]:
        """
        Request predictions along a route corridor.
        
        Creates a bounding box around the route and fills gaps.
        """
        lat_min = min(start[0], goal[0]) - buffer_factor * self.grid_resolution * 10
        lat_max = max(start[0], goal[0]) + buffer_factor * self.grid_resolution * 10
        lon_min = min(start[1], goal[1]) - buffer_factor * self.grid_resolution * 10
        lon_max = max(start[1], goal[1]) + buffer_factor * self.grid_resolution * 10
        
        return await self.fill_gaps(
            existing_coords=existing_coords,
            route_bounds={
                "lat_min": lat_min,
                "lat_max": lat_max,
                "lon_min": lon_min,
                "lon_max": lon_max
            }
        )
    
    async def check_health(self) -> bool:
        """Check if forecast service is available and has model loaded."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.forecast_url}/health")
                if response.status_code == 200:
                    data = response.json()
                    return data.get("model_loaded", False)
        except:
            pass
        return False
