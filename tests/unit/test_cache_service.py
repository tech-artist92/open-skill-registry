
import pytest

from open_skill_registry.server.services.cache_service import CacheConfig, CacheService


@pytest.fixture
def cache_config():
    return CacheConfig(enabled=True, redis_url=None)

from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_cache_service_in_memory_fallback():
    service = CacheService(CacheConfig(enabled=True, redis_url=None))
    
    with patch("time.time", side_effect=[1000.0, 1000.0, 1000.0, 1002.0]):
        await service.set("test_key", "test_value", ttl_seconds=1)
        
        val = await service.get("test_key")
        assert val == "test_value"
        
        # Test TTL expiration (the next time.time() call returns 1002.0, so it expired)
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
    # Test weak etag check
    weak_etag = f"W/{etag}"
    assert service.check_etag(etag, weak_etag) is True

@pytest.mark.asyncio
async def test_cache_service_disabled():
    service = CacheService(CacheConfig(enabled=False, redis_url="redis://localhost:6379"))
    await service.set("test_key", "test_value")
    val = await service.get("test_key")
    assert val == "test_value"

@pytest.mark.asyncio
@patch("redis.asyncio.from_url")
async def test_cache_service_redis_unavailable_fallback(mock_from_url):
    # Mock redis to raise an exception when setting
    mock_redis = AsyncMock()
    mock_redis.set.side_effect = Exception("Connection failed")
    mock_from_url.return_value = mock_redis

    service = CacheService(CacheConfig(enabled=True, redis_url="redis://localhost:9999"))
    # The set should fallback to in-memory
    await service.set("test_key", "test_value")
    
    # After falling back, it should get from in memory
    val = await service.get("test_key")
    assert val == "test_value"
