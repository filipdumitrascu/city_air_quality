from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from schemas import InsertPollutionDataRequest
from db import insert_data, fetch_data
import logging
import os
from fastapi import Query
from typing import List, Optional
from db import init_db, close_db
import math

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
        logging.info("Database connection initialized")
    except Exception as e:
        logging.error(f"Database NOT available at startup: {e}")
    yield
    try:
        close_db()
    except Exception:
        pass

app = FastAPI(
    title="Database service API",
    description="Microservice that communicates with database",
    lifespan=lifespan,
    version="1.0.0")

@app.get("/")
async def root():
    """Root endpoint."""
    return {"service": "database_service", "status": "running"}

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "database_service"}

@app.post("/add_data/")
async def add_data(payload: InsertPollutionDataRequest):
    """Adaugă datele de poluare în baza de date."""
    try:
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

        for entry in payload.data:
            if entry.dimension in pollution_data:
                pollution_data[entry.dimension] = entry.value

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

        insert_data(params)
        return {"success": True}

    except Exception as e:
        logging.error(f"Error adding data {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error adding data: {str(e)}")
    
def get_coordinate_deltas(radius_km: float, latitude_deg: float):
    """
    Calculează delta de latitudine și longitudine pentru o rază dată (în km),
    la o anumită latitudine (în grade).

    Returnează:
        (delta_latitude, delta_longitude)
    """
    # Lat: 1 grad ≈ 111.32 km peste tot pe glob
    delta_lat = radius_km / 111.32

    # Lng: 1 grad ≈ 111.32 * cos(latitudine)
    lat_rad = math.radians(latitude_deg)
    km_per_deg_lng = 111.32 * math.cos(lat_rad)
    delta_lng = radius_km / km_per_deg_lng

    return delta_lat, delta_lng
    
@app.get("/get_data/")
async def get_data(
    latitude: float = Query(...),
    longitude: float = Query(...),
    radius: int = Query(..., ge=0),
    layers: Optional[List[str]] = Query(None)
):
    """Obține datele de poluare din jurul unei locații."""

    if not layers:
        layers = ["Temperature","Humidity","Pressure","Altitude","CO2","PM1_0","PM2_5","PM10"]

    try:
        delta_lat, delta_lng = get_coordinate_deltas(radius, latitude)
        params = (layers, latitude, delta_lat, longitude, delta_lng)
        results = fetch_data(params)
        return results
    except Exception as e:
        logging.error("a gasit eroare la results")
        if e.status_code == 404:
            logging.error("a gasit eroare la result no found")
            raise HTTPException(status_code=404, detail="No data found")
        else:
            logging.error("a gasit eroare la results la fetching")
            raise HTTPException(status_code=500, detail=f"Error fetching measurements: {str(e)}")
