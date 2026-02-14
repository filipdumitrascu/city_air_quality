from config import get_db_config
import logging
import os
import math
from psycopg2 import pool
from fastapi import HTTPException

logging.basicConfig(
    level=logging.DEBUG, 
    filename=os.path.join('logs', 'database_service.log'),
    filemode='w', 
    format='%(asctime)s - %(levelname)s - %(message)s'
)

db_pool = None

# Database Connection Pool
def init_db():
    """
    Initialize PostgreSQL connection pool for QuestDB.
    
    Uses SimpleConnectionPool with 1-10 connections.
    Config loaded from DATABASE_URL environment variable.
    """
    global db_pool
    try:
        db_config = get_db_config()
        db_pool = pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10, 
            **db_config
        )
        if db_pool:
            logging.info("Database connection pool initialized successfully")
        return db_pool
    except Exception as e:
        logging.error(f"Error initializing database connection pool: {str(e)}")
        raise RuntimeError("Database connection failed")

def close_db():
    """Close all pool connections when shutdown"""
    global db_pool
    if db_pool:
        db_pool.closeall()
        logging.info("Database connection pool closed")

def get_db_connection():
    """Gets a pool connection."""
    global db_pool
    if not db_pool:
        init_db()
    try:
        conn = db_pool.getconn()
        if conn.closed:
            conn = db_pool.getconn()
        return conn
    except Exception as e:
        raise RuntimeError("Database connection error")

def release_db_connection(conn):
    """Release pool connection."""
    global db_pool
    if db_pool and conn:
        db_pool.putconn(conn)


# Actions
def insert_data(params=None):
    """Execute INSERT in database using pool connection."""
    conn = None
    try:
        query = """INSERT INTO sensor_readings 
            (sensor_id, timestamp, latitude, longitude, pm10, pm25, no2)
            VALUES (%s, %s, %s, %s, %s, %s, %s)"""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        cursor.close()
    except Exception as e:
        if conn:
            conn.rollback()
        logging.error(f"Insert failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Insert failed: {str(e)}")
    finally:
        if conn:
            release_db_connection(conn)

def fetch_data(params=None):
    """
    Execute SELECT in database using pool connection.
    
    Args:
        params: Tuple containing:
            - params[0]: List of column names (layers)
            - params[1]: latitude (center)
            - params[2]: delta_lat (radius in lat degrees)
            - params[3]: longitude (center)
            - params[4]: delta_lng (radius in lon degrees)
            - params[5]: sensor_types (list of 'fixed', 'mobile')
    
    Returns:
        List of sensor readings matching the query
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
        sensor_types = params[5] if len(params) > 5 else ['fixed', 'mobile']
        
        # Build column list
        columns = ', '.join([f'"{col}"' for col in layers])
        
        # Build sensor_type filter
        # sensor_type is stored as 'fixed' or 'mobile' in the database
        if sensor_types and len(sensor_types) < 2:
            # Only one type selected
            sensor_filter = f"AND sensor_type = '{sensor_types[0]}'"
        else:
            # Both types or none specified - no filter needed
            sensor_filter = ""
        
        query = f"""
            SELECT sensor_id, 
                timestamp, 
                latitude,
                longitude,
                {columns}
            FROM (
                SELECT *
                FROM (
                    SELECT *, ROUND(latitude, 4) AS lat4, ROUND(longitude, 4) AS lng4
                    FROM sensor_readings
                    WHERE 1=1 {sensor_filter}
                )
                LATEST ON timestamp PARTITION BY lat4, lng4
            )
            WHERE ABS(lat4 - round(CAST(%s AS DOUBLE), 4)) <= round(CAST(%s AS DOUBLE), 4)
            AND ABS(lng4 - round(CAST(%s AS DOUBLE), 4)) <= round(CAST(%s AS DOUBLE), 4)
            ORDER BY timestamp DESC
        """
        
        # Execute with position parameters (latitude, delta_lat, longitude, delta_lng)
        cursor.execute(query, (latitude, delta_lat, longitude, delta_lng))
        results = cursor.fetchall()
  
        if not results:
            logging.info("No data found for query")
            raise HTTPException(status_code=404, detail="No data found")
        
        cursor.close()
        return results
        
    except HTTPException as e:
        raise e
    except Exception as e:
        logging.error(f"Database error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        if conn:
            release_db_connection(conn)
