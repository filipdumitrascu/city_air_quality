from pydantic import BaseModel, Field
from typing import List, Optional


class InsertPollutionDataRequest(BaseModel):
    """
    Request model for inserting sensor data.
    
    Required: sensor_id, sensor_type, timestamp, latitude, longitude
    Optional: All other fields default to -1 (no data)
    """
    # Required fields
    sensor_id: str = Field(..., min_length=1, description="Sensor identifier (e.g., 'CityAirQ_001')")
    sensor_type: str = Field(..., description="Sensor type: 'fixed', 'mobile', 'predicted'")
    timestamp: int = Field(..., description="Unix timestamp in milliseconds")
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    
    # Optional - Weather data (BME680)
    altitude: float = Field(default=-1, description="Altitude in meters")
    humidity: float = Field(default=-1, description="Relative humidity %")
    pressure: float = Field(default=-1, description="Atmospheric pressure hPa")
    temperature: float = Field(default=-1, description="Temperature in Celsius")
    
    # Optional - Gas sensors
    co: float = Field(default=-1, description="Carbon monoxide")
    co2: float = Field(default=-1, description="Carbon dioxide")
    no2: float = Field(default=-1, description="Nitrogen dioxide")
    nh3: float = Field(default=-1, description="Ammonia")
    vocs: float = Field(default=-1, description="Volatile organic compounds")
    
    # Optional - Particulate matter
    pm1_0: float = Field(default=-1, description="PM1.0 ug/m3")
    pm2_5: float = Field(default=-1, description="PM2.5 ug/m3")
    pm10: float = Field(default=-1, description="PM10 ug/m3")


class InsertPollutionDataResponse(BaseModel):
    """Response model for successful insertion."""
    success: bool
    sensor_id: str


class SensorReading(BaseModel):
    """Model for a single sensor reading."""
    sensor_id: str
    sensor_type: str
    timestamp: str
    latitude: float
    longitude: float
    
    # Optional pollution data
    pm10: Optional[float] = None
    pm2_5: Optional[float] = None
    pm1_0: Optional[float] = None
    no2: Optional[float] = None
    co: Optional[float] = None
    co2: Optional[float] = None
    nh3: Optional[float] = None
    vocs: Optional[float] = None
    
    # Optional weather data
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pressure: Optional[float] = None
    altitude: Optional[float] = None
