import redis
import json
import hashlib
from typing import Optional, Dict, Any
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

class CacheManager:
    """
    Redis cache manager for routing service.
    Caches:
    1. Pre-computed graphs (expensive to build)
    2. Popular routes (common queries)
    3. Algorithm results
    """
    
    def __init__(self, redis_host: str = "redis", redis_port: int = 6379):
        try:
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5
            )
            self.redis_client.ping()
            logger.info(f"Redis connected: {redis_host}:{redis_port}")
        except redis.ConnectionError as e:
            logger.warning(f"Redis connection failed: {e}. Running without cache.")
            self.redis_client = None
    
    def get_cached_route(self, 
                        start_lat: float, start_lon: float,
                        end_lat: float, end_lon: float,
                        algorithm: str,
                        time_window: int) -> Optional[Dict]:
        """
        Get cached route.
        Key format: route:{hash}
        """
        if not self.redis_client:
            return None
        
        try:
            cache_key = self._generate_route_key(
                start_lat, start_lon, end_lat, end_lon, 
                algorithm, time_window)
            
            cached = self.redis_client.get(cache_key)
            if cached:
                logger.info(f"Cache HIT: {cache_key}")
                self._increment_stat("hits")
                return json.loads(cached)
            
            logger.info(f"Cache MISS: {cache_key}")
            self._increment_stat("misses")
            return None
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None
    
    def cache_route(self, 
                   start_lat: float, start_lon: float,
                   end_lat: float, end_lon: float,
                   algorithm: str,
                   time_window: int, 
                   route_data: Dict,
                   ttl_minutes: int = 15):
        """
        Cache route result with TTL.
        TTL: 15 minutes (pollution data changes)
        """
        if not self.redis_client:
            return
        
        try:
            cache_key = self._generate_route_key(
                start_lat, start_lon, end_lat, end_lon,
                algorithm, time_window)
            
            self.redis_client.setex(
                cache_key,
                timedelta(minutes=ttl_minutes),
                json.dumps(route_data)
            )
            logger.info(f"Cached route: {cache_key} (TTL: {ttl_minutes}m)")
        except Exception as e:
            logger.error(f"Cache set error: {e}")
    
    def get_cached_graph(self, time_window: int) -> Optional[Dict]:
        """
        Get cached graph data.
        Graphs are expensive to build, cache for 30 min.
        """
        if not self.redis_client:
            return None
        
        try:
            cache_key = f"graph:{time_window}h"
            cached = self.redis_client.get(cache_key)
            
            if cached:
                logger.info(f"Graph cache HIT: {cache_key}")
                return json.loads(cached)
            
            logger.info(f"Graph cache MISS: {cache_key}")
            return None
        except Exception as e:
            logger.error(f"Graph cache get error: {e}")
            return None
    
    def cache_graph(self, time_window: int, graph_data: Dict, ttl_minutes: int = 30):
        """Cache graph data."""
        if not self.redis_client:
            return
        
        try:
            cache_key = f"graph:{time_window}h"
            self.redis_client.setex(
                cache_key,
                timedelta(minutes=ttl_minutes),
                json.dumps(graph_data)
            )
            logger.info(f"Cached graph: {cache_key} (TTL: {ttl_minutes}m)")
        except Exception as e:
            logger.error(f"Graph cache set error: {e}")
    
    def get_stats(self) -> Dict:
        """Get cache statistics."""
        if not self.redis_client:
            return {"error": "Redis not connected"}
        
        try:
            hits = int(self.redis_client.get("stats:routing:hits") or 0)
            misses = int(self.redis_client.get("stats:routing:misses") or 0)
            total = hits + misses
            hit_rate = (hits / total * 100) if total > 0 else 0
            
            return {
                "hits": hits,
                "misses": misses,
                "total_requests": total,
                "hit_rate_percent": round(hit_rate, 2)
            }
        except Exception as e:
            logger.error(f"Stats error: {e}")
            return {"error": str(e)}
    
    def clear_cache(self):
        """Clear all routing cache (for testing)."""
        if not self.redis_client:
            return
        
        try:
            pattern = "route:*"
            for key in self.redis_client.scan_iter(pattern):
                self.redis_client.delete(key)
            
            pattern = "graph:*"
            for key in self.redis_client.scan_iter(pattern):
                self.redis_client.delete(key)
            
            logger.info("Cache cleared")
        except Exception as e:
            logger.error(f"Cache clear error: {e}")
    
    def _generate_route_key(self, 
                           start_lat: float, start_lon: float,
                           end_lat: float, end_lon: float,
                           algorithm: str,
                           time_window: int) -> str:
        """
        Generate cache key for route.
        Round coordinates to 3 decimals (~100m precision).
        """
        start_rounded = f"{start_lat:.3f},{start_lon:.3f}"
        end_rounded = f"{end_lat:.3f},{end_lon:.3f}"
        key_string = f"{start_rounded}|{end_rounded}|{algorithm}|{time_window}"
        
        key_hash = hashlib.md5(key_string.encode()).hexdigest()[:16]
        return f"route:{key_hash}"
    
    def _increment_stat(self, stat_type: str):
        """Increment cache statistics."""
        if not self.redis_client:
            return
        
        try:
            key = f"stats:routing:{stat_type}"
            self.redis_client.incr(key)
        except Exception as e:
            logger.error(f"Stat increment error: {e}")
