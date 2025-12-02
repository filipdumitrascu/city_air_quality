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

class InsertPollutionDataRequest(BaseModel):
    clientId: str = Field(..., min_length=1)
    timestamp: str = Field(..., min_length=1)
    location: Location
    data: List[DataPoint]

class InsertPollutionDataResponse(BaseModel):
    success: bool
    message: str

class GetMeasurementsRequest(BaseModel):
    latitude: float
    longitude: float
    radius: int = Query(..., ge=0),
    layers: Optional[List[str]] = Query(None) 