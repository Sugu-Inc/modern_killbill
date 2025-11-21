"""Redis caching layer for performance optimization.

Provides caching utilities for frequently accessed data to reduce database load.
"""
import json
from typing import Any, Optional
from datetime import timedelta
import structlog

import redis.asyncio as redis

from billing.config import settings

logger = structlog.get_logger(__name__)


class RedisCache:
    """Redis-based caching layer."""

    def __init__(self):
        """Initialize Redis connection."""
        self.redis_client: Optional[redis.Redis] = None
        self._initialized = False

    async def _ensure_connection(self) -> redis.Redis:
        """
        Ensure Redis connection is established.

        Returns:
            Redis client instance
        """
        if not self._initialized or self.redis_client is None:
            try:
                # Convert RedisDsn to string before passing to redis.from_url
                redis_url_str = str(settings.redis_url)
                self.redis_client = redis.from_url(
                    redis_url_str,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                )
                # Test connection
                await self.redis_client.ping()
                self._initialized = True
                logger.info("redis_connected", url=redis_url_str)
            except Exception as e:
                logger.error("redis_connection_failed", error=str(e))
                raise

        return self.redis_client

    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        try:
            client = await self._ensure_connection()
            value = await client.get(key)

            if value is None:
                logger.debug("cache_miss", key=key)
                return None

            logger.debug("cache_hit", key=key)

            # Try to deserialize JSON
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value

        except Exception as e:
            logger.warning("cache_get_failed", key=key, error=str(e))
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized if dict/list)
            ttl: Time-to-live in seconds (default: 300 = 5 minutes)

        Returns:
            True if successful, False otherwise
        """
        if ttl is None:
            ttl = 300  # 5 minutes default

        try:
            client = await self._ensure_connection()

            # Serialize to JSON if dict or list
            if isinstance(value, (dict, list)):
                value = json.dumps(value)

            await client.setex(key, ttl, value)

            logger.debug("cache_set", key=key, ttl=ttl)
            return True

        except Exception as e:
            logger.warning("cache_set_failed", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """
        Delete key from cache.

        Args:
            key: Cache key

        Returns:
            True if deleted, False otherwise
        """
        try:
            client = await self._ensure_connection()
            result = await client.delete(key)

            logger.debug("cache_delete", key=key, deleted=bool(result))
            return bool(result)

        except Exception as e:
            logger.warning("cache_delete_failed", key=key, error=str(e))
            return False

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all keys matching a pattern.

        Args:
            pattern: Key pattern (e.g., "account:*", "plan:*")

        Returns:
            Number of keys deleted
        """
        try:
            client = await self._ensure_connection()

            # Scan for matching keys
            deleted = 0
            async for key in client.scan_iter(match=pattern):
                await client.delete(key)
                deleted += 1

            logger.info("cache_pattern_invalidated", pattern=pattern, count=deleted)
            return deleted

        except Exception as e:
            logger.warning("cache_pattern_invalidation_failed", pattern=pattern, error=str(e))
            return 0

    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.

        Args:
            key: Cache key

        Returns:
            True if key exists, False otherwise
        """
        try:
            client = await self._ensure_connection()
            result = await client.exists(key)
            return bool(result)

        except Exception as e:
            logger.warning("cache_exists_failed", key=key, error=str(e))
            return False

    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Increment a counter.

        Args:
            key: Cache key
            amount: Amount to increment by

        Returns:
            New value or None if failed
        """
        try:
            client = await self._ensure_connection()
            result = await client.incrby(key, amount)
            return result

        except Exception as e:
            logger.warning("cache_increment_failed", key=key, error=str(e))
            return None

    async def expire(self, key: str, ttl: int) -> bool:
        """
        Set expiration on existing key.

        Args:
            key: Cache key
            ttl: Time-to-live in seconds

        Returns:
            True if successful, False otherwise
        """
        try:
            client = await self._ensure_connection()
            result = await client.expire(key, ttl)
            return bool(result)

        except Exception as e:
            logger.warning("cache_expire_failed", key=key, error=str(e))
            return False

    async def close(self):
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()
            self._initialized = False
            logger.info("redis_closed")


# Global cache instance
cache = RedisCache()


# Helper functions for common cache patterns
def cache_key(entity_type: str, entity_id: str, suffix: str = "") -> str:
    """
    Generate consistent cache key.

    Args:
        entity_type: Entity type (account, plan, subscription, etc.)
        entity_id: Entity ID
        suffix: Optional suffix for variations

    Returns:
        Cache key string
    """
    if suffix:
        return f"{entity_type}:{entity_id}:{suffix}"
    return f"{entity_type}:{entity_id}"
