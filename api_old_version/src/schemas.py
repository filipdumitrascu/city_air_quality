from pydantic import BaseModel, Field
from typing import List
from typing import List, Optional
from fastapi import Query

class Location(BaseModel):
    latitude: float
    longitude: float

class DataPoint(BaseModel):
    dimension: str = Field(..., min_length=1)
    value: float

class SensorIngest(BaseModel):
    clientId: str = Field(..., min_length=1)
    timestamp: int
    location: Location
    data: List[DataPoint]

class GetMeasurementsRequest(BaseModel):
    latitude: float
    longitude: float
    radius: int = Query(..., gt=0),
    layers: Optional[List[str]] = Query(None)