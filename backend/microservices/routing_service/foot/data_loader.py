"""
PollutionDataLoader (loads pollution data form Database Service)

- fetch_pollution_data()  returns the data in a circe with a specific radius
- fetch_route_pollution()  calls the previous function centered at midpoint distance
between the start and goal + 25% of the radius for safety  (used for bicycle mode)
- fetch_area_pollution()   fetch for a bounding box (used for route mode)
"""
import httpx
import logging
import math
from typing import List, Dict, Optional, Tuple

import sys
import os

# Add parent directory to path for imports
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from config import get_config, ROUTING_POLLUTANTS

logger = logging.getLogger(__name__)


def haversine_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """Calculate distance in km using Haversine formula"""
    lat1, lon1 = coord1
    lat2, lon2 = coord2

    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)

    return R * 2 * math.asin(math.sqrt(a))


class PollutionDataLoader:
    """Loads pollution data from Database Service"""
    def __init__(self):
        self.config = get_config()
        self.database_url = self.config["database_service_url"]

    async def fetch_pollution_data(
        self,
        lat: float,
        lon: float,
        radius_km: float,
        sensor_types: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Fetch pollution data from Database Service.
        
        Returns list of dicts with:
        - sensor_id, sensor_type, timestamp, latitude, longitude, layers
        
        Values of -1 are kept but will be filtered during AQI calculation.
        """
        try:
            params = {
                "latitude": lat,
                "longitude": lon,
                "radius": radius_km,
                "layers": ROUTING_POLLUTANTS
            }

            if sensor_types:
                params["sensor_types"] = sensor_types

            logger.info(f"Fetching pollution: ({lat:.4f}, {lon:.4f}), radius={radius_km}km")

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{self.database_url}/get_data/",
                    params=params
                )
                response.raise_for_status()
                data = response.json()

            logger.info(f"Fetched {len(data)} pollution readings")
            return data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning("No pollution data found")
                return []
            raise
        except Exception as e:
            logger.error(f"Error fetching pollution: {e}")
            raise

    async def fetch_route_pollution(
        self,
        start: Tuple[float, float],
        goal: Tuple[float, float],
        sensor_types: Optional[List[str]] = None,
        buffer_factor: float = 0.75
    ) -> List[Dict]:
        """
        Fetch pollution data optimized for a specific route.
        
        Queries a circle centered at midpoint with radius based on
        start-goal distance. More efficient than querying all of the city.
        """
        center_lat = (start[0] + goal[0]) / 2
        center_lon = (start[1] + goal[1]) / 2

        distance = haversine_distance(start, goal)
        radius_km = max(distance * buffer_factor, 1.0)

        logger.info(f"Route query: center=({center_lat:.4f}, {center_lon:.4f}), radius={radius_km:.2f}km")

        return await self.fetch_pollution_data(
            center_lat, center_lon, radius_km, sensor_types
        )

    async def fetch_area_pollution(
        self,
        lat_min: float, lat_max: float,
        lon_min: float, lon_max: float,
        sensor_types: Optional[List[str]] = None
    ) -> List[Dict]:
        """Fetch pollution for entire bounding box (legacy method)"""
        center_lat = (lat_min + lat_max) / 2
        center_lon = (lon_min + lon_max) / 2

        lat_diff = (lat_max - lat_min) * 111
        lon_diff = (lon_max - lon_min) * 111 * 0.7
        radius_km = max(lat_diff, lon_diff) / 2 + 2

        return await self.fetch_pollution_data(
            center_lat, center_lon, radius_km, sensor_types
        )
