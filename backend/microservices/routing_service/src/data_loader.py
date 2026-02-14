import httpx
import logging
import math
from typing import List, Dict, Optional, Tuple
from .config import get_config

logger = logging.getLogger(__name__)

def haversine_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """Calculate distance between coordinates in km using Haversine formula"""
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    
    R = 6371  # Earth's radius in km
    
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = (
        math.sin(dlat / 2) ** 2 +
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
        math.sin(dlon / 2) ** 2
    )
    
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c

def calculate_optimized_query_params(
    start: Tuple[float, float],
    goal: Tuple[float, float],
    buffer_factor: float = 0.75
) -> Tuple[float, float, float]:
    """
    Calculate optimized center and radius for pollution data query.
    
    Instead of querying all of Bucharest, we query a circle that:
    - Is centered at the midpoint between start and goal
    - Has radius = distance * buffer_factor (allows for detours)
    
    Args:
        start: (lat, lon) start coordinate
        goal: (lat, lon) goal coordinate
        buffer_factor: Multiplier for radius (0.75 = 50% buffer on each side)
                      Higher = more data, more detour options
                      Lower = less data, faster query
    
    Returns:
        (center_lat, center_lon, radius_km)
    
    Example:
        Start: Piata Unirii (44.4268, 26.1025)
        Goal: Piata Victoriei (44.4530, 26.0855)
        Distance: ~3.2 km
        Radius: 3.2 * 0.75 = 2.4 km
        
        This covers the direct path plus reasonable detours,
        but won't fetch data from Militari or Titan.
    """
    # Calculate midpoint (center of query circle)
    center_lat = (start[0] + goal[0]) / 2
    center_lon = (start[1] + goal[1]) / 2
    
    # Calculate distance between start and goal
    distance_km = haversine_distance(start, goal)
    
    # Calculate radius with buffer
    # Minimum radius of 1km to ensure we have enough data for short routes
    radius_km = max(distance_km * buffer_factor, 1.0)
    
    logger.info(
        f"Optimized query: center=({center_lat:.4f}, {center_lon:.4f}), "
        f"distance={distance_km:.2f}km, radius={radius_km:.2f}km"
    )
    
    return center_lat, center_lon, radius_km

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
        Fetch pollution data from Database Service
        
        Args:
            lat: Center latitude
            lon: Center longitude
            radius_km: Search radius in kilometers
            sensor_types: List of sensor types to include ['fixed', 'mobile']
        
        Returns:
            List of pollution readings (arrays from QuestDB)
        """
        try:
            # Build query parameters
            params = {
                "latitude": lat,
                "longitude": lon,
                "radius": radius_km,
                "layers": ["pm10", "pm25", "no2"]
            }
            
            # Add sensor_types to query params if specified
            if sensor_types:
                params["sensor_types"] = sensor_types
            
            logger.info(f"Fetching pollution data: lat={lat}, lon={lon}, radius={radius_km}km, sensors={sensor_types}")
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.database_url}/get_data/",
                    params=params
                )
                response.raise_for_status()
                data = response.json()
            
            # Filter by sensor type if specified (backup filtering if DB doesn't support it)
            if sensor_types:
                filtered_data = []
                for reading in data:
                    sensor_id = reading[0] if isinstance(reading, (list, tuple)) else reading.get("sensor_id", "")
                    
                    # Determine type from sensor_id prefix
                    if ("fixed" in sensor_types and sensor_id.startswith("F")) or \
                       ("mobile" in sensor_types and sensor_id.startswith("M")):
                        filtered_data.append(reading)
                
                if len(filtered_data) != len(data):
                    logger.info(f"Filtered {len(data)} -> {len(filtered_data)} readings by sensor_types={sensor_types}")
                return filtered_data
            
            logger.info(f"Fetched {len(data)} pollution readings")
            return data
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching pollution data: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching pollution data: {e}")
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
        
        Instead of fetching all Bucharest data, this method:
        1. Calculates the midpoint between start and goal
        2. Uses distance * buffer_factor as radius
        3. Queries only the relevant area
        
        This is more efficient than fetch_area_pollution for routing.
        
        Args:
            start: (lat, lon) start coordinate
            goal: (lat, lon) goal coordinate
            sensor_types: List of sensor types ['fixed', 'mobile']
            buffer_factor: How much extra area to include (default 0.75)
                          0.5 = tight around direct path
                          1.0 = generous detour allowance
        
        Returns:
            List of pollution readings in the route corridor
        """
        center_lat, center_lon, radius_km = calculate_optimized_query_params(
            start, goal, buffer_factor
        )
        
        return await self.fetch_pollution_data(
            center_lat,
            center_lon,
            radius_km,
            sensor_types
        )
    
    async def fetch_area_pollution(
        self,
        lat_min: float,
        lat_max: float,
        lon_min: float,
        lon_max: float,
        sensor_types: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Fetch pollution data for entire area (legacy method).
        
        Note: For routing, prefer fetch_route_pollution() which is more efficient.
        """
        center_lat = (lat_min + lat_max) / 2
        center_lon = (lon_min + lon_max) / 2
        
        # Calculate radius to cover entire area
        lat_diff = (lat_max - lat_min) * 111
        lon_diff = (lon_max - lon_min) * 111 * 0.7
        radius_km = max(lat_diff, lon_diff) / 2 + 2
        
        return await self.fetch_pollution_data(
            center_lat,
            center_lon,
            radius_km,
            sensor_types
        )
