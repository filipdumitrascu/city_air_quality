from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from schemas import InsertPollutionDataRequest
from db import insert_data, fetch_data, init_db, close_db
import logging
import os
from typing import List, Optional
import math

# Configure file-based logging for Database Service
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)

log_file = os.path.join(log_dir, 'database_service.log')
if not os.path.exists(log_file):
    open(log_file, 'w').close()

logging.basicConfig(
    level=logging.DEBUG,
    filename=log_file,
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s'
)


# Fast API
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Initialize database connection pool on startup.
    Close all connections on shutdown.
    """
    try:
        init_db()
        logging.info("Database connection initialized")
    except Exception as e:
        logging.error(f"Database NOT available at startup: {e}")
    
    yield  # App runs here
    
    try:
        close_db()
        logging.info("Database connections closed")
    except Exception:
        pass

app = FastAPI(
    title="Database Service API",
    description="Microservice that communicates with QuestDB",
    lifespan=lifespan,
    version="1.0.0"
)


# Health check endpoints
@app.get("/")
async def root():
    """Root endpoint"""
    return {"service": "database_service", "status": "running"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "database_service"}


# Endpoint (data insertion)
@app.post("/add_data/")
async def add_data(payload: InsertPollutionDataRequest):
    """
    Insert pollution data into QuestDB.
    
    Transforms payload from Client Message Handler format to database format:
    - Extracts pollution dimensions (Temperature, PM10, etc.)
    - Maps to database columns
    - Inserts via connection pool
    
    Args:
        payload: Sensor data with clientId, timestamp, location, measurements
    
    Returns:
        {"success": True} on successful insertion
        
    Raises:
        400: Invalid data or database insertion error
    """
    try:
        # Initialize pollution data dictionary with all possible dimensions
        pollution_data = {
            "Temperature": None,
            "Humidity": None,
            "Pressure": None,
            "Altitude": None,
            "CO2": None,
            "PM1.0": None,
            "PM2.5": None,
            "PM10": None
        }

        # Map payload data to pollution_data dictionary
        for entry in payload.data:
            if entry.dimension in pollution_data:
                pollution_data[entry.dimension] = entry.value

        # Prepare parameters for database insertion
        params = (
            payload.clientId,
            payload.timestamp,
            payload.location.latitude,
            payload.location.longitude,
            pollution_data["Temperature"],
            pollution_data["Humidity"],
            pollution_data["Pressure"],
            pollution_data["Altitude"],
            pollution_data["CO2"],
            pollution_data["PM1.0"],
            pollution_data["PM2.5"],
            pollution_data["PM10"]
        )

        # Execute INSERT query
        insert_data(params)
        return {"success": True}

    except Exception as e:
        logging.error(f"Error adding data {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error adding data: {str(e)}")


# Helepr function
def get_coordinate_deltas(radius_km: float, latitude_deg: float):
    """
    Calculate latitude and longitude deltas for a given radius in km.
    
    Used to convert radius (km) to coordinate bounds for spatial queries.
    
    Args:
        radius_km: Search radius in kilometers
        latitude_deg: Center latitude in degrees
    
    Returns:
        (delta_lat, delta_lng): Coordinate deltas in degrees
        
    Math:
        - 1 degree latitude = 111.32 km everywhere
        - 1 degree longitude = 111.32 * cos(latitude) km (varies with latitude)
    """
    # Latitude: constant 111.32 km per degree
    delta_lat = radius_km / 111.32

    # Longitude: varies with latitude (narrower near poles)
    lat_rad = math.radians(latitude_deg)
    km_per_deg_lng = 111.32 * math.cos(lat_rad)
    delta_lng = radius_km / km_per_deg_lng

    return delta_lat, delta_lng


# Endpoint (data retrieval)
@app.get("/get_data/")
async def get_data(
    latitude: float = Query(...),
    longitude: float = Query(...),
    radius: float = Query(..., ge=0),
    layers: Optional[List[str]] = Query(None)
):
    """
    Retrieve pollution data within a geographic radius.
    
    Flow:
    1. Convert radius (km) to coordinate deltas
    2. Query QuestDB for readings within bounding box
    3. Return latest readings per grid cell (LATEST ON partition)
    
    Args:
        latitude: Center point latitude
        longitude: Center point longitude
        radius: Search radius in kilometers (float, >=0)
        layers: Optional list of pollution metrics to retrieve
                Default: All metrics (Temperature, PM10, etc.)
    
    Returns:
        List of sensor readings: [clientId, timestamp, lat, lon, ...pollution values]
        
    Raises:
        404: No data found in specified area
        500: Database query error
    """
    # Default to all available pollution layers if none specified
    if not layers:
        layers = ["Temperature", "Humidity", "Pressure", "Altitude", "CO2", "PM1_0", "PM2_5", "PM10"]

    try:
        # Convert radius to coordinate deltas
        delta_lat, delta_lng = get_coordinate_deltas(radius, latitude)
        
        # Prepare parameters for query
        params = (layers, latitude, delta_lat, longitude, delta_lng)
        
        # Execute SELECT query
        results = fetch_data(params)
        return results
        
    except HTTPException as http_exc:
        # Re-raise HTTP exceptions (404, etc.)
        logging.error(f"HTTP Exception: {http_exc}")
        raise http_exc
    except Exception as e:
        # Log and wrap unexpected errors
        logging.error(f"Error fetching data: {str(e)}")
        logging.exception(e)
        raise HTTPException(status_code=500, detail=f"Error fetching measurements: {str(e)}")
