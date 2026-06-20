"""
- Ingest_Service calls send_data_to_database() function which sends a HTTP POST
request to /add_data endpoint in Database_Service

- Data_Provider_Service calls get_data_from_database() function which sends a
HTTP GET request to /get_data endpoint in Database Service
"""

import httpx
import logging
import os
from fastapi import HTTPException

DATABASE_SERVICE_URL = os.getenv("DATABASE_SERVICE_URL", "http://database-service:8000")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

async def send_data_to_database(payload: dict) -> dict:
    """
    Send sensor data to database for storage. (used by Ingest_Service)

    Args:
        payload: Dict with sensor data matching pollution_data schema
    
    Returns:
        {"success": True} on success
        {"error": "..."} on failure
    """
    try:
        url = f"{DATABASE_SERVICE_URL}/add_data/"

        # Set defaults for optional fields (database expects -1 for missing values)
        defaults = {
            'altitude': -1, 'humidity': -1, 'pressure': -1, 'temperature': -1,
            'co': -1, 'co2': -1, 'no2': -1, 'nh3': -1, 'vocs': -1,
            'pm1_0': -1, 'pm2_5': -1, 'pm10': -1
        }

        # Apply defaults for missing or None values
        data = {**defaults, **{k: v for k, v in payload.items() if v is not None}}

        # POST REQUEST
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=data)

        if response.status_code == 200:
            logging.info(f"Data sent to database for sensor {data.get('sensor_id')}")
            return {"success": True}

        logging.error(f"Database error: {response.text}")
        return {"error": f"Database error: {response.text}"}
            
    except httpx.TimeoutException:
        logging.error("Database service timeout")
        return {"error": "Database service timeout"}

    except Exception as e:
        logging.error(f"Error sending to database: {str(e)}")
        return {"error": str(e)}

async def get_data_from_database(payload: dict) -> str:
    """
    Fetch pollution data from database. (used by Data_Provider_Service)
    
    Args:
        payload: Dict containing:
            - latitude, longitude, radius
            - layers (optional), sensor_types (optional)
    
    Returns:
        JSON string with sensor readings
    """
    try:
        url = f"{DATABASE_SERVICE_URL}/get_data/"

        # Build query parameters
        params = {
            "latitude": payload.get("latitude"),
            "longitude": payload.get("longitude"),
            "radius": payload.get("radius"),
        }

        # Add layers as multiple query params
        if payload.get("layers"):
            params["layers"] = payload.get("layers")

        # Add sensor_types as multiple query params
        if payload.get("sensor_types"):
            params["sensor_types"] = payload.get("sensor_types")

        # GET REQUEST
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()

        logging.info("Data received from database")
        return response.text

    except httpx.HTTPStatusError as e:
        logging.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)

    except httpx.TimeoutException:
        logging.error("Database service timeout")
        raise HTTPException(status_code=504, detail="Database service timeout")

    except Exception as e:
        logging.error(f"Error fetching from database: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
