from config import get_db_config
from fastapi import HTTPException
from psycopg2 import pool
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

db_pool = None

# CONNECTION POOL MANAGEMENT
def init_db():
    """Initialize PostgreSQL connection pool for QuestDB."""
    global db_pool
    try:
        db_config = get_db_config()
        db_pool = pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            **db_config
        )
        if db_pool:
            logging.info("Database connection pool initialized")
        return db_pool
    except Exception as e:
        logging.error(f"Error initializing database pool: {str(e)}")
        raise RuntimeError("Database connection failed")

def close_db():
    """Close all pool connections."""
    global db_pool
    if db_pool:
        db_pool.closeall()
        logging.info("Database connection pool closed")

def get_db_connection():
    """Get a connection from the pool."""
    global db_pool
    if not db_pool:
        init_db()
    try:
        conn = db_pool.getconn()
        if conn.closed:
            conn = db_pool.getconn()
        return conn
    except Exception as e:
        logging.error(f"Connection error: {str(e)}")
        raise RuntimeError("Database connection error")

def release_db_connection(conn):
    """Release connection back to pool."""
    global db_pool
    if db_pool and conn:
        db_pool.putconn(conn)


# DATA OPERATIONS
def insert_data(params):
    """
    Insert sensor data into pollution_data table.
    
    Args:
        params: Tuple with 17 values matching schema:
            (sensor_type, sensor_id, timestamp, latitude, longitude, altitude,
             humidity, pressure, temperature, co, co2, no2, nh3,
             pm1_0, pm2_5, pm10, vocs)
    """
    conn = None
    try:
        query = """
            INSERT INTO pollution_data 
            (sensor_type, sensor_id, timestamp, latitude, longitude, altitude,
             humidity, pressure, temperature, co, co2, no2, nh3,
             pm1_0, pm2_5, pm10, vocs)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        cursor.close()
        logging.info(f"Inserted data for {params[0]}/{params[1]}")
    except Exception as e:
        if conn:
            conn.rollback()
        logging.error(f"Insert failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Insert failed: {str(e)}")
    finally:
        if conn:
            release_db_connection(conn)


def fetch_data(params):
    """
    Fetch pollution data within geographic bounds.
    
    Returns only the LATEST reading per unique location (rounded to 4 decimals).
    This means:
    - Fixed sensors (SPO-RO): 1 reading per station (latest)
    - Mobile sensors (CityAirQ, WearAware): 1 reading per unique GPS position (latest)
    
    Args:
        params: Tuple containing:
            [0] layers: List of column names to retrieve
            [1] latitude: Center latitude
            [2] delta_lat: Latitude delta (radius)
            [3] longitude: Center longitude
            [4] delta_lng: Longitude delta (radius)
            [5] sensor_types: List of sensor types to filter
    
    Returns:
        List of dicts with sensor readings (deduplicated by location)
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Extract parameters
        layers = params[0]
        latitude = params[1]
        delta_lat = params[2]
        longitude = params[3]
        delta_lng = params[4]
        sensor_types = params[5] if len(params) > 5 else ['CityAirQ', 'WearAware']
        
        # Build column list - always include base columns
        base_columns = ['sensor_type', 'sensor_id', 'timestamp', 'latitude', 'longitude']
        
        # Add requested layers (validate against schema)
        valid_layers = ['pm10', 'pm2_5', 'pm1_0', 'no2', 'co', 'co2', 'nh3', 'vocs',
                        'temperature', 'humidity', 'pressure', 'altitude']
        layer_columns = [col for col in layers if col in valid_layers]
        
        all_columns = base_columns + layer_columns
        columns_str = ', '.join(all_columns)
        
        # Build sensor_type filter
        if sensor_types and len(sensor_types) == 1:
            sensor_filter = f"AND sensor_type = '{sensor_types[0]}'"
        elif sensor_types and len(sensor_types) > 1:
            types_str = "', '".join(sensor_types)
            sensor_filter = f"AND sensor_type IN ('{types_str}')"
        else:
            sensor_filter = ""
        
        # Calculate bounds
        lat_min = latitude - delta_lat
        lat_max = latitude + delta_lat
        lon_min = longitude - delta_lng
        lon_max = longitude + delta_lng
        
        # Query: Get all data in bounds, then deduplicate per location in Python
        # QuestDB doesn't support ROW_NUMBER() OVER, so we fetch and dedupe
        query = f"""
            SELECT {columns_str}
            FROM pollution_data
            WHERE latitude >= %s AND latitude <= %s
              AND longitude >= %s AND longitude <= %s
              {sensor_filter}
            ORDER BY timestamp DESC
            LIMIT 10000
        """
        
        cursor.execute(query, (lat_min, lat_max, lon_min, lon_max))
        rows = cursor.fetchall()
        
        if not rows:
            logging.info("No data found for query")
            raise HTTPException(status_code=404, detail="No data found")
        
        # Deduplicate: keep only latest reading per location (4 decimal precision)
        # 4 decimals = ~11 meters precision
        location_map = {}
        
        for row in rows:
            result = {}
            for i, col in enumerate(all_columns):
                value = row[i]
                if col == 'timestamp' and value:
                    result[col] = str(value)
                else:
                    result[col] = value
            
            # Create location key (rounded to 4 decimals)
            lat_key = round(result['latitude'], 4)
            lon_key = round(result['longitude'], 4)
            location_key = (lat_key, lon_key)
            
            # Keep only the first (most recent due to ORDER BY DESC)
            if location_key not in location_map:
                location_map[location_key] = result
        
        results = list(location_map.values())
        
        cursor.close()
        logging.info(f"Fetched {len(rows)} rows, deduplicated to {len(results)} unique locations")
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Database error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        if conn:
            release_db_connection(conn)
