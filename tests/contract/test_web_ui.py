import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from open_skill_registry.server.app import create_app
from open_skill_registry.server.db.session import init_db


@pytest.fixture
def app():
    app_instance = create_app()
    if (
        hasattr(app_instance.state, "config")
        and app_instance.state.config
        and hasattr(app_instance.state.config, "search")
        and app_instance.state.config.search
    ):
        app_instance.state.config.search.provider = "none"
    return app_instance


@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_db(app):
    await init_db(app.state.engine)


@pytest.mark.asyncio
async def test_get_root_serves_html(app):
    """Test that GET / returns index.html with expected title and elements."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        content = response.text
        assert "<title>Open Skill Registry</title>" in content

        # Check header and brand
        assert "Open Skill Registry" in content
        assert "v1.0" in content

        # Check search input and clear button
        assert 'id="search-input"' in content
        assert 'id="search-clear-btn"' in content

        # Check catalog and states
        assert 'id="catalog-grid"' in content
        assert 'id="loading-spinner"' in content
        assert 'id="empty-state"' in content
        assert 'id="error-state"' in content

        # Check detail modal elements
        assert 'id="detail-modal"' in content
        assert 'id="modal-skill-name"' in content
        assert 'id="modal-instructions"' in content
        assert 'id="modal-version-select"' in content
        assert 'id="modal-files-list"' in content
        assert 'id="cli-pull-command"' in content

        # Check upload modal elements
        assert 'id="upload-modal"' in content
        assert 'id="upload-dropzone"' in content
        assert 'id="file-input"' in content
        assert 'id="upload-namespace"' in content
        assert 'id="upload-slug"' in content
        assert 'id="upload-version"' in content
        assert 'id="upload-visibility"' in content
        assert 'value="PUBLIC"' in content
        assert 'value="NAMESPACE_ONLY"' in content
        assert 'value="PRIVATE"' in content
        assert 'id="publish-btn"' in content


@pytest.mark.asyncio
async def test_get_static_styles_css(app):
    """Test that GET /static/styles.css returns CSS stylesheet with required styles."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/static/styles.css")
        assert response.status_code == 200
        assert "text/css" in response.headers.get("content-type", "")
        css = response.text

        # Color system and variables
        assert ":root" in css
        assert "--brand-primary" in css
        assert "--bg-surface" in css

        # Dark mode support
        assert "prefers-color-scheme: dark" in css

        # Dropzone drag-over style
        assert ".dropzone.drag-over" in css or ".drag-over" in css

        # Grid and responsive layout
        assert "catalog-grid" in css
        assert "grid-template-columns" in css

        # Markdown styling
        assert "markdown-container" in css


@pytest.mark.asyncio
async def test_get_static_app_js(app):
    """Test that GET /static/app.js returns JavaScript with client logic."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/static/app.js")
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "javascript" in content_type
        js = response.text

        # API routing calls
        assert "/api/v1/skills" in js
        assert "/api/v1/skills/search" in js
        assert "/api/v1/skills/publish" in js

        # Core logic routines
        assert "loadCatalog" in js
        assert "searchSkills" in js
        assert "renderMarkdown" in js
        assert "handleFileSelected" in js
        assert "handlePublishSubmit" in js

        # Event handling for drag & drop
        assert "dragover" in js
        assert "drop" in js


@pytest.mark.asyncio
async def test_api_endpoints_unobstructed(app):
    """Test that mounting static files and root route does not interfere with APIs."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        health_resp = await client.get("/health")
        assert health_resp.status_code == 200

        api_health_resp = await client.get("/api/v1/health")
        assert api_health_resp.status_code == 200

        skills_resp = await client.get("/api/v1/skills")
        assert skills_resp.status_code == 200
        data = skills_resp.json()
        assert "data" in data


@pytest.mark.asyncio
async def test_static_404_handling(app):
    """Test that non-existent static files return 404."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/static/nonexistent_file_12345.css")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_web_ui_api_lifecycle_flow(app):
    """Test complete API lifecycle: publish -> list -> detail -> instructions -> files -> search."""
    import io
    import zipfile

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Publish skill (simulating drag-and-drop / publish form submit in app.js)
        zip_buf = io.BytesIO()
        skill_md = (
            "---\nname: Calculator Skill\nversion: 1.0.0\n"
            "description: Math calculations\ntags: [math, calc]\n---\n"
            "# Calculator\nPerform calculations."
        )
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("SKILL.md", skill_md)
            zf.writestr("calc.py", "def add(a, b): return a + b")
        zip_buf.seek(0)

        pub_resp = await client.post(
            "/api/v1/skills/publish",
            data={
                "namespace": "public",
                "slug": "calculator",
                "version": "1.0.0",
                "visibility": "PUBLIC",
            },
            files={"file": ("calc.zip", zip_buf, "application/zip")},
        )
        assert pub_resp.status_code == 201
        pub_json = pub_resp.json()
        assert pub_json["data"]["slug"] == "calculator"
        assert pub_json["data"]["version"] == "1.0.0"

        # 2. List skills (app.js loadCatalog)
        list_resp = await client.get("/api/v1/skills")
        assert list_resp.status_code == 200
        items = list_resp.json()["data"]["items"]
        assert any(s["slug"] == "calculator" for s in items)

        # 3. Get skill detail (app.js openSkillDetail)
        detail_resp = await client.get("/api/v1/skills/public/calculator")
        assert detail_resp.status_code == 200
        detail = detail_resp.json()["data"]
        assert detail["name"] == "Calculator Skill"
        assert "1.0.0" in detail["versions"]

        # 4. Get skill instructions (app.js loadVersionDetails)
        inst_resp = await client.get("/api/v1/skills/public/calculator/instructions?version=1.0.0")
        assert inst_resp.status_code == 200
        assert "# Calculator" in inst_resp.text

        # 5. Get version details for manifest files (app.js loadVersionDetails)
        ver_resp = await client.get("/api/v1/skills/public/calculator/versions/1.0.0")
        assert ver_resp.status_code == 200
        ver_data = ver_resp.json()["data"]
        manifest_files = [f["path"] for f in ver_data["manifest"]["files"]]
        assert "calc.py" in manifest_files
        assert "SKILL.md" in manifest_files

        # 6. Live search (app.js searchSkills)
        search_resp = await client.get("/api/v1/skills/search?q=Calculator")
        assert search_resp.status_code == 200
        search_items = search_resp.json()["data"]["items"]
        assert len(search_items) >= 1
        assert search_items[0]["slug"] == "calculator"

