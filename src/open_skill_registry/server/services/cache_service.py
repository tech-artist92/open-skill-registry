import time
import hashlib
import asyncio
import logging
from typing import Optional, Union, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class CacheConfig:
    enabled: bool = True
    redis_url: Optional[str] = None

class CacheService:
    def __init__(self, config: Union[CacheConfig, str, None, Any] = None, redis_url: Optional[str] = None):
        if isinstance(config, str):
            self.config = CacheConfig(enabled=True, redis_url=config)
        elif config is None:
            self.config = CacheConfig(enabled=True, redis_url=redis_url)
        else:
            self.config = config

        self._in_memory_cache: Dict[str, Dict[str, Any]] = {}
        self._redis = None
        self._use_redis = False
        
        r_url = getattr(self.config, "redis_url", getattr(self.config, "url", None))
        enabled = getattr(self.config, "enabled", True)

        if enabled and r_url:
            try:
                import redis.asyncio as redis
                self._redis = redis.from_url(r_url, decode_responses=True)
                self._use_redis = True
            except Exception as e:
                logger.warning(f"Failed to initialize Redis from {r_url}: {e}")
                self._use_redis = False
        else:
            self._use_redis = False

    async def _cleanup_in_memory(self):
        now = time.time()
        expired_keys = [k for k, v in self._in_memory_cache.items() if v["expires_at"] is not None and v["expires_at"] < now]
        for k in expired_keys:
            del self._in_memory_cache[k]

    async def get(self, key: str) -> Optional[str]:
        if self._use_redis:
            try:
                val = await self._redis.get(key)
                return val
            except Exception as e:
                logger.warning(f"Redis get failed: {e}. Falling back to in-memory.")
                self._use_redis = False
        
        await self._cleanup_in_memory()
        item = self._in_memory_cache.get(key)
        if item:
            if item["expires_at"] is None or item["expires_at"] >= time.time():
                return item["value"]
            else:
                del self._in_memory_cache[key]
        return None

    async def set(self, key: str, value: str, ttl_seconds: int = 3600) -> None:
        if self._use_redis:
            try:
                await self._redis.set(key, value, ex=ttl_seconds)
                return
            except Exception as e:
                logger.warning(f"Redis set failed: {e}. Falling back to in-memory.")
                self._use_redis = False
        
        self._in_memory_cache[key] = {
            "value": value,
            "expires_at": time.time() + ttl_seconds if ttl_seconds is not None else None
        }

    async def delete(self, key: str) -> None:
        if self._use_redis:
            try:
                await self._redis.delete(key)
                return
            except Exception as e:
                logger.warning(f"Redis delete failed: {e}. Falling back to in-memory.")
                self._use_redis = False
        
        if key in self._in_memory_cache:
            del self._in_memory_cache[key]

    async def clear(self) -> None:
        if self._use_redis:
            try:
                await self._redis.flushdb()
                return
            except Exception as e:
                logger.warning(f"Redis clear failed: {e}. Falling back to in-memory.")
                self._use_redis = False
        
        self._in_memory_cache.clear()

    def generate_etag(self, content: Union[str, bytes]) -> str:
        if isinstance(content, str):
            content = content.encode('utf-8')
        digest = hashlib.sha256(content).hexdigest()
        return f'"{digest}"'

    def check_etag(self, etag: str, if_none_match: Optional[str]) -> bool:
        if not if_none_match:
            return False
        
        # Strip weak prefix if present in the given etag
        if etag.startswith("W/"):
            etag = etag[2:]

        # Remove whitespace and split by comma for multiple tags
        tags = []
        for t in if_none_match.split(','):
            t = t.strip()
            if t.startswith("W/"):
                t = t[2:]
            tags.append(t)

        return etag in tags or "*" in tags
