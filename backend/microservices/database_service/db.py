from config import get_db_config
import logging
import os
from psycopg2 import pool
from fastapi import HTTPException

logging.basicConfig(
    level=logging.DEBUG, 
    filename=os.path.join('logs', 'database_service.log'),
    filemode='w', 
    format='%(asctime)s - %(levelname)s - %(message)s'
)

db_pool = None

def init_db():
    """Inițializează pool-ul de conexiuni la baza de date."""
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
        raise HTTPException(status_code=500, detail="Database connection failed")

def close_db():
    """Închide toate conexiunile din pool la shutdown."""
    global db_pool
    if db_pool:
        db_pool.closeall()
        logging.info("Database connection pool closed")

def get_db_connection():
    """Obține o conexiune din pool."""
    global db_pool
    if not db_pool:
        raise HTTPException(status_code=500, detail="Database pool not initialized")
    try:
        conn = db_pool.getconn()
        if conn.closed:
            logging.warning("Connection was closed. Retrying...")
            conn = db_pool.getconn()
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")

def release_db_connection(conn):
    """Eliberează conexiunea înapoi în pool."""
    global db_pool
    if db_pool and conn:
        db_pool.putconn(conn)

def insert_data(params=None):
    """Execută un INSERT în baza de date folosind o conexiune din pool."""
    conn = None
    try:
        query = """INSERT INTO pollution_data 
            (Client, Timestamp, Latitude, Longitude, Temperature, Humidity, Pressure, Altitude, CO2, PM1_0, PM2_5, PM10)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
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
    """Execută un SELECT în baza de date folosind o conexiune din pool."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # query = f"""
        #     SELECT Client, Timestamp, Latitude, Longitude, {', '.join(params[0])} 
        #     FROM pollution_data
        #     WHERE ABS(Latitude - %s) <= %s AND ABS(Longitude - %s) <= %s
        # #     """
        # query = f"""
        #     SELECT Client, "Timestamp", "Latitude", "Longitude", {', '.join(params[0])}
        #     FROM (
        #         SELECT *,
        #             ROUND("Latitude", 4) AS lat_rounded,
        #             ROUND("Longitude", 4) AS lon_rounded
        #         FROM pollution_data
        #     )
        #     LATEST ON "Timestamp" PARTITION BY lat_rounded, lon_rounded
        #     WHERE ABS("Latitude" - %s) <= %s
        #     AND ABS("Longitude" - %s) <= %s
        #     ORDER BY "Timestamp" DESC
        # """
        # query = f"""
        #     SELECT Client, "Timestamp", "Latitude", "Longitude", {', '.join(params[0])}
        #     FROM (
        #         SELECT *
        #         FROM pollution_data
        #         LATEST ON "Timestamp" PARTITION BY "Latitude", "Longitude"
        #     )
        #     WHERE ABS("Latitude" - %s) <= %s
        #     AND ABS("Longitude" - %s) <= %s
        #     ORDER BY "Timestamp" DESC
        # """

        query = f"""
             SELECT "Client", 
                "Timestamp", 
                "Latitude",
                "Longitude",
                {', '.join(params[0])}
                FROM (
                    SELECT *
                    FROM (
                        SELECT *, ROUND("Latitude", 4) AS lat4, ROUND("Longitude", 4) AS lng4
                        FROM pollution_data
                    )
                    LATEST ON "Timestamp" PARTITION BY lat4, lng4
                )
                WHERE ABS(lat4 - round(CAST(%s AS DOUBLE), 4)) <= round(CAST(%s AS DOUBLE), 4)
                AND ABS(lng4 - round(CAST(%s AS DOUBLE), 4)) <= round(CAST(%s AS DOUBLE), 4)
                ORDER BY "Timestamp" DESC
        """
        cursor.execute(query, params[1:])
        results = cursor.fetchall()
  
        if not results:
            logging.info("intra aici si da raise")
            raise HTTPException(status_code=404, detail="No data found")
        cursor.close()
        return results
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        if conn:
            release_db_connection(conn)
