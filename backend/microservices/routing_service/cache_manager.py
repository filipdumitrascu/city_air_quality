import redis
import json
import hashlib
import logging
from typing import Optional
from config import get_config

logger = logging.getLogger(__name__)

class CacheManager:
    """Redis cache manager for route responses"""
    
    def __init__(self):
        self.config = get_config()
        self.connected = False
        self.redis_client = None
        
        try:
            self.redis_client = redis.Redis(
                host=self.config["redis_host"],
                port=self.config["redis_port"],
                db=self.config["redis_db"],
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            self.redis_client.ping()
            self.connected = True
            logger.info(f"Redis connected at {self.config['redis_host']}:{self.config['redis_port']}")
        except Exception as e:
            logger.warning(f"Redis unavailable: {e}")
    
    def generate_cache_key(self, start, goal, alpha: float, 
                           sensor_types: list, mode_heuristic: str) -> str:
        """Generate unique cache key"""
        key_data = json.dumps({
            "start": [round(start.lat, 4), round(start.lon, 4)],
            "goal": [round(goal.lat, 4), round(goal.lon, 4)],
            "alpha": round(alpha, 2),
            "sensors": sorted(sensor_types),
            "mode": mode_heuristic
        }, sort_keys=True)
        
        hash_hex = hashlib.md5(key_data.encode()).hexdigest()
        return f"route:{hash_hex}"
    
    def get_cached_route(self, cache_key: str) -> Optional[dict]:
        """Get cached route if exists"""
        if not self.connected:
            return None
        
        try:
            cached = self.redis_client.get(cache_key)
            if cached:
                logger.info(f"Cache HIT: {cache_key}")
                return json.loads(cached)
            return None
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None
    
    def cache_route(self, cache_key: str, route_data: dict, ttl: int = None):
        """Cache route response"""
        if not self.connected:
            return
        
        try:
            ttl = ttl or self.config["cache_ttl"]
            self.redis_client.setex(cache_key, ttl, json.dumps(route_data))
            logger.info(f"Cached: {cache_key} (TTL={ttl}s)")
        except Exception as e:
            logger.error(f"Cache set error: {e}")
    
    def is_connected(self) -> bool:
        """Check Redis connection"""
        if not self.connected or not self.redis_client:
            return False
        try:
            self.redis_client.ping()
            return True
        except:
            return False
