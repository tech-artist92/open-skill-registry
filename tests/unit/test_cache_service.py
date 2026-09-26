import pytest
import asyncio
from typing import Optional

from open_skill_registry.server.services.cache_service import CacheService, CacheConfig

@pytest.fixture
def cache_config():
    return CacheConfig(enabled=True, redis_url=None)

@pytest.mark.asyncio
async def test_cache_service_in_memory_fallback():
    # redis_url=None means fallback to in-memory
    service = CacheService(CacheConfig(enabled=True, redis_url=None))
    await service.set("test_key", "test_value", ttl_seconds=1)
    
    val = await service.get("test_key")
    assert val == "test_value"
    
    # Test TTL (rough)
    await asyncio.sleep(1.1)
    val2 = await service.get("test_key")
    assert val2 is None

@pytest.mark.asyncio
async def test_cache_service_delete_clear():
    service = CacheService(CacheConfig(enabled=True, redis_url=None))
    await service.set("k1", "v1")
    await service.set("k2", "v2")
    
    await service.delete("k1")
    assert await service.get("k1") is None
    assert await service.get("k2") == "v2"
    
    await service.clear()
    assert await service.get("k2") is None

def test_cache_service_etag():
    service = CacheService(CacheConfig(enabled=True, redis_url=None))
    content = "hello world"
    etag = service.generate_etag(content)
    assert etag.startswith('"') and etag.endswith('"')
    
    assert service.check_etag(etag, etag) is True
    assert service.check_etag(etag, "something_else") is False
    assert service.check_etag(etag, None) is False

@pytest.mark.asyncio
async def test_cache_service_disabled():
    service = CacheService(CacheConfig(enabled=False, redis_url="redis://localhost:6379"))
    await service.set("test_key", "test_value")
    # Should be a no-op / in-memory without error but actually since it's disabled, 
    # it might just not store anything, or use in-memory. The brief says: 
    # "If Redis is disabled (enabled=False), unavailable, or fails connection, gracefully falls back to an in-memory TTL dictionary cache"
    # Actually wait, if it's disabled, does it fall back to in-memory, or just not cache?
    # "gracefully falls back to an in-memory TTL dictionary cache"
    val = await service.get("test_key")
    assert val == "test_value"

@pytest.mark.asyncio
async def test_cache_service_redis_unavailable_fallback():
    # Use a dummy redis URL that will fail connection
    service = CacheService(CacheConfig(enabled=True, redis_url="redis://localhost:9999"))
    # The set should fallback to in-memory
    await service.set("test_key", "test_value")
    val = await service.get("test_key")
    assert val == "test_value"
