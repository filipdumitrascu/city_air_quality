import os
from dotenv import load_dotenv
from fastapi import HTTPException

# Încarcă variabilele de mediu din fișierul .env
load_dotenv()

def get_db_config():
    """Returnează un dicționar cu datele de configurare ale bazei de date."""
    try:
        return {
            "host": os.getenv('DB_HOST'),
            "port": os.getenv('DB_PORT', 8812),
            "user": os.getenv('DB_USER'),
            "password": os.getenv('DB_PASSWORD'),
            "dbname": os.getenv('DB_NAME')
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error loading database configuration: {str(e)}")