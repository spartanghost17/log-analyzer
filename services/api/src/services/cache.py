"""
Cache Service
Redis-based caching for API responses
"""

import json
from typing import Optional, Any

import redis.asyncio as redis

from ..settings import get_logger

logger = get_logger(__name__)


class CacheService:
    """Service for Redis caching operations"""

    def __init__(self):
        self.logger = logger.bind(component="cache_service")
        self.redis_host = "redis"
        self.redis_port = 6379
        self.client: Optional[redis.Redis] = None
        self.default_ttl = 300  # 5 minutes

    async def connect(self):
        """Initialize Redis connection"""
        self.logger.info("connecting_to_redis")

        try:
            self.client = await redis.from_url(
                f"redis://{self.redis_host}:{self.redis_port}",
                encoding="utf-8",
                decode_responses=True
            )

            # Test connection
            await self.client.ping()
            self.logger.info("redis_connected")

        except Exception as e:
            self.logger.error("redis_connection_failed", error=str(e))
            # Don't fail - caching is optional
            self.client = None

    async def disconnect(self):
        """Close Redis connection"""
        self.logger.info("disconnecting_from_redis")

        if self.client:
            await self.client.close()

        self.logger.info("redis_disconnected")

    async def check_health(self) -> bool:
        """Check Redis health"""
        try:
            if self.client:
                await self.client.ping()
                return True
            return False
        except Exception as e:
            self.logger.error("redis_health_check_failed", error=str(e))
            return False

    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        if not self.client:
            return None

        try:
            value = await self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            self.logger.error("cache_get_failed", key=key, error=str(e))
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set value in cache

        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time to live in seconds (default: 300)

        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            return False

        try:
            serialized = json.dumps(value)
            await self.client.setex(
                key,
                ttl or self.default_ttl,
                serialized
            )
            return True
        except Exception as e:
            self.logger.error("cache_set_failed", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """
        Delete key from cache

        Args:
            key: Cache key to delete

        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            return False

        try:
            await self.client.delete(key)
            return True
        except Exception as e:
            self.logger.error("cache_delete_failed", key=key, error=str(e))
            return False

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all keys matching a pattern

        Args:
            pattern: Redis key pattern (e.g., "logs:*")

        Returns:
            Number of keys deleted
        """
        if not self.client:
            return 0

        try:
            keys = []
            async for key in self.client.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                return await self.client.delete(*keys)
            return 0
        except Exception as e:
            self.logger.error("cache_invalidate_failed", pattern=pattern, error=str(e))
            return 0

    def cache_key(self, prefix: str, **kwargs) -> str:
        """
        Generate cache key from prefix and parameters

        Args:
            prefix: Key prefix
            **kwargs: Key-value pairs to include in key

        Returns:
            Cache key string
        """
        parts = [prefix]
        for k, v in sorted(kwargs.items()):
            if v is not None:
                parts.append(f"{k}:{v}")
        return ":".join(parts)