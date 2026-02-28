import httpx
import logging
import math
import polyline
from typing import List, Dict, Tuple, Optional
from .config import get_config
from .utils import haversine_distance

logger = logging.getLogger(__name__)


def decode_polyline(encoded: str) -> List[Tuple[float, float]]:
    """
    Decode Google's encoded polyline to list of (lat, lon) tuples.
    Uses the polyline library for accurate decoding.
    """
    decoded = polyline.decode(encoded)
    return [(lat, lon) for lat, lon in decoded]


def sample_waypoints(
    path: List[Tuple[float, float]], 
    sample_distance_m: int = 200
) -> List[Tuple[float, float]]:
    """
    Sample waypoints from path at regular intervals.
    
    Args:
        path: List of (lat, lon) coordinates
        sample_distance_m: Distance between samples in meters
    
    Returns:
        Sampled waypoints including start and end
    """
    if len(path) <= 2:
        return path
    
    sample_distance_km = sample_distance_m / 1000.0
    sampled = [path[0]]
    accumulated_distance = 0.0
    
    for i in range(1, len(path)):
        dist = haversine_distance(path[i-1], path[i])
        accumulated_distance += dist
        
        if accumulated_distance >= sample_distance_km:
            sampled.append(path[i])
            accumulated_distance = 0.0
    
    if sampled[-1] != path[-1]:
        sampled.append(path[-1])
    
    return sampled


class GoogleRoutesClient:
    """Client for Google Routes API"""
    
    def __init__(self):
        self.config = get_config()
        self.api_key = self.config["google_maps_api_key"]
        self.base_url = "https://routes.googleapis.com/directions/v2:computeRoutes"
        
        if not self.api_key:
            logger.warning("Google Maps API key not configured!")
    
    def is_configured(self) -> bool:
        """Check if API key is configured"""
        return bool(self.api_key)
    
    async def get_routes(
        self,
        start: Tuple[float, float],
        goal: Tuple[float, float],
        alternatives: bool = True
    ) -> List[Dict]:
        """
        Get routes from Google Routes API.
        
        Args:
            start: (lat, lon) start coordinate
            goal: (lat, lon) goal coordinate
            alternatives: Whether to request alternative routes
        
        Returns:
            List of route dictionaries with decoded paths
        """
        if not self.api_key:
            raise ValueError("Google Maps API key not configured")
        
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline,routes.legs,routes.routeLabels"
        }
        
        body = {
            "origin": {
                "location": {
                    "latLng": {
                        "latitude": start[0],
                        "longitude": start[1]
                    }
                }
            },
            "destination": {
                "location": {
                    "latLng": {
                        "latitude": goal[0],
                        "longitude": goal[1]
                    }
                }
            },
            "travelMode": "DRIVE",
            "computeAlternativeRoutes": alternatives,
            "routeModifiers": {
                "avoidTolls": False,
                "avoidHighways": False,
                "avoidFerries": True
            },
            "languageCode": "en-US",
            "units": "METRIC"
        }
        
        logger.info(f"Requesting Google Routes: {start} -> {goal}")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                self.base_url,
                headers=headers,
                json=body
            )
            
            if response.status_code != 200:
                logger.error(f"Google Routes API error: {response.status_code} - {response.text}")
                response.raise_for_status()
            
            data = response.json()
        
        routes = []
        for i, route in enumerate(data.get("routes", [])):
            encoded_polyline = route.get("polyline", {}).get("encodedPolyline", "")
            
            if not encoded_polyline:
                logger.warning(f"Route {i} has no polyline, skipping")
                continue
            
            path = decode_polyline(encoded_polyline)
            
            duration_str = route.get("duration", "0s")
            duration_seconds = int(duration_str.replace("s", ""))
            
            distance_meters = route.get("distanceMeters", 0)
            
            routes.append({
                "index": i,
                "path": path,
                "distance_km": distance_meters / 1000.0,
                "duration_minutes": duration_seconds / 60.0,
                "labels": route.get("routeLabels", []),
                "waypoint_count": len(path)
            })
            
            logger.info(
                f"Route {i}: {distance_meters/1000:.2f}km, "
                f"{duration_seconds/60:.1f}min, {len(path)} waypoints"
            )
        
        logger.info(f"Got {len(routes)} routes from Google")
        return routes
    
    async def get_routes_with_pollution(
        self,
        start: Tuple[float, float],
        goal: Tuple[float, float],
        pollution_data: List,
        alpha: float = 0.5,
        sample_distance_m: int = 200
    ) -> Tuple[Dict, List[Dict]]:
        """
        Get routes from Google and score them by pollution.
        
        Args:
            start: (lat, lon) start coordinate
            goal: (lat, lon) goal coordinate
            pollution_data: List of pollution readings from database
            alpha: Weight for pollution (0=fastest, 1=cleanest)
            sample_distance_m: Distance between pollution samples
        
        Returns:
            Tuple of (best_route, all_routes_with_scores)
        """
        routes = await self.get_routes(start, goal, alternatives=True)
        
        if not routes:
            raise ValueError("No routes returned from Google")
        
        pollution_grid = self._build_pollution_grid(pollution_data)
        
        scored_routes = []
        for route in routes:
            sampled_waypoints = sample_waypoints(
                route["path"], 
                sample_distance_m
            )
            
            pollution_scores = self._calculate_route_pollution(
                sampled_waypoints, 
                pollution_grid
            )
            
            route["sampled_waypoints"] = sampled_waypoints
            route["pollution"] = pollution_scores
            
            normalized_distance = route["distance_km"] / max(r["distance_km"] for r in routes)
            normalized_pollution = pollution_scores["avg_aqi"] / 100.0
            
            route["score"] = (1 - alpha) * normalized_distance + alpha * normalized_pollution
            
            scored_routes.append(route)
            
            logger.info(
                f"Route {route['index']}: score={route['score']:.3f} "
                f"(dist={normalized_distance:.2f}, poll={normalized_pollution:.2f})"
            )
        
        scored_routes.sort(key=lambda r: r["score"])
        best_route = scored_routes[0]
        
        logger.info(f"Selected route {best_route['index']} with score {best_route['score']:.3f}")
        
        return best_route, scored_routes
    
    def _build_pollution_grid(
        self, 
        pollution_data: List,
        grid_resolution: float = 0.002
    ) -> Dict[Tuple[float, float], Dict[str, float]]:
        """
        Build pollution grid from database readings.
        
        Args:
            pollution_data: List of readings [sensor_id, timestamp, lat, lon, pm10, pm25, no2]
            grid_resolution: Grid cell size in degrees
        
        Returns:
            Dictionary mapping grid points to pollution values
        """
        grid = {}
        
        for reading in pollution_data:
            try:
                if isinstance(reading, (list, tuple)):
                    lat = float(reading[2])
                    lon = float(reading[3])
                    pm10 = float(reading[4]) if len(reading) > 4 and reading[4] else 0.0
                    pm25 = float(reading[5]) if len(reading) > 5 and reading[5] else 0.0
                    no2 = float(reading[6]) if len(reading) > 6 and reading[6] else 0.0
                else:
                    lat = float(reading.get("latitude", 0))
                    lon = float(reading.get("longitude", 0))
                    pm10 = float(reading.get("pm10", 0))
                    pm25 = float(reading.get("pm25", 0))
                    no2 = float(reading.get("no2", 0))
                
                grid_lat = round(lat / grid_resolution) * grid_resolution
                grid_lon = round(lon / grid_resolution) * grid_resolution
                grid_point = (grid_lat, grid_lon)
                
                pm10_idx = pm10
                pm25_idx = pm25 * 1.5
                no2_idx = no2 * 0.8
                aqi = (pm10_idx + pm25_idx + no2_idx) / 3.3
                
                if grid_point in grid:
                    existing = grid[grid_point]
                    grid[grid_point] = {
                        'pm10': (existing['pm10'] + pm10) / 2,
                        'pm25': (existing['pm25'] + pm25) / 2,
                        'no2': (existing['no2'] + no2) / 2,
                        'aqi': (existing['aqi'] + aqi) / 2
                    }
                else:
                    grid[grid_point] = {
                        'pm10': pm10,
                        'pm25': pm25,
                        'no2': no2,
                        'aqi': aqi
                    }
                    
            except Exception as e:
                logger.warning(f"Skipping invalid reading: {e}")
                continue
        
        logger.info(f"Built pollution grid with {len(grid)} cells")
        return grid
    
    def _calculate_route_pollution(
        self,
        waypoints: List[Tuple[float, float]],
        pollution_grid: Dict[Tuple[float, float], Dict[str, float]],
        grid_resolution: float = 0.002
    ) -> Dict[str, float]:
        """
        Calculate pollution statistics for route waypoints.
        
        Args:
            waypoints: List of (lat, lon) coordinates
            pollution_grid: Pollution data grid
            grid_resolution: Grid cell size
        
        Returns:
            Dictionary with pollution statistics
        """
        pm10_values = []
        pm25_values = []
        no2_values = []
        aqi_values = []
        
        for lat, lon in waypoints:
            grid_lat = round(lat / grid_resolution) * grid_resolution
            grid_lon = round(lon / grid_resolution) * grid_resolution
            grid_point = (grid_lat, grid_lon)
            
            if grid_point in pollution_grid:
                data = pollution_grid[grid_point]
            else:
                nearest = self._find_nearest_grid_point(
                    (lat, lon), 
                    pollution_grid
                )
                data = pollution_grid.get(nearest, {'pm10': 0, 'pm25': 0, 'no2': 0, 'aqi': 50})
            
            pm10_values.append(data.get('pm10', 0))
            pm25_values.append(data.get('pm25', 0))
            no2_values.append(data.get('no2', 0))
            aqi_values.append(data.get('aqi', 50))
        
        return {
            'avg_pm10': round(sum(pm10_values) / len(pm10_values), 1) if pm10_values else 0,
            'max_pm10': round(max(pm10_values), 1) if pm10_values else 0,
            'avg_pm25': round(sum(pm25_values) / len(pm25_values), 1) if pm25_values else 0,
            'max_pm25': round(max(pm25_values), 1) if pm25_values else 0,
            'avg_no2': round(sum(no2_values) / len(no2_values), 1) if no2_values else 0,
            'max_no2': round(max(no2_values), 1) if no2_values else 0,
            'avg_aqi': round(sum(aqi_values) / len(aqi_values), 1) if aqi_values else 50,
            'max_aqi': round(max(aqi_values), 1) if aqi_values else 50,
        }
    
    def _find_nearest_grid_point(
        self,
        coord: Tuple[float, float],
        pollution_grid: Dict[Tuple[float, float], Dict]
    ) -> Optional[Tuple[float, float]]:
        """Find nearest grid point with pollution data"""
        if not pollution_grid:
            return None
        
        nearest = min(
            pollution_grid.keys(),
            key=lambda p: haversine_distance(coord, p)
        )
        
        if haversine_distance(coord, nearest) > 2.0:
            return None
        
        return nearest
