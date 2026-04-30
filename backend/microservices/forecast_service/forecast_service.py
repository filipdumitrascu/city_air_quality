from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import logging
import os
import time
import asyncio
import math
import httpx

from polpred import PolPredModel

# Logging to stdout only (visible via kubectl logs)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ENV variables
DATABASE_SERVICE_URL = os.getenv("DATABASE_SERVICE_URL", "http://database-service:8000")
MODEL_PATH = os.getenv("MODEL_PATH", "/app/model/polpred.pkl")
GRID_RESOLUTION = float(os.getenv("GRID_RESOLUTION", "0.002"))  # ~220m

# Constants
BUCHAREST_BOUNDS = {
    "lat_min": 44.33,
    "lat_max": 44.57,
    "lon_min": 25.93,
    "lon_max": 26.27
}
PREDICT_POLLUTANTS = ["pm10", "pm2_5", "no2", "co"]
ROMANIA_OFFSET_MS = 3 * 60 * 60 * 1000


# Request/Response Models
class Point(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
class ModelStatus(BaseModel):
    """Model status information."""
    loaded: bool
    model_path: str
    pollutants: List[str]
    feature_count: int
    last_prediction: Optional[str] = None


# Global state
model: Optional[PolPredModel] = None
model_status = {
    "loaded": False,
    "last_prediction": None,
    "predictions_count": 0
}


# Helper functions
def get_current_timestamp_ms() -> int:
    """Get current Unix timestamp in milliseconds (Romania time)."""
    import time
    return int(time.time() * 1000) + ROMANIA_OFFSET_MS

async def fetch_current_sensor_state() -> List[dict]:
    """
    Fetch current readings from all sensors (SPO-RO + mobile).
    Returns list of station snapshots for model input.
    """
    try:
        params = {
            "latitude": (BUCHAREST_BOUNDS["lat_min"] + BUCHAREST_BOUNDS["lat_max"]) / 2,
            "longitude": (BUCHAREST_BOUNDS["lon_min"] + BUCHAREST_BOUNDS["lon_max"]) / 2,
            "radius": 20,  # 20km covers all of Bucharest
            "sensor_types": ["SPO-RO", "CityAirQ", "WearAware"],
            "layers": PREDICT_POLLUTANTS
        }
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{DATABASE_SERVICE_URL}/get_data/",
                params=params
            )
            response.raise_for_status()
            data = response.json()
        
        # Convert to model format
        stations = []
        for reading in data:
            station = {
                "station_id": f"{reading.get('sensor_type', 'UNK')}_{reading.get('sensor_id', 'unknown')}",
                "lat": reading.get("latitude"),
                "lon": reading.get("longitude"),
            }
            # Add pollutant values (skip -1 which means missing)
            for pollutant in PREDICT_POLLUTANTS:
                val = reading.get(pollutant)
                if val is not None and val >= 0:
                    station[pollutant] = val
            
            # Only include if has at least one valid pollutant
            if any(pollutant in station for pollutant in PREDICT_POLLUTANTS):
                stations.append(station)
        
        logger.info(f"Fetched {len(stations)} stations with valid data")
        return stations
        
    except Exception as e:
        logger.error(f"Error fetching sensor state: {e}")
        raise HTTPException(status_code=503, detail=f"Cannot fetch sensor data: {e}")

async def insert_prediction_to_db(prediction: dict) -> bool:
    """Insert a single prediction to database as Forecast sensor type."""
    try:
        payload = {
            "sensor_type": "Forecast",
            "sensor_id": None,  # No sensor_id for forecasts
            "timestamp": prediction["timestamp"],
            "latitude": prediction["lat"],
            "longitude": prediction["lon"],
            "pm10": prediction.get("pm10", -1),
            "pm2_5": prediction.get("pm2_5", -1),
            "no2": prediction.get("no2", -1),
            "co": prediction.get("co", -1),
            # Set other fields to -1 (not predicted)
            "altitude": -1, "humidity": -1, "pressure": -1, "temperature": -1,
            "co2": -1, "nh3": -1, "vocs": -1, "pm1_0": -1
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{DATABASE_SERVICE_URL}/add_data/",
                json=payload
            )
            return response.status_code == 200
            
    except Exception as e:
        logger.warning(f"Failed to insert prediction: {e}")
        return False


# FASTAPI APPLICATION
@asynccontextmanager
async def lifespan(app: FastAPI):
    global model
    
    logger.info("Starting Forecast Service...")
    
    # Try to load model
    if os.path.exists(MODEL_PATH):
        try:
            model = PolPredModel.load(MODEL_PATH)
            model_status["loaded"] = True
            logger.info(f"Model loaded from {MODEL_PATH}")
            logger.info(f"Pollutants: {model.config.pollutant_columns}")
            logger.info(f"Features: {len(model.feature_columns_)}")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            model_status["loaded"] = False
    else:
        logger.warning(f"Model file not found: {MODEL_PATH}")
        logger.warning("Service will start but predictions will fail until model is provided")
        model_status["loaded"] = False
    
    logger.info("Forecast Service ready")

    yield

    logger.info("Forecast Service shutting down")

app = FastAPI(
    title="Forecast Service",
    description="Spatial pollution prediction for CityAirQ",
    version="1.0.0",
    lifespan=lifespan
)

# Prometheus metrics
Instrumentator().instrument(app).expose(app)


# HEALTH ENDPOINTS
@app.get("/")
async def root():
    return {
        "service": "forecast_service",
        "version": "1.0.0",
        "status": "running",
        "model_loaded": model_status["loaded"]
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy" if model_status["loaded"] else "degraded",
        "service": "forecast_service",
        "model_loaded": model_status["loaded"],
        "predictions_count": model_status["predictions_count"]
    }

@app.get("/model/status", response_model=ModelStatus)
async def get_model_status():
    """Get information about the loaded model."""
    if not model_status["loaded"] or model is None:
        return ModelStatus(
            loaded=False,
            model_path=MODEL_PATH,
            pollutants=[],
            feature_count=0,
            last_prediction=model_status.get("last_prediction")
        )
    
    return ModelStatus(
        loaded=True,
        model_path=MODEL_PATH,
        pollutants=list(model.config.pollutant_columns),
        feature_count=len(model.feature_columns_),
        last_prediction=model_status.get("last_prediction")
    )


# PREDICT ENDPOINT
@app.post("/predict/fill-gaps")
async def predict_fill_gaps(
    max_neighbor_distance_km: float = 1.0,
    resolution: float = 0.005
):
    """
    Predict pollution at grid points around each sensor.
    Always includes fixed SPO-RO stations plus any mobile sensors with data.
    """
    import time
    import math
    start_time = time.time()
    
    if not model_status["loaded"] or model is None:
        return {
            "message": "Model not loaded - skipping gap fill",
            "gaps_filled": 0
        }
    
    # Fetch existing sensor data (for model input)
    station_state = await fetch_current_sensor_state()
    
    if len(station_state) < 2:
        return {
            "message": f"Not enough stations ({len(station_state)}) for gap fill",
            "gaps_filled": 0
        }
    
    # Build sensor locations for grid generation
    # Always include fixed stations + any mobile sensors from DB
    sensor_locations = set()
    
    for station in station_state:
        lat, lon = station["lat"], station["lon"]
        grid_lat = round(round(lat / resolution) * resolution, 6)
        grid_lon = round(round(lon / resolution) * resolution, 6)
        sensor_locations.add((grid_lat, grid_lon))
    
    sensor_locations = list(sensor_locations)
    
    # Build set of existing sensor coordinates (snapped to grid) - to skip
    existing_coords = set()
    for lat, lon in sensor_locations:
        grid_lat = round(lat / resolution) * resolution
        grid_lon = round(lon / resolution) * resolution
        existing_coords.add((round(grid_lat, 6), round(grid_lon, 6)))
    
    # Generate grid points (uniform coverage around each sensor)
    km_to_deg_lat = 1 / 111.32
    km_to_deg_lon = 1 / (111.32 * math.cos(math.radians(44.43)))
    
    radius_deg_lat = max_neighbor_distance_km * km_to_deg_lat
    radius_deg_lon = max_neighbor_distance_km * km_to_deg_lon
    
    steps_lat = int(radius_deg_lat / resolution)
    steps_lon = int(radius_deg_lon / resolution)
    
    gap_points_set = set()
    
    for slat, slon in sensor_locations:
        # Generate grid in square around station
        for dlat in range(-steps_lat, steps_lat + 1):
            for dlon in range(-steps_lon, steps_lon + 1):
                plat = round(slat + dlat * resolution, 6)
                plon = round(slon + dlon * resolution, 6)
                
                # Skip if outside Bucharest bounds
                if not (BUCHAREST_BOUNDS["lat_min"] <= plat <= BUCHAREST_BOUNDS["lat_max"] and
                        BUCHAREST_BOUNDS["lon_min"] <= plon <= BUCHAREST_BOUNDS["lon_max"]):
                    continue
                
                coord = (plat, plon)
                
                # Skip if already has sensor
                if coord in existing_coords:
                    continue
                
                # Skip if already added
                if coord in gap_points_set:
                    continue
                
                gap_points_set.add(coord)
    
    gap_points = [Point(lat=lat, lon=lon) for lat, lon in gap_points_set]
    
    logger.info(f"Gap fill: {len(sensor_locations)} sensors from DB, "
                    f"{len(gap_points)} gap points within {max_neighbor_distance_km}km radius")
    
    if not gap_points:
        return {
            "message": "No gaps to fill near existing sensors",
            "sensors": len(sensor_locations),
            "gaps_filled": 0,
            "calculation_time_ms": round((time.time() - start_time) * 1000, 2)
        }
    
    # Limit predictions per call
    max_predictions = 500
    if len(gap_points) > max_predictions:
        logger.info(f"Limiting from {len(gap_points)} to {max_predictions} predictions")
        gap_points = gap_points[:max_predictions]
    
    # Predict for gaps
    timestamp = get_current_timestamp_ms()
    predictions = []
    
    for point in gap_points:
        try:
            pred = model.predict_at(
                latitude=point.lat,
                longitude=point.lon,
                station_state=station_state,
                timestamp=datetime.utcnow().isoformat()
            )
            
            predictions.append({
                "lat": point.lat,
                "lon": point.lon,
                "pm10": pred.get("pm10") or pred.get("PM10"),
                "pm2_5": pred.get("pm2_5") or pred.get("PM2.5"),
                "no2": pred.get("no2") or pred.get("NO2"),
                "co": pred.get("co") or pred.get("CO"),
                "timestamp": timestamp
            })
        except Exception as e:
            logger.warning(f"Prediction failed at ({point.lat}, {point.lon}): {e}")
            continue
    
    # Insert to DB
    insert_tasks = [insert_prediction_to_db(pred) for pred in predictions]
    results = await asyncio.gather(*insert_tasks)
    inserted_count = sum(results)
    
    model_status["last_prediction"] = datetime.utcnow().isoformat()
    model_status["predictions_count"] += len(predictions)
    
    calc_time = round((time.time() - start_time) * 1000, 2)
    
    logger.info(f"Gap fill complete: {inserted_count} predictions in {calc_time}ms")
    
    return {
        "message": f"Filled {inserted_count} gap points with predictions",
        "sensors": len(sensor_locations),
        "gaps_found": len(gap_points),
        "gaps_filled": inserted_count,
        "max_neighbor_distance_km": max_neighbor_distance_km,
        "resolution_deg": resolution,
        "calculation_time_ms": calc_time
    }
