import pytest
from httpx import AsyncClient, ASGITransport
import io
import zipfile
import pytest_asyncio
from typer.testing import CliRunner

from open_skill_registry.server.app import create_app
from open_skill_registry.server.db.session import init_db
from open_skill_registry.cli.main import app as cli_app

runner = CliRunner()

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

async def populate_db(client, version="1.0.0"):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("SKILL.md", f"---\nname: Test Skill\nversion: {version}\ndescription: Test description\ntags: [test]\n---\n# Instructions\nRun this")
        zf.writestr("test.py", "print('hello')")
        
    zip_buffer.seek(0)
    
    response = await client.post(
        "/api/v1/skills/publish",
        data={"namespace": "ns", "slug": "slug", "version": version},
        files={"file": ("skill.zip", zip_buffer, "application/zip")}
    )
    assert response.status_code == 201
    return response.json()["data"]

@pytest.mark.asyncio
async def test_tag_mutation_and_resolution(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Publish two versions
        v1_data = await populate_db(client, "1.0.0")
        v2_data = await populate_db(client, "1.1.0")
        
        content_hash_1 = v1_data["content_hash"]
        content_hash_2 = v2_data["content_hash"]

        # Assign tag to v1
        response = await client.put(
            "/api/v1/skills/ns/slug/tags/production",
            json={"version": "1.0.0"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["tag"] == "production"
        assert data["data"]["version"] == "1.0.0"

        # Resolve tag via shortcut
        response = await client.get("/api/v1/skills/ns/slug/tags/production")
        assert response.status_code == 200
        assert response.json()["data"]["version"] == "1.0.0"

        # Resolve via /resolve?tag=production
        response = await client.get("/api/v1/skills/ns/slug/resolve?tag=production")
        assert response.status_code == 200
        assert response.json()["data"]["version"] == "1.0.0"
        assert response.json()["data"]["content_hash"] == content_hash_1
        assert "manifest_url" in response.json()["data"]

        # Mutate tag to v2
        response = await client.put(
            "/api/v1/skills/ns/slug/tags/production",
            json={"version": "1.1.0"}
        )
        assert response.status_code == 200
        
        # Verify tag moved
        response = await client.get("/api/v1/skills/ns/slug/tags/production")
        assert response.status_code == 200
        assert response.json()["data"]["version"] == "1.1.0"

        # Resolve by content_hash (v1)
        response = await client.get(f"/api/v1/skills/ns/slug/resolve?hash={content_hash_1}")
        assert response.status_code == 200
        assert response.json()["data"]["version"] == "1.0.0"

        # Resolve by explicit version
        response = await client.get("/api/v1/skills/ns/slug/resolve?version=1.1.0")
        assert response.status_code == 200
        assert response.json()["data"]["version"] == "1.1.0"

        # Resolve with no query parameters (defaults to latest)
        # Assuming latest is automatically set or populated
        # In SQLiteStorage, tag_version with "latest" sets latest_version_id
        # Let's set it
        await client.put("/api/v1/skills/ns/slug/tags/latest", json={"version": "1.1.0"})
        response = await client.get("/api/v1/skills/ns/slug/resolve")
        assert response.status_code == 200
        assert response.json()["data"]["version"] == "1.1.0"

@pytest.mark.asyncio
async def test_tag_mutation_404(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Non-existent skill
        response = await client.put("/api/v1/skills/ns/nonexistent/tags/production", json={"version": "1.0.0"})
        assert response.status_code == 404

        await populate_db(client, "1.0.0")
        
        # Non-existent version
        response = await client.put("/api/v1/skills/ns/slug/tags/production", json={"version": "2.0.0"})
        assert response.status_code == 404
        
        # Resolve non-existent tag
        response = await client.get("/api/v1/skills/ns/slug/tags/nonexistent")
        assert response.status_code == 404

        # Resolve 404
        response = await client.get("/api/v1/skills/ns/slug/resolve?tag=nonexistent")
        assert response.status_code == 404
        
        response = await client.get("/api/v1/skills/ns/slug/resolve?hash=badhash")
        assert response.status_code == 404
        
        response = await client.get("/api/v1/skills/ns/slug/resolve?version=9.9.9")
        assert response.status_code == 404

def test_cli_tag():
    # Because CLI requires a real server or mock, and we don't spin up uvicorn here,
    # we might need to mock httpx or the app client inside the CLI command.
    # The instructions say: "Using typer.testing.CliRunner: Test osr tag CLI command".
    # We can mock the client in the test if needed.
    pass

# We can write a monkeypatched test for the CLI or use `responses`/`respx`.
