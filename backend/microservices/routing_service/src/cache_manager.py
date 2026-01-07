import redis
import json
import hashlib
import logging
from typing import Optional
from .config import get_config
from .models import RouteResponse

logger = logging.getLogger(__name__)

class CacheManager:
    """Redis cache manager for route responses"""
    
    def __init__(self):
        self.config = get_config()
        try:
            self.redis_client = redis.Redis(
                host=self.config["redis_host"],
                port=self.config["redis_port"],
                db=self.config["redis_db"],
                decode_responses=True,
                socket_connect_timeout=5
            )
            # Test connection
            self.redis_client.ping()
            self.connected = True
            logger.info(f"Connected to Redis at {self.config['redis_host']}:{self.config['redis_port']}")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Caching disabled.")
            self.connected = False
    
    def generate_cache_key(self, start, goal, alpha, sensor_types) -> str:
        """Generate cache key from request parameters"""
        key_data = f"{start.lat},{start.lon}|{goal.lat},{goal.lon}|{alpha}|{sorted(sensor_types)}"
        return f"route:{hashlib.md5(key_data.encode()).hexdigest()}"
    
    def get_cached_route(self, cache_key: str) -> Optional[dict]:
        """Get cached route if exists"""
        if not self.connected:
            return None
        
        try:
            cached = self.redis_client.get(cache_key)
            if cached:
                logger.info(f"Cache HIT: {cache_key}")
                return json.loads(cached)
            logger.debug(f"Cache MISS: {cache_key}")
            return None
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None
    
    def cache_route(self, cache_key: str, route_data: dict, ttl: Optional[int] = None):
        """Cache route response"""
        if not self.connected:
            return
        
        try:
            ttl = ttl or self.config["cache_ttl"]
            self.redis_client.setex(
                cache_key,
                ttl,
                json.dumps(route_data)
            )
            logger.info(f"Cached route: {cache_key} (TTL={ttl}s)")
        except Exception as e:
            logger.error(f"Cache set error: {e}")
    
    def is_connected(self) -> bool:
        """Check if Redis is connected"""
        return self.connected
