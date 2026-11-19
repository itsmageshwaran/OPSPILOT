"""
Redis Caching & Distributed Synchronization Layer for OpsPilot.
Demonstrates:
1. Cache-Aside pattern with TTL expiration
2. Active cache invalidation upon data mutation
3. Distributed Locking via Redis SETNX with TTL to prevent duplicate execution
4. In-memory fallback with TTL support when local Redis server is unavailable
"""

import os
import time
import json
import logging
from typing import Optional, Any, Dict, Callable

logger = logging.getLogger("opspilot.cache")


class RedisCacheManager:
    """
    Production-ready Redis Cache Manager with automatic TTL handling,
    key invalidation, distributed locking, and graceful in-memory fallback.
    """
    def __init__(self, host: Optional[str] = None, port: Optional[int] = None):
        self.host = host or os.getenv("REDIS_HOST", "127.0.0.1")
        self.port = int(port or os.getenv("REDIS_PORT", "6379"))
        self._client = None
        self._connected = False
        self._memory_cache: Dict[str, str] = {}
        self._memory_ttls: Dict[str, float] = {}

        self._connect()

    def _connect(self):
        try:
            import redis
            client = redis.Redis(
                host=self.host,
                port=self.port,
                decode_responses=True,
                socket_connect_timeout=1.5
            )
            client.ping()
            self._client = client
            self._connected = True
            logger.info(f"Connected to Redis server at {self.host}:{self.port}")
        except Exception as e:
            self._connected = False
            logger.info(f"Redis server unavailable ({e}); utilizing in-memory cache store.")

    @property
    def is_connected(self) -> bool:
        return self._connected

    def get(self, key: str) -> Optional[str]:
        """Cache-Aside Read: Fetches cached value or returns None if expired/missing."""
        if self._connected and self._client:
            try:
                return self._client.get(key)
            except Exception:
                self._connected = False

        # In-memory fallback with TTL check
        now = time.time()
        exp = self._memory_ttls.get(key)
        if exp and now > exp:
            self._memory_cache.pop(key, None)
            self._memory_ttls.pop(key, None)
            return None
        return self._memory_cache.get(key)

    def set(self, key: str, value: str, ex: Optional[int] = 300) -> bool:
        """Cache-Aside Write: Sets key with specified TTL in seconds."""
        if self._connected and self._client:
            try:
                return bool(self._client.set(key, value, ex=ex))
            except Exception:
                self._connected = False

        self._memory_cache[key] = value
        if ex:
            self._memory_ttls[key] = time.time() + ex
        return True

    def delete(self, key: str) -> bool:
        """Cache Invalidation: Purges cached entry upon data mutation."""
        if self._connected and self._client:
            try:
                return bool(self._client.delete(key))
            except Exception:
                self._connected = False

        self._memory_cache.pop(key, None)
        self._memory_ttls.pop(key, None)
        return True

    def acquire_lock(self, key: str, ttl: int = 30) -> bool:
        """
        Distributed Lock Acquisition using Redis SETNX with TTL.
        Prevents race conditions and duplicate cron/batch executions.
        """
        if self._connected and self._client:
            try:
                return bool(self._client.set(key, "locked", nx=True, ex=ttl))
            except Exception:
                self._connected = False

        now = time.time()
        exp = self._memory_ttls.get(key)
        if exp and now < exp:
            return False
        self._memory_cache[key] = "locked"
        self._memory_ttls[key] = now + ttl
        return True

    def release_lock(self, key: str) -> bool:
        """Releases the distributed lock."""
        return self.delete(key)

    def get_stats(self) -> Dict[str, Any]:
        """Returns caching diagnostics and keyspace statistics."""
        return {
            "connected_to_real_redis": self._connected,
            "host": self.host,
            "port": self.port,
            "cached_keys_count": len(self._memory_cache) if not self._connected else "managed_by_redis_server",
            "active_mode": "Real Redis Server" if self._connected else "In-Memory LRU Cache Fallback"
        }


# Global singleton cache instance
cache_manager = RedisCacheManager()
