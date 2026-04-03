import os
import logging
import asyncio
from datetime import datetime
from typing import List, Optional
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from prometheus_fastapi_instrumentator import Instrumentator

from polpred import PolPredModel


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DATABASE_SERVICE_URL = os.getenv("DATABASE_SERVICE_URL", "http://database-service:8000")
MODEL_PATH = os.getenv("MODEL_PATH", "/app/model/polpred.pkl")

# Grid configuration (matching routing_service)
GRID_RESOLUTION = float(os.getenv("GRID_RESOLUTION", "0.002"))  # ~220m

# Bucharest bounds
BUCHAREST_BOUNDS = {
    "lat_min": 44.35,
    "lat_max": 44.55,
    "lon_min": 25.95,
    "lon_max": 26.25
}

# Pollutants to predict (what fixed stations measure)
PREDICT_POLLUTANTS = ["pm10", "pm2_5", "no2", "co"]

# Romania timezone offset
ROMANIA_OFFSET_MS = 3 * 60 * 60 * 1000


# REQUEST/RESPONSE MODELS
class Point(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)

class PredictRequest(BaseModel):
    """Request to predict pollution at specific points."""
    points: List[Point] = Field(..., min_length=1, max_length=1000)
    insert_to_db: bool = Field(default=True, description="Insert predictions to database")

class GridPredictRequest(BaseModel):
    """Request to predict pollution for a grid area."""
    lat_min: float = Field(default=BUCHAREST_BOUNDS["lat_min"])
    lat_max: float = Field(default=BUCHAREST_BOUNDS["lat_max"])
    lon_min: float = Field(default=BUCHAREST_BOUNDS["lon_min"])
    lon_max: float = Field(default=BUCHAREST_BOUNDS["lon_max"])
    resolution: float = Field(default=GRID_RESOLUTION, description="Grid resolution in degrees")
    insert_to_db: bool = Field(default=True)

class PredictionResult(BaseModel):
    """Single prediction result."""
    lat: float
    lon: float
    pm10: Optional[float] = None
    pm2_5: Optional[float] = None
    no2: Optional[float] = None
    co: Optional[float] = None
    timestamp: int

class PredictResponse(BaseModel):
    """Response with predictions."""
    predictions: List[PredictionResult]
    station_count: int
    inserted_to_db: bool
    prediction_time_ms: float

class ModelStatus(BaseModel):
    """Model status information."""
    loaded: bool
    model_path: str
    pollutants: List[str]
    feature_count: int
    last_prediction: Optional[str] = None


# GLOBAL STATE
model: Optional[PolPredModel] = None
model_status = {
    "loaded": False,
    "last_prediction": None,
    "predictions_count": 0
}

# HELPER FUNCTIONS
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

def generate_grid_points(
    lat_min: float, lat_max: float,
    lon_min: float, lon_max: float,
    resolution: float
) -> List[Point]:
    """Generate grid points within bounds."""
    points = []
    lat = lat_min
    while lat <= lat_max:
        lon = lon_min
        while lon <= lon_max:
            points.append(Point(lat=round(lat, 6), lon=round(lon, 6)))
            lon += resolution
        lat += resolution
    
    logger.info(f"Generated {len(points)} grid points")
    return points


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

Instrumentator().instrument(app).expose(app)


# ENDPOINTS
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

@app.post("/predict", response_model=PredictResponse)
async def predict_points(request: PredictRequest):
    """
    Predict pollution at specific coordinates.
    
    Uses current sensor state (SPO-RO + mobile) to predict
    pollution values at requested points.
    """
    import time
    start_time = time.time()
    
    if not model_status["loaded"] or model is None:
        raise HTTPException(
            status_code=503,
            detail="Model not loaded. Please provide a trained model."
        )
    
    # Fetch current sensor state
    station_state = await fetch_current_sensor_state()
    
    if len(station_state) < 2:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least 2 stations for prediction, got {len(station_state)}"
        )
    
    # Make predictions
    timestamp = get_current_timestamp_ms()
    predictions = []
    
    for point in request.points:
        try:
            pred = model.predict_at(
                latitude=point.lat,
                longitude=point.lon,
                station_state=station_state,
                timestamp=datetime.utcnow().isoformat()
            )
            
            result = PredictionResult(
                lat=point.lat,
                lon=point.lon,
                pm10=pred.get("pm10") or pred.get("PM10"),
                pm2_5=pred.get("pm2_5") or pred.get("PM2.5"),
                no2=pred.get("no2") or pred.get("NO2"),
                co=pred.get("co") or pred.get("CO"),
                timestamp=timestamp
            )
            predictions.append(result)
            
        except Exception as e:
            logger.warning(f"Prediction failed for ({point.lat}, {point.lon}): {e}")
            continue
    
    # Insert to database if requested
    inserted = False
    if request.insert_to_db and predictions:
        insert_tasks = [
            insert_prediction_to_db(pred.model_dump())
            for pred in predictions
        ]
        results = await asyncio.gather(*insert_tasks)
        inserted = any(results)
        logger.info(f"Inserted {sum(results)}/{len(predictions)} predictions to DB")
    
    # Update status
    model_status["last_prediction"] = datetime.utcnow().isoformat()
    model_status["predictions_count"] += len(predictions)
    
    calc_time = round((time.time() - start_time) * 1000, 2)
    
    return PredictResponse(
        predictions=predictions,
        station_count=len(station_state),
        inserted_to_db=inserted,
        prediction_time_ms=calc_time
    )

@app.post("/predict/grid", response_model=PredictResponse)
async def predict_grid(request: GridPredictRequest):
    """
    Predict pollution for entire grid area.
    
    Generates grid points within bounds and predicts pollution
    at each point. Useful for filling gaps in sensor coverage.
    """
    # Generate grid points
    points = generate_grid_points(
        request.lat_min, request.lat_max,
        request.lon_min, request.lon_max,
        request.resolution
    )
    
    if len(points) > 1000:
        raise HTTPException(
            status_code=400,
            detail=f"Grid too large: {len(points)} points. Max 1000. Increase resolution."
        )
    
    # Use regular predict endpoint
    predict_request = PredictRequest(
        points=points,
        insert_to_db=request.insert_to_db
    )
    
    return await predict_points(predict_request)

@app.post("/predict/fill-gaps")
async def predict_fill_gaps(
    max_neighbor_distance_km: float = 2.0,
    resolution: float = 0.005  # ~500m for visualization (coarser than routing)
):
    """
    Predict pollution at grid points that:
    1. Don't have sensor data
    2. Have at least one neighbor within max_neighbor_distance_km
    
    This is for VISUALIZATION - filling gaps on the pollution map.
    Called periodically after OpenAQ sync.
    
    Args:
        max_neighbor_distance_km: Only predict if nearest sensor is within this range (default 2km)
        resolution: Grid resolution in degrees (~0.005 = 500m)
    """
    import time
    import math
    start_time = time.time()
    
    if not model_status["loaded"] or model is None:
        return {
            "message": "Model not loaded - skipping gap fill",
            "gaps_filled": 0
        }
    
    # Fetch existing sensor data
    station_state = await fetch_current_sensor_state()
    
    if len(station_state) < 3:
        return {
            "message": f"Not enough stations ({len(station_state)}) for gap fill",
            "gaps_filled": 0
        }
    
    # Helper: haversine distance in km
    def haversine(lat1, lon1, lat2, lon2):
        R = 6371  # Earth radius km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return 2 * R * math.asin(math.sqrt(a))
    
    # Build set of existing sensor coordinates (snapped to grid)
    existing_coords = set()
    sensor_locations = []  # (lat, lon) for distance checks
    
    for station in station_state:
        lat, lon = station["lat"], station["lon"]
        sensor_locations.append((lat, lon))
        # Snap to grid
        grid_lat = round(lat / resolution) * resolution
        grid_lon = round(lon / resolution) * resolution
        existing_coords.add((round(grid_lat, 6), round(grid_lon, 6)))
    
    # Generate grid points
    all_points = generate_grid_points(
        BUCHAREST_BOUNDS["lat_min"], BUCHAREST_BOUNDS["lat_max"],
        BUCHAREST_BOUNDS["lon_min"], BUCHAREST_BOUNDS["lon_max"],
        resolution
    )
    
    # Filter: gaps that have at least one neighbor within range
    gap_points = []
    for point in all_points:
        coord = (round(point.lat, 6), round(point.lon, 6))
        
        # Skip if already has sensor
        if coord in existing_coords:
            continue
        
        # Check if any sensor is within max_neighbor_distance_km
        has_nearby_neighbor = False
        for slat, slon in sensor_locations:
            dist = haversine(point.lat, point.lon, slat, slon)
            if dist <= max_neighbor_distance_km:
                has_nearby_neighbor = True
                break
        
        if has_nearby_neighbor:
            gap_points.append(point)
    
    logger.info(f"Gap fill: {len(all_points)} grid points, {len(existing_coords)} have sensors, "
                f"{len(gap_points)} gaps with neighbors within {max_neighbor_distance_km}km")
    
    if not gap_points:
        return {
            "message": "No gaps to fill near existing sensors",
            "total_points": len(all_points),
            "covered_points": len(existing_coords),
            "gaps_filled": 0,
            "calculation_time_ms": round((time.time() - start_time) * 1000, 2)
        }
    
    # Limit predictions per call
    max_predictions = 300
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
        "total_points": len(all_points),
        "covered_points": len(existing_coords),
        "gaps_found": len(gap_points),
        "gaps_filled": inserted_count,
        "station_count": len(station_state),
        "max_neighbor_distance_km": max_neighbor_distance_km,
        "calculation_time_ms": calc_time
    }
