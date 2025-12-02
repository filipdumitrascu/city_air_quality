import os
import psycopg2
from dotenv import load_dotenv
from fastapi import HTTPException
import logging
# Încarcă variabilele de mediu din fișierul .env
load_dotenv()

# Detalii pentru conectare
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT', 8812)
DB_NAME = os.getenv('DB_NAME')

# Funcție pentru a crea o conexiune la baza de date
def get_db_connection():
    try:
        connection = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            dbname=DB_NAME
        )
        return connection
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error during database connection: {str(e)}")

#de modificat conexiunea la baza de date sa nu se deschida si sa se inchida de fiecare data
def execute_query(query, params=None):
    try:
        logging.info(f"Executing query AICI: {query} {params}")
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(query, params)

        logging.info(f"Query executed successfully")

        # Verificăm dacă interogarea este de tip SELECT pentru a returna rezultate
        if query.strip().upper().startswith("SELECT"):
            results = cursor.fetchall()  # Extragem toate datele
        else:
            logging.info(f"before commit")
            conn.commit()
            results = None  # Nu returnăm nimic pentru interogări de tip INSERT/UPDATE/DELETE

        cursor.close()
        conn.close()
        return results  # Returnăm rezultatele interogării (sau None dacă nu e SELECT)

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error during query execution: {str(e)}")