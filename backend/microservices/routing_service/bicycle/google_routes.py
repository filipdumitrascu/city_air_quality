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
            "travelMode": "DRIVE",
            "computeAlternativeRoutes": alternatives,
            "routeModifiers": {"avoidTolls": False, "avoidHighways": False},
        }

        logger.info(f"Requesting Google Routes: {start} -> {goal}")

        # POST REQUEST
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

        # Get max values for normalization
        d_max = max(r["distance_km"] for r in routes)
        aqi_max = 500  # fixed, as per thesis

        for route in routes:
            norm_dist = route["distance_km"] / d_max
            norm_aqi = route["pollution"]["avg_aqi"] / aqi_max
            route["score"] = (1 - alpha) * norm_dist + alpha * norm_aqi

        routes.sort(key=lambda r: r["score"])

        logger.info(f"Selected route {routes[0]['index']} (score={routes[0]['score']:.3f})")
        return routes[0], routes


    def _build_pollution_grid(
        self, 
        pollution_data: List[Dict],
        resolution: float = 0.002
    ) -> Dict[Tuple[float, float], Dict[str, float]]:
        """Build pollution grid from database readings - all 8 pollutants"""
        grid = {}
        pollutant_keys = ['pm10', 'pm2_5', 'pm1_0', 'no2', 'co', 'co2', 'nh3', 'vocs']

        # Import AQI calculation from graph_builder
        from foot.graph_builder import calculate_aqi

        for reading in pollution_data:
            try:
                if isinstance(reading, dict):
                    lat = float(reading.get("latitude", 0))
                    lon = float(reading.get("longitude", 0))

                    pollutants = {}
                    for key in pollutant_keys:
                        val = reading.get(key, -1)
                        pollutants[key] = float(val) if val is not None else -1
                else:
                    lat = float(reading[3])
                    lon = float(reading[4])
                    pollutants = {
                        'pm10': float(reading[5]) if len(reading) > 5 and reading[5] is not None else -1,
                        'pm2_5': float(reading[6]) if len(reading) > 6 and reading[6] is not None else -1,
                        'no2': float(reading[7]) if len(reading) > 7 and reading[7] is not None else -1,
                        'co': float(reading[8]) if len(reading) > 8 and reading[8] is not None else -1,
                        'co2': float(reading[9]) if len(reading) > 9 and reading[9] is not None else -1,
                        'pm1_0': float(reading[10]) if len(reading) > 10 and reading[10] is not None else -1,
                        'nh3': float(reading[11]) if len(reading) > 11 and reading[11] is not None else -1,
                        'vocs': float(reading[12]) if len(reading) > 12 and reading[12] is not None else -1,
                    }

                grid_point = (
                    round(lat / resolution) * resolution,
                    round(lon / resolution) * resolution
                )

                # Calculate AQI using weighted formula
                aqi = calculate_aqi(pollutants) or 50.0

                if grid_point in grid:
                    old = grid[grid_point]
                    merged = {}
                    for key in pollutant_keys:
                        old_val = old.get(key, -1)
                        new_val = pollutants.get(key, -1)
                        if old_val >= 0 and new_val >= 0:
                            merged[key] = (old_val + new_val) / 2
                        elif new_val >= 0:
                            merged[key] = new_val
                        else:
                            merged[key] = old_val
                    merged['aqi'] = (old['aqi'] + aqi) / 2
                    grid[grid_point] = merged
                else:
                    pollutants['aqi'] = aqi
                    grid[grid_point] = pollutants

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
        """Calculate pollution statistics for waypoints - all 8 pollutants"""
        pollutant_keys = ['pm10', 'pm2_5', 'pm1_0', 'no2', 'co', 'co2', 'nh3', 'vocs']
        pollutant_values = {key: [] for key in pollutant_keys}
        aqi_vals = []

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
                # Collect each pollutant
                for key in pollutant_keys:
                    val = data.get(key, -1)
                    if val >= 0:
                        pollutant_values[key].append(val)

                aqi_vals.append(data.get('aqi', 50))
            else:
                aqi_vals.append(50)  # Default

        # Build result
        result = {
            'avg_aqi': round(sum(aqi_vals) / len(aqi_vals), 1) if aqi_vals else 50,
            'max_aqi': round(max(aqi_vals), 1) if aqi_vals else 50,
        }

        # Add stats for each pollutant
        for key in pollutant_keys:
            vals = pollutant_values[key]
            if vals:
                result[f'avg_{key}'] = round(sum(vals) / len(vals), 1)
                result[f'max_{key}'] = round(max(vals), 1)
            else:
                result[f'avg_{key}'] = -1
                result[f'max_{key}'] = -1

        return result


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
        """Get pollution at specific point - returns all pollutants"""
        grid = self._build_pollution_grid(pollution_data)
        point = (round(lat / 0.002) * 0.002, round(lon / 0.002) * 0.002)

        default = {
            'pm10': -1, 'pm2_5': -1, 'pm1_0': -1, 
            'no2': -1, 'co': -1, 'co2': -1,
            'nh3': -1, 'vocs': -1, 'aqi': 50
        }
        return grid.get(point, default)
