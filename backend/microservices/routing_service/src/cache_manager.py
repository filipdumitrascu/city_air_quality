import redis
import json
import hashlib
import logging
from typing import Optional
from .config import get_config

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
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # Test connection
            self.redis_client.ping()
            self.connected = True
            logger.info(f"Redis connected at {self.config['redis_host']}:{self.config['redis_port']}")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Caching disabled.")
            self.connected = False
    
    def generate_cache_key(self, start, goal, alpha, sensor_types, heuristic: str = "haversine") -> str:
        """
        Generate unique cache key from request parameters
        
        Args:
            start: Start coordinate
            goal: Goal coordinate
            alpha: Pollution weight
            sensor_types: List of sensor types
            heuristic: Heuristic function name
        
        Returns:
            Cache key string (e.g., 'route:abc123')
        """
        # Round coordinates to 4 decimals for consistent caching
        # Include heuristic in cache key
        key_data = f"{start.lat:.4f},{start.lon:.4f}|{goal.lat:.4f},{goal.lon:.4f}|{alpha:.2f}|{sorted(sensor_types)}|{heuristic}"
        hash_hex = hashlib.md5(key_data.encode()).hexdigest()
        return f"route:{hash_hex}"
    
    def get_cached_route(self, cache_key: str) -> Optional[dict]:
        """
        Get cached route if exists
        
        Args:
            cache_key: Cache key
        
        Returns:
            Cached route data or None
        """
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
        """
        Cache route response
        
        Args:
            cache_key: Cache key
            route_data: Route data to cache
            ttl: Time to live in seconds (default from config)
        """
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
        if not self.connected:
            return False
        
        try:
            self.redis_client.ping()
            return True
        except:
            return False
