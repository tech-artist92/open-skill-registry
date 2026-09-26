import io
import json
import pytest
import httpx
from pathlib import Path
from open_skill_registry.client.main import AsyncSkillRegistryClient, SkillRegistryClient
from open_skill_registry.client.exceptions import (
    NotFoundError,
    AuthenticationError,
    DuplicateVersionError
)

def mock_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    method = request.method
    
    if request.headers.get("Authorization") == "Bearer bad_key":
        return httpx.Response(401, json={"detail": "Unauthorized"})

    if method == "GET" and path == "/api/v1/skills/search":
        return httpx.Response(200, json={"data": {"items": [], "total": 0}})

    if method == "GET" and path == "/api/v1/skills":
        return httpx.Response(200, json={"data": {"items": [], "total": 0}})

    if method == "GET" and path == "/api/v1/skills/public/myskill":
        return httpx.Response(200, json={"data": {"name": "myskill"}})

    if method == "GET" and path == "/api/v1/skills/public/noskill":
        return httpx.Response(404, json={"detail": "Not found"})

    if method == "GET" and path == "/api/v1/skills/public/myskill/versions/1.0.0":
        return httpx.Response(200, json={"data": {"version": "1.0.0"}})

    if method == "GET" and path == "/api/v1/skills/public/myskill/versions/1.0.0/instructions":
        return httpx.Response(200, json={"data": "instructions text"})

    if method == "GET" and path == "/api/v1/skills/public/myskill/versions/1.0.0/files/main.py":
        return httpx.Response(200, content=b"print('hello')")

    if method == "POST" and path == "/api/v1/skills/publish":
        if b"duplicate" in request.content:
            return httpx.Response(409, json={"detail": "Duplicate version"})
        if b"bad" in request.content:
            return httpx.Response(400, json={"detail": "Bad request"})
        return httpx.Response(200, json={"data": {"status": "published"}})

    return httpx.Response(404, json={"detail": "Not found"})


@pytest.fixture
def mock_transport():
    return httpx.MockTransport(mock_handler)

@pytest.fixture
def async_client(mock_transport):
    return AsyncSkillRegistryClient(transport=mock_transport, base_url="http://testserver")

@pytest.fixture
def sync_client(mock_transport):
    return SkillRegistryClient(transport=mock_transport, base_url="http://testserver")

@pytest.mark.asyncio
async def test_async_search(async_client):
    res = await async_client.search(query="test")
    assert res == {"items": [], "total": 0}

@pytest.mark.asyncio
async def test_async_list_skills(async_client):
    res = await async_client.list_skills()
    assert res == {"items": [], "total": 0}

@pytest.mark.asyncio
async def test_async_get_skill(async_client):
    res = await async_client.get_skill("public", "myskill")
    assert res == {"name": "myskill"}

@pytest.mark.asyncio
async def test_async_get_skill_not_found(async_client):
    with pytest.raises(NotFoundError):
        await async_client.get_skill("public", "noskill")

@pytest.mark.asyncio
async def test_async_get_version(async_client):
    res = await async_client.get_version("public", "myskill", "1.0.0")
    assert res == {"version": "1.0.0"}

@pytest.mark.asyncio
async def test_async_get_instructions(async_client):
    res = await async_client.get_instructions("public", "myskill", "1.0.0")
    assert res == "instructions text"

@pytest.mark.asyncio
async def test_async_get_file(async_client):
    res = await async_client.get_file("public", "myskill", "1.0.0", "main.py")
    assert res == b"print('hello')"

@pytest.mark.asyncio
async def test_async_publish(async_client):
    res = await async_client.publish(file_data=b"good data", namespace="public", slug="myskill", version="1.0.0")
    assert res == {"status": "published"}

@pytest.mark.asyncio
async def test_async_publish_duplicate(async_client):
    with pytest.raises(DuplicateVersionError):
        await async_client.publish(file_data=b"duplicate", namespace="public", slug="myskill", version="1.0.0")

@pytest.mark.asyncio
async def test_async_publish_bad_request(async_client):
    with pytest.raises(ValueError):
        await async_client.publish(file_data=b"bad request", namespace="public", slug="myskill", version="1.0.0")

@pytest.mark.asyncio
async def test_async_auth_error(mock_transport):
    client = AsyncSkillRegistryClient(api_key="bad_key", transport=mock_transport, base_url="http://testserver")
    with pytest.raises(AuthenticationError):
        await client.list_skills()

@pytest.mark.asyncio
async def test_async_context_manager(mock_transport):
    async with AsyncSkillRegistryClient(transport=mock_transport, base_url="http://testserver") as client:
        res = await client.list_skills()
        assert res == {"items": [], "total": 0}

def test_sync_search(sync_client):
    res = sync_client.search(query="test")
    assert res == {"items": [], "total": 0}

def test_sync_list_skills(sync_client):
    res = sync_client.list_skills()
    assert res == {"items": [], "total": 0}

def test_sync_get_skill(sync_client):
    res = sync_client.get_skill("public", "myskill")
    assert res == {"name": "myskill"}

def test_sync_get_skill_not_found(sync_client):
    with pytest.raises(NotFoundError):
        sync_client.get_skill("public", "noskill")

def test_sync_get_version(sync_client):
    res = sync_client.get_version("public", "myskill", "1.0.0")
    assert res == {"version": "1.0.0"}

def test_sync_get_instructions(sync_client):
    res = sync_client.get_instructions("public", "myskill", "1.0.0")
    assert res == "instructions text"

def test_sync_get_file(sync_client):
    res = sync_client.get_file("public", "myskill", "1.0.0", "main.py")
    assert res == b"print('hello')"

def test_sync_publish(sync_client):
    res = sync_client.publish(file_data=b"good data", namespace="public", slug="myskill", version="1.0.0")
    assert res == {"status": "published"}

def test_sync_publish_bad_request(sync_client):
    with pytest.raises(ValueError):
        sync_client.publish(file_data=b"bad request", namespace="public", slug="myskill", version="1.0.0")

def test_sync_auth_error(mock_transport):
    client = SkillRegistryClient(api_key="bad_key", transport=mock_transport, base_url="http://testserver")
    with pytest.raises(AuthenticationError):
        client.list_skills()

def test_sync_context_manager(mock_transport):
    with SkillRegistryClient(transport=mock_transport, base_url="http://testserver") as client:
        res = client.list_skills()
        assert res == {"items": [], "total": 0}
