import httpx
import logging
import math
import polyline
from typing import List, Dict, Tuple, Optional

import sys
import os

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from config import get_config

logger = logging.getLogger(__name__)


def haversine_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """Distance in km"""
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    
    return R * 2 * math.asin(math.sqrt(a))

def sample_waypoints(path: List[Tuple[float, float]], sample_distance_m: int = 200) -> List[Tuple[float, float]]:
    """Sample waypoints at regular intervals"""
    if len(path) <= 2:
        return path
    
    sample_km = sample_distance_m / 1000.0
    sampled = [path[0]]
    accumulated = 0.0
    
    for i in range(1, len(path)):
        accumulated += haversine_distance(path[i-1], path[i])
        if accumulated >= sample_km:
            sampled.append(path[i])
            accumulated = 0.0
    
    if sampled[-1] != path[-1]:
        sampled.append(path[-1])
    
    return sampled


class GoogleRoutesClient:
    """Client for Google Routes API with pollution scoring"""
    
    def __init__(self):
        self.config = get_config()
        self.api_key = self.config["google_maps_api_key"]
        self.base_url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    
    def is_configured(self) -> bool:
        """Check if API key is set"""
        return bool(self.api_key)
    
    async def get_routes(
        self,
        start: Tuple[float, float],
        goal: Tuple[float, float],
        alternatives: bool = True
    ) -> List[Dict]:
        """
        Get routes from Google Routes API.
        
        Uses DRIVE mode (BICYCLE not supported in Romania).
        """
        if not self.api_key:
            raise ValueError("Google Maps API key not configured")
        
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline"
        }
        
        body = {
            "origin": {
                "location": {"latLng": {"latitude": start[0], "longitude": start[1]}}
            },
            "destination": {
                "location": {"latLng": {"latitude": goal[0], "longitude": goal[1]}}
            },
            "travelMode": "DRIVE",  # BICYCLE not supported in Romania
            "computeAlternativeRoutes": alternatives,
            "routeModifiers": {"avoidTolls": False, "avoidHighways": False},
        }
        
        logger.info(f"Requesting Google Routes: {start} -> {goal}")
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(self.base_url, headers=headers, json=body)
            
            if response.status_code != 200:
                logger.error(f"Google API error: {response.status_code}")
                response.raise_for_status()
            
            data = response.json()
        
        routes = []
        for i, route in enumerate(data.get("routes", [])):
            encoded = route.get("polyline", {}).get("encodedPolyline", "")
            if not encoded:
                continue
            
            path = polyline.decode(encoded)
            duration_s = int(route.get("duration", "0s").replace("s", ""))
            distance_m = route.get("distanceMeters", 0)
            
            routes.append({
                "index": i,
                "path": path,
                "distance_km": distance_m / 1000.0,
                "duration_minutes": duration_s / 60.0,
            })
        
        logger.info(f"Got {len(routes)} routes from Google")
        return routes
    
    async def get_routes_with_pollution(
        self,
        start: Tuple[float, float],
        goal: Tuple[float, float],
        pollution_data: List[Dict],
        alpha: float = 0.5,
        sample_distance_m: int = 200
    ) -> Tuple[Dict, List[Dict]]:
        """
        Get routes and score by pollution.
        
        Returns (best_route, all_routes_with_scores)
        """
        routes = await self.get_routes(start, goal)
        
        if not routes:
            raise ValueError("No routes from Google")
        
        pollution_grid = self._build_pollution_grid(pollution_data)
        
        for route in routes:
            sampled = sample_waypoints(route["path"], sample_distance_m)
            route["sampled_waypoints"] = sampled
            route["pollution"] = self._calculate_pollution_stats(sampled, pollution_grid)
            
            # Score: weighted combination of distance and pollution
            norm_dist = route["distance_km"] / max(r["distance_km"] for r in routes)
            norm_poll = route["pollution"]["avg_aqi"] / 100.0
            route["score"] = (1 - alpha) * norm_dist + alpha * norm_poll
        
        routes.sort(key=lambda r: r["score"])
        
        logger.info(f"Selected route {routes[0]['index']} (score={routes[0]['score']:.3f})")
        return routes[0], routes
    
    def _build_pollution_grid(
        self, 
        pollution_data: List[Dict],
        resolution: float = 0.002
    ) -> Dict[Tuple[float, float], Dict[str, float]]:
        """Build pollution grid from database readings"""
        grid = {}
        
        for reading in pollution_data:
            try:
                if isinstance(reading, dict):
                    lat = float(reading.get("latitude", 0))
                    lon = float(reading.get("longitude", 0))
                    pm10 = reading.get("pm10", -1)
                    pm2_5 = reading.get("pm2_5", -1)
                else:
                    lat = float(reading[3])
                    lon = float(reading[4])
                    pm10 = reading[5] if len(reading) > 5 else -1
                    pm2_5 = reading[6] if len(reading) > 6 else -1
                
                pm10 = float(pm10) if pm10 is not None else -1
                pm2_5 = float(pm2_5) if pm2_5 is not None else -1
                
                grid_point = (
                    round(lat / resolution) * resolution,
                    round(lon / resolution) * resolution
                )
                
                # Calculate AQI from valid values only
                valid = []
                if pm10 >= 0:
                    valid.append(pm10)
                if pm2_5 >= 0:
                    valid.append(pm2_5 * 1.5)
                
                aqi = sum(valid) / len(valid) if valid else 50.0
                
                if grid_point in grid:
                    old = grid[grid_point]
                    grid[grid_point] = {
                        'pm10': (old['pm10'] + pm10) / 2 if pm10 >= 0 and old['pm10'] >= 0 else max(old['pm10'], pm10),
                        'pm2_5': (old['pm2_5'] + pm2_5) / 2 if pm2_5 >= 0 and old['pm2_5'] >= 0 else max(old['pm2_5'], pm2_5),
                        'aqi': (old['aqi'] + aqi) / 2
                    }
                else:
                    grid[grid_point] = {'pm10': pm10, 'pm2_5': pm2_5, 'aqi': aqi}
                    
            except Exception as e:
                logger.warning(f"Skipping reading: {e}")
        
        logger.info(f"Built pollution grid: {len(grid)} cells")
        return grid
    
    def _calculate_pollution_stats(
        self,
        waypoints: List[Tuple[float, float]],
        pollution_grid: Dict[Tuple[float, float], Dict[str, float]],
        resolution: float = 0.002
    ) -> Dict[str, float]:
        """Calculate pollution statistics for waypoints"""
        pm10_vals, pm2_5_vals, aqi_vals = [], [], []
        
        for lat, lon in waypoints:
            grid_point = (
                round(lat / resolution) * resolution,
                round(lon / resolution) * resolution
            )
            
            data = pollution_grid.get(grid_point)
            if not data:
                # Find nearest
                data = self._find_nearest(grid_point, pollution_grid)
            
            if data:
                if data.get('pm10', -1) >= 0:
                    pm10_vals.append(data['pm10'])
                if data.get('pm2_5', -1) >= 0:
                    pm2_5_vals.append(data['pm2_5'])
                aqi_vals.append(data.get('aqi', 50))
            else:
                aqi_vals.append(50)  # Default
        
        return {
            'avg_pm10': round(sum(pm10_vals) / len(pm10_vals), 1) if pm10_vals else 0,
            'max_pm10': round(max(pm10_vals), 1) if pm10_vals else 0,
            'avg_pm2_5': round(sum(pm2_5_vals) / len(pm2_5_vals), 1) if pm2_5_vals else 0,
            'max_pm2_5': round(max(pm2_5_vals), 1) if pm2_5_vals else 0,
            'avg_aqi': round(sum(aqi_vals) / len(aqi_vals), 1) if aqi_vals else 50,
            'max_aqi': round(max(aqi_vals), 1) if aqi_vals else 50,
        }
    
    def _find_nearest(
        self,
        point: Tuple[float, float],
        grid: Dict[Tuple[float, float], Dict]
    ) -> Optional[Dict]:
        """Find nearest grid point"""
        if not grid:
            return None
        
        nearest = min(grid.keys(), key=lambda p: haversine_distance(point, p))
        
        if haversine_distance(point, nearest) > 2.0:
            return None
        
        return grid[nearest]
    
    def get_pollution_at_point(
        self,
        lat: float,
        lon: float,
        pollution_data: List[Dict]
    ) -> Dict[str, float]:
        """Get pollution at specific point"""
        grid = self._build_pollution_grid(pollution_data)
        point = (round(lat / 0.002) * 0.002, round(lon / 0.002) * 0.002)
        return grid.get(point, {'pm10': -1, 'pm2_5': -1, 'aqi': 50})
