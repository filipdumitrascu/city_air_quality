from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal
import time


def get_current_timestamp_ms() -> int:
    """Get current Unix timestamp in milliseconds."""
    return int(time.time() * 1000)


class InsertPollutionDataRequest(BaseModel):
    """
    Request model for inserting sensor data.
    
    Required: sensor_type, latitude, longitude
    Optional: sensor_id (None for Forecast), timestamp (default: current time)
    """
    # Required fields
    sensor_type: Literal["CityAirQ", "WearAware", "SPO-RO", "Forecast"] = Field(
        ..., description="Sensor type: CityAirQ, WearAware, SPO-RO, or Forecast"
    )
    sensor_id: Optional[str] = Field(
        default=None, description="Sensor identifier (e.g., '001'). None for Forecast."
    )
    timestamp: Optional[int] = Field(
        default=None, description="Unix timestamp in milliseconds. Default: current time."
    )
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
    
    # Convert explicit null values to -1
    @field_validator('altitude', 'humidity', 'pressure', 'temperature',
                     'co', 'co2', 'no2', 'nh3', 'vocs', 'pm1_0', 'pm2_5', 'pm10',
                     mode='before')
    @classmethod
    def null_to_default(cls, v):
        return -1 if v is None else v


class InsertPollutionDataResponse(BaseModel):
    """Response model for successful insertion."""
    success: bool
    sensor_type: str
    sensor_id: Optional[str] = None


class SensorReading(BaseModel):
    """Model for a single sensor reading."""
    sensor_type: str
    sensor_id: Optional[str] = None
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
