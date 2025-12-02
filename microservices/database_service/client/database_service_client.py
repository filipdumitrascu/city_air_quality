import httpx
import logging
from fastapi import HTTPException
import os

DATABASE_SERVER_URL = "http://35.187.0.103:8003"

logging.basicConfig(
    level=logging.DEBUG, 
    filename=os.path.join('logs', 'database_client.log'),
    filemode='w', 
    format='%(asctime)s - %(levelname)s - %(message)s'
) 
client = httpx.AsyncClient()

async def send_data_to_database(payload):
    try:
        url = f"{DATABASE_SERVER_URL}/add_data/"
        async with httpx.AsyncClient() as client:
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
    try:
        url = f"{DATABASE_SERVER_URL}/get_data/"
        response = await client.get(url, params=payload)
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

