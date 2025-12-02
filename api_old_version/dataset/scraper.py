import requests
import pandas as pd
import numpy as np

# Coordonate grid pentru București
coordinates = [
    (44.52, 25.98), (44.52, 26.10), (44.52, 26.22),
    (44.44, 25.98), (44.44, 26.10), (44.44, 26.22),
    (44.36, 25.98), (44.36, 26.10), (44.36, 26.22)
]

variables = {
    "temperature_2m": "Temperature",
    "relative_humidity_2m": "Humidity",
    "surface_pressure": "Pressure",
    "carbon_dioxide": "CO2",
    "pm10": "PM10",
    "pm2_5": "PM2.5",
}

air_quality_variables = ["pm10", "pm2_5", "carbon_dioxide"]

# Funcție pentru a crea timestamp-ul din data și ora
def create_timestamp(date, hour):
    return pd.to_datetime(date + " " + hour + ":00")

# # Open-Meteo API pentru fiecare punct de pe grid
def get_open_meteo_data():
    dfs = []
    for lat, lon in coordinates:
        pollutants = {}
        times = []
        for var in variables:
            url = "https://archive-api.open-meteo.com/v1/archive"
            if var in air_quality_variables:
                url = "https://air-quality-api.open-meteo.com/v1/air-quality"
            params = {
                "latitude": lat,
                "longitude": lon,
                "start_date": "2024-02-27",
                "end_date": "2025-02-27",
                "hourly": var,
                "timezone": "Europe/Bucharest"
            }
            response = requests.get(url, params=params)
            data = response.json()

            if "hourly" in data:
                if var == "carbon_dioxide" and "carbon_dioxide" in data["hourly"] and data["hourly"]["carbon_dioxide"]:
                    print(f"CO2 Data found for lat: {lat}, lon: {lon}")
                    values = data["hourly"]["carbon_dioxide"]
                elif var == "carbon_dioxide" and "carbon_dioxide" not in data["hourly"]:
                    print(f"No CO2 data found for lat: {lat}, lon: {lon}")
                values = data["hourly"][var]
                pollutants[variables[var]] = values
                if not times:
                    times = data["hourly"]["time"]
            else:
                pollutants[variables[var]] = []  # Dacă nu există date pentru această variabilă
        # Creăm dataframe-ul pentru această locație
        df = pd.DataFrame(pollutants)
        
        # Adăugăm coloanele de 'date' și 'hour' din timestamp-ul primit
        df["date"] = [t.split("T")[0] for t in times]
        df["hour"] = [t.split("T")[1].split(":")[0] for t in times]
        
        # Creăm coloana 'Timestamp' folosind datele și orele
        df["Timestamp"] = [create_timestamp(date, hour) for date, hour in zip(df["date"], df["hour"])]
        
        # Adăugăm coordonatele
        df["latitude"] = lat
        df["longitude"] = lon
        
        # Eliminăm coloanele de 'date' și 'hour'
        df = df.drop(columns=["date", "hour"])

        # Reorganizăm coloanele pentru a fi în ordinea dorită
        df = df[["Timestamp", "latitude", "longitude", "Temperature", "Humidity", "Pressure", "CO2", "PM10", "PM2.5"]]
        
        dfs.append(df)

    # Concatenare
    result_df = pd.concat(dfs, ignore_index=True)
    return result_df


# Open-Meteo API pentru fiecare punct de pe grid
def get_open_meteo_get_CO2():
    dfs = []
    for lat, lon in coordinates:
        pollutants = {}
        times = []
        url = "https://air-quality-api.open-meteo.com/v1/air-quality"
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": "2024-10-27",
            "end_date": "2025-02-27",
            "hourly": "carbon_dioxide",
            "timezone": "Europe/Bucharest"
        }
        response = requests.get(url, params=params)
        data = response.json()

        if "hourly" in data and data["hourly"]["carbon_dioxide"] != None:
            values = data["hourly"]["carbon_dioxide"]
            print(values[0])
            pollutants[variables["carbon_dioxide"]] = values
            if not times:
                times = data["hourly"]["time"]
        else:
            print("no values for {lat} {lon}")
            pollutants[variables["carbon_dioxide"]] = []  # Dacă nu există date pentru această variabilă
        # Creăm dataframe-ul pentru această locație
        df = pd.DataFrame(pollutants)
        
        # Adăugăm coloanele de 'date' și 'hour' din timestamp-ul primit
        df["date"] = [t.split("T")[0] for t in times]
        df["hour"] = [t.split("T")[1].split(":")[0] for t in times]
        
        # Creăm coloana 'Timestamp' folosind datele și orele
        df["Timestamp"] = [create_timestamp(date, hour) for date, hour in zip(df["date"], df["hour"])]
        
        # Adăugăm coordonatele
        df["latitude"] = lat
        df["longitude"] = lon
        
        # Eliminăm coloanele de 'date' și 'hour'
        df = df.drop(columns=["date", "hour"])

        # Reorganizăm coloanele pentru a fi în ordinea dorită
        df = df[["Timestamp", "latitude", "longitude", "CO2"]]
        
        dfs.append(df)

    # Concatenare
    result_df = pd.concat(dfs, ignore_index=True)
    return result_df


# Funcție principală pentru combinarea și salvarea datelor
def main():
    df_meteo = get_open_meteo_data()
    # df_aq = get_openaq_data()

    # Convertim timestamp-urile pentru aliniere
    df_meteo["Timestamp"] = pd.to_datetime(df_meteo["Timestamp"])
    df_meteo.to_csv("bucharest_open_meteo_CO2.csv", index=False)
    print("Datele pentru întreg Bucureștiul au fost salvate în 'bucharest_air_quality_full.csv'.")

if __name__ == "__main__":
    main()
