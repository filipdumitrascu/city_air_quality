import httpx
import logging
from fastapi import HTTPException
import os

DATABASE_SERVER_URL = os.getenv("DATABASE_SERVICE_URL", "http://database-service:8000")

logging.basicConfig(
    level=logging.DEBUG, 
    filename=os.path.join('logs', 'database_client.log'),
    filemode='w', 
    format='%(asctime)s - %(levelname)s - %(message)s'
) 


async def send_data_to_database(payload):
    """Send sensor data to database for storage."""
    try:
        url = f"{DATABASE_SERVER_URL}/add_data/"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
        if response.status_code == 200:
            logging.info("Data successfully sent to DatabaseServer")
            return {"success": True}
        else:
            logging.error(f"Error from DatabaseServer: {response.text}")
            return {"error": "Failed to add data to the database"}
    except Exception as e:
        logging.error(f"Error while sending data to DatabaseServer: {str(e)}")
        return {"error": f"Error: {str(e)}"}


async def get_data_from_database(payload):
    """
    Fetch pollution data from database.
    
    Args:
        payload: Dict containing:
            - latitude: Center point latitude
            - longitude: Center point longitude
            - radius: Search radius in km
            - layers: List of pollution metrics
            - sensor_types: Optional list of sensor types ('fixed', 'mobile')
    
    Returns:
        JSON string with sensor readings
    """
    try:
        url = f"{DATABASE_SERVER_URL}/get_data/"
        
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
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status() 
       
        logging.info("Data successfully received from DatabaseServer")
        data = response.text
        return data
        
    except HTTPException as e:
        raise e
    except httpx.HTTPStatusError as e:
        logging.error(f"HTTP error while fetching data: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        logging.error(f"Unexpected error while sending data to DatabaseServer: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
