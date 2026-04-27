import os
from urllib.parse import urlparse

def get_db_config():
    """
    Parse DATABASE_URL and return connection config dict.
    
    Expected format: postgresql://user:password@host:port/dbname
    
    Returns:
        dict with host, port, user, password, dbname
    """
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set")

    parsed = urlparse(db_url)

    return {
        "host": parsed.hostname,
        "port": parsed.port or 8812,
        "user": parsed.username or "admin",
        "password": parsed.password or "quest",
        "dbname": parsed.path.lstrip("/") or "qdb"
    }
