import httpx
import logging
from typing import List, Dict, Optional
from .config import get_config

logger = logging.getLogger(__name__)

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
            
            logger.info(f"Fetching pollution data: lat={lat}, lon={lon}, radius={radius_km}km")
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.database_url}/get_data/",
                    params=params
                )
                response.raise_for_status()
                data = response.json()
            
            # Filter by sensor type if specified
            # QuestDB returns arrays: [sensor_id, timestamp, lat, lon, pm10, ...]
            if sensor_types:
                filtered_data = []
                for reading in data:
                    sensor_id = reading[0] if isinstance(reading, (list, tuple)) else reading.get("sensor_id", "")
                    
                    # Determine type from sensor_id prefix
                    if ("fixed" in sensor_types and sensor_id.startswith("F")) or \
                       ("mobile" in sensor_types and sensor_id.startswith("M")):
                        filtered_data.append(reading)
                
                logger.info(f"Filtered {len(data)} → {len(filtered_data)} readings by sensor_types={sensor_types}")
                return filtered_data
            
            logger.info(f"Fetched {len(data)} pollution readings")
            return data
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching pollution data: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching pollution data: {e}")
            raise
    
    async def fetch_area_pollution(
        self,
        lat_min: float,
        lat_max: float,
        lon_min: float,
        lon_max: float,
        sensor_types: Optional[List[str]] = None
    ) -> List[Dict]:
        """Fetch pollution data for entire area"""
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
