from fastapi import FastAPI, HTTPException
from database import execute_query
from schemas import SensorIngest,GetMeasurementsRequest
from datetime import datetime
import pytz
import logging

logging.basicConfig(level=logging.DEBUG, filename='app.log', filemode='w')

app = FastAPI()

def validate_coordinates_and_radius(data: GetMeasurementsRequest):
    # Verifică dacă latitudinea este între -90 și 90
    if not (-90 <= data.latitude <= 90):
        raise HTTPException(status_code=400, detail="latitude must be between -90 and 90")
    
    # Verifică dacă longitudinea este între -180 și 180
    if not (-180 <= data.longitude <= 180):
        raise HTTPException(status_code=400, detail="longitude must be between -180 and 180")
    
    # Verifică dacă raza este un număr pozitiv
    if data.radius < 0:
        raise HTTPException(status_code=400, detail="radius must be a positive number")


@app.post("/ingest/")
async def ingest_data(payload: SensorIngest):
    try:
        print("Received payload:", payload)
        # # Convertim timestamp-ul la format ISO (ajustat pentru fusul orar)
        # utc_time = payload.timestamp + 7200000  # Ajustare fus orar
        # isoTimestamp = datetime.fromtimestamp(utc_time / 1000).replace(tzinfo=pytz.UTC).isoformat()
        utc_time = payload.timestamp + 7200000  # Ajustare fus orar pentru UTC+2
        utc_dt = datetime.fromtimestamp(utc_time / 1000)  # Obținem datetime în UTC

        # Adăugăm fusul orar
        isoTimestamp = pytz.utc.localize(utc_dt).isoformat()

        Temperature = None
        Humidity = None
        Pressure = None
        Altitude = None
        CO2 = None
        PM1_0 = None
        PM2_5 = None
        PM10 = None

        for entry in payload.data:
            if entry.dimension == "Temperature":
                Temperature = entry.value
            elif entry.dimension == "Humidity":
                Humidity = entry.value
            elif entry.dimension == "Pressure":
                Pressure = entry.value
            elif entry.dimension == "Altitude":
                Altitude = entry.value
            elif entry.dimension == "CO2":
                CO2 = entry.value
            elif entry.dimension == "PM1.0":
                PM1_0 = entry.value
            elif entry.dimension == "PM2.5":
                PM2_5 = entry.value
            elif entry.dimension == "PM10":
                PM10 = entry.value

        query = """INSERT INTO pollution_data 
                (Client, Timestamp, Latitude, Longitude, Temperature, Humidity, Pressure, Altitude, CO2, PM1_0, PM2_5, PM10)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""

        params = (
            payload.clientId,
            isoTimestamp,
            payload.location.latitude,
            payload.location.longitude,
            Temperature,
            Humidity,
            Pressure,
            Altitude,
            CO2,
            PM1_0,
            PM2_5,
            PM10
        )

        execute_query(query, params)

        return {"success": True}

    except Exception as e:
        logging.error(f"{str(e)}")
        raise HTTPException(status_code=400, detail=f"{str(e)}")

@app.get("/measurements/")
async def get_measurements(data: GetMeasurementsRequest):
    try:
        validate_coordinates_and_radius(data)
        available_layers = ["Temperature", "Humidity", "Pressure", "Altitude", "CO2", "PM1_0", "PM2_5", "PM10"]
        selected_layers = data.layers if data.layers else available_layers
        
        query = f"""
        SELECT Client, Timestamp, Latitude, Longitude, {', '.join(selected_layers)} 
        FROM pollution_data
        WHERE ABS(Latitude - %s) <= %s AND ABS(Longitude - %s) <= %s
        """
        params = (data.latitude, data.radius, data.longitude, data.radius)

        results = execute_query(query, params)
        formatted_results = []
        for row in results:
            client_id, timestamp, latitude, longitude, *sensor_values = row

            sensor_data = [
                {"dimension": sensor, "value": value} 
                for sensor, value in zip(selected_layers, sensor_values) if value is not None
            ]

            formatted_results.append({
                "clientId": client_id,
                "timestamp": int(timestamp.timestamp() * 1000),  # Convertim timestamp la milisecunde
                "location": {
                    "latitude": latitude,
                    "longitude": longitude
                },
                "data": sensor_data
            })

        return {"data": formatted_results}

    except Exception as e:
        logging.error(f"{str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching measurements: {str(e)}")