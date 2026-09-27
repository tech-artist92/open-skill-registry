import io
import zipfile

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from open_skill_registry.server.app import create_app
from open_skill_registry.server.db.session import init_db


@pytest.fixture
def app():
    app_instance = create_app()
    if hasattr(app_instance.state, "config") and app_instance.state.config:
        if hasattr(app_instance.state.config, "search") and app_instance.state.config.search:
            app_instance.state.config.search.provider = "none"
    return app_instance

@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_db(app):
    await init_db(app.state.engine)

async def populate_db(client):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("SKILL.md", "---\nname: Test Skill\nversion: 1.0.0\ndescription: Test description\ntags: [test]\n---\n# Instructions\nRun this")
        zf.writestr("test.py", "print('hello')")
        
    zip_buffer.seek(0)
    
    response = await client.post(
        "/api/v1/skills/publish",
        data={"namespace": "ns", "slug": "slug", "version": "1.0.0"},
        files={"file": ("skill.zip", zip_buffer, "application/zip")}
    )
    assert response.status_code == 201
    return response.json()["data"]

@pytest.mark.asyncio
async def test_search_skills(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await populate_db(client)
        response = await client.get("/api/v1/skills/search?q=test")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "items" in data["data"]
        assert len(data["data"]["items"]) >= 1
        assert data["data"]["items"][0]["slug"] == "slug"

@pytest.mark.asyncio
async def test_list_skills(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await populate_db(client)
        response = await client.get("/api/v1/skills?page=1&size=20")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "items" in data["data"]
        assert "total" in data["data"]
        assert len(data["data"]["items"]) >= 1

@pytest.mark.asyncio
async def test_get_skill_detail(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await populate_db(client)
        response = await client.get("/api/v1/skills/ns/slug")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["slug"] == "slug"

@pytest.mark.asyncio
async def test_get_skill_version(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await populate_db(client)
        response = await client.get("/api/v1/skills/ns/slug/versions/1.0.0")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["version"] == "1.0.0"
        
        etag = response.headers.get("etag")
        assert etag is not None
        response_304 = await client.get("/api/v1/skills/ns/slug/versions/1.0.0", headers={"if-none-match": etag})
        assert response_304.status_code == 304

@pytest.mark.asyncio
async def test_get_skill_instructions(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await populate_db(client)
        response = await client.get("/api/v1/skills/ns/slug/versions/1.0.0/instructions")
        assert response.status_code == 200
        assert "# Instructions" in response.text
        
        etag = response.headers.get("etag")
        assert etag is not None
        response_304 = await client.get("/api/v1/skills/ns/slug/versions/1.0.0/instructions", headers={"if-none-match": etag})
        assert response_304.status_code == 304

@pytest.mark.asyncio
async def test_get_skill_file(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await populate_db(client)
        response = await client.get("/api/v1/skills/ns/slug/versions/1.0.0/file?path=test.py")
        assert response.status_code == 200
        assert "print('hello')" in response.text

@pytest.mark.asyncio
async def test_get_skill_file_path_traversal(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await populate_db(client)
        response = await client.get("/api/v1/skills/ns/slug/versions/1.0.0/file?path=../test.py")
        assert response.status_code == 400

        response = await client.get("/api/v1/skills/ns/slug/versions/1.0.0/file?path=/test.py")
        assert response.status_code == 400

@pytest.mark.asyncio
async def test_get_skill_404(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/skills/ns/nonexistent")
        assert response.status_code == 404

@pytest.mark.asyncio
async def test_get_skill_version_404(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await populate_db(client)
        response = await client.get("/api/v1/skills/ns/slug/versions/9.9.9")
        assert response.status_code == 404

@pytest.mark.asyncio
async def test_get_skill_file_404(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await populate_db(client)
        response = await client.get("/api/v1/skills/ns/slug/versions/1.0.0/file?path=nonexistent.py")
        assert response.status_code == 404

@pytest.mark.asyncio
async def test_get_skill_file_path_traversal_backslash(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await populate_db(client)
        response = await client.get("/api/v1/skills/ns/slug/versions/1.0.0/file?path=..\\test.py")
        assert response.status_code == 400
