# src/data_loader.py - Load Real Pollution Data from QuestDB

import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


class PollutionDataLoader:
    """
    Load pollution data from QuestDB.
    Supports filtering by sensor type (fixed vs mobile).
    """
    
    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or os.getenv(
            "DATABASE_URL",
            "postgresql://admin:quest@localhost:8812/qdb"
        )
        self.conn = None
    
    def connect(self):
        if self.conn is None or self.conn.closed:
            try:
                self.conn = psycopg2.connect(self.db_url)
                logger.info("Connected to QuestDB")
            except Exception as e:
                logger.error(f"Database connection failed: {e}")
                raise
    
    def disconnect(self):
        if self.conn and not self.conn.closed:
            self.conn.close()
    
    def fetch_fixed_sensors(self, time_window_hours: int = 1) -> List[Dict]:
        """Get data from stationary sensors only."""
        self.connect()
        
        cutoff_time = datetime.now() - timedelta(hours=time_window_hours)
        
        query = """
            SELECT 
                latitude as lat,
                longitude as lon,
                pm10,
                pm25,
                no2,
                timestamp
            FROM sensor_readings
            WHERE sensor_type = 'fixed'
                AND timestamp >= %s
                AND latitude BETWEEN 44.35 AND 44.50
                AND longitude BETWEEN 26.00 AND 26.20
            ORDER BY timestamp DESC
        """
        
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (cutoff_time,))
                results = cur.fetchall()
                logger.info(f"Fetched {len(results)} fixed sensor readings")
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error fetching fixed sensors: {e}")
            return []
    
    def fetch_mobile_sensors(self, time_window_hours: int = 1) -> List[Dict]:
        """Get data from mobile sensors (denser coverage)."""
        self.connect()
        
        cutoff_time = datetime.now() - timedelta(hours=time_window_hours)
        
        query = """
            SELECT 
                latitude as lat,
                longitude as lon,
                pm10,
                pm25,
                no2,
                timestamp
            FROM sensor_readings
            WHERE sensor_type = 'mobile'
                AND timestamp >= %s
                AND latitude BETWEEN 44.35 AND 44.50
                AND longitude BETWEEN 26.00 AND 26.20
            ORDER BY timestamp DESC
        """
        
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (cutoff_time,))
                results = cur.fetchall()
                logger.info(f"Fetched {len(results)} mobile sensor readings")
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error fetching mobile sensors: {e}")
            return []
    
    def fetch_all(self, time_window_hours: int = 1) -> List[Dict]:
        """Fetch both fixed and mobile sensors."""
        fixed = self.fetch_fixed_sensors(time_window_hours)
        mobile = self.fetch_mobile_sensors(time_window_hours)
        
        all_data = fixed + mobile
        logger.info(f"Total: {len(all_data)} (fixed: {len(fixed)}, mobile: {len(mobile)})")
        
        return all_data
