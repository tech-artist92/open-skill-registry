import io
import zipfile

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from open_skill_registry.server.app import create_app
from open_skill_registry.server.db.session import init_db


@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_db(app):
    await init_db(app.state.engine)

@pytest.fixture
def app():
    app_instance = create_app()
    if hasattr(app_instance.state, "config") and app_instance.state.config:
        if hasattr(app_instance.state.config, "search") and app_instance.state.config.search:
            app_instance.state.config.search.provider = "none"
    return app_instance

@pytest.mark.asyncio
async def test_publish_skill_single_file(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Mocking the service layer might be needed, or an in-memory DB/storage.
        # Assuming app is configured with in-memory DB for tests.
        response = await client.post(
            "/api/v1/skills/publish",
            data={"namespace": "public", "slug": "my-skill"},
            files={"file": ("SKILL.md", b"---\nname: my skill\nversion: 1.0.0\ndescription: test\n---\ncontent", "text/markdown")}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["data"]["version"] == "1.0.0"

@pytest.mark.asyncio
async def test_publish_skill_duplicate(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        files = {"file": ("SKILL.md", b"---\nname: dup skill\nversion: 1.0.0\ndescription: test\n---\ncontent", "text/markdown")}
        # First publish
        await client.post(
            "/api/v1/skills/publish",
            data={"namespace": "public", "slug": "dup-skill"},
            files=files
        )
        
        # Second publish should fail with 409
        files2 = {"file": ("SKILL.md", b"---\nname: dup skill\nversion: 1.0.0\ndescription: test\n---\ncontent", "text/markdown")}
        response = await client.post(
            "/api/v1/skills/publish",
            data={"namespace": "public", "slug": "dup-skill"},
            files=files2
        )
        assert response.status_code == 409
        assert "duplicate" in response.json()["error"].lower()

@pytest.mark.asyncio
async def test_publish_skill_missing_skill_md(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/skills/publish",
            data={"namespace": "public", "slug": "bad-skill"},
            files={"file": ("readme.txt", b"just some text", "text/plain")}
        )
        assert response.status_code == 400

@pytest.mark.asyncio
async def test_publish_skill_path_traversal(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # We need a zip file containing traversal
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr("SKILL.md", b"---\nname: evil\n---\n")
            zf.writestr("../secret.txt", b"evil")
            
        zip_buffer.seek(0)
        
        response = await client.post(
            "/api/v1/skills/publish",
            data={"namespace": "public"},
            files={"file": ("archive.zip", zip_buffer, "application/zip")}
        )
        assert response.status_code == 400

@pytest.mark.asyncio
async def test_publish_skill_valid_zip(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr("SKILL.md", b"---\nname: zip skill\nversion: 2.0.0\ndescription: test\n---\n")
            zf.writestr("utils.py", b"def hello(): pass")
            
        zip_buffer.seek(0)
        
        response = await client.post(
            "/api/v1/skills/publish",
            data={"namespace": "public"},
            files={"file": ("package.zip", zip_buffer, "application/zip")}
        )
        assert response.status_code == 201
        assert response.json()["data"]["version"] == "2.0.0"
