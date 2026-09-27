"""Integration tests directly validating all sections of quickstart.md (T057).

Covers:
- Section 2: Minimal Setup (osr init creates osr.config.yaml with semantic search enabled)
- Section 3: Embedded Library Mode (SkillRegistry direct in-process publish, search, get)
- Section 4: Hosted Registry (/health endpoint reporting status: ok)
- Section 5: CLI Validation Flow (push single-file, dir, batch; search, info, pull, verify SHA-256)
- Section 6: Web UI (GET / serves HTML, /static/styles.css serves CSS, /static/app.js serves JS)
- Section 7: Google ADK Dynamic Discovery (Embedded mode and Hosted mode)
"""

import httpx
import pytest
import yaml
from starlette.testclient import TestClient
from typer.testing import CliRunner

from open_skill_registry import (
    OpenSkillRegistry,
    RegistryConfig,
    SkillRegistry,
)
from open_skill_registry.cli.main import app as cli_app
from open_skill_registry.server.app import create_app
from open_skill_registry.server.db.session import init_db


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def sample_weather_skill(tmp_path):
    skill_dir = tmp_path / "samples" / "weather-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: weather-lookup\n"
        "description: Fetches real-time weather information for any city.\n"
        "---\n"
        "# Weather Lookup Instructions\n"
        "Step 1: Check city name.\n"
        "Step 2: Return simulated weather response.\n",
        encoding="utf-8",
    )
    return skill_dir


@pytest.fixture
def sample_standalone_skill(tmp_path):
    samples_dir = tmp_path / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)
    skill_file = samples_dir / "standalone-skill.md"
    skill_file.write_text(
        "---\n"
        "name: quick-math\n"
        "description: Performs quick arithmetic calculations.\n"
        "version: 1.0.0\n"
        "---\n"
        "# Quick Math\n"
        "Provide two numbers and an operation. Return the result.\n",
        encoding="utf-8",
    )
    return skill_file


@pytest.fixture
def sample_batch_skills(tmp_path):
    batch_dir = tmp_path / "samples" / "batch-skills"
    skill_a = batch_dir / "skill-a"
    skill_b = batch_dir / "skill-b"
    skill_a.mkdir(parents=True, exist_ok=True)
    skill_b.mkdir(parents=True, exist_ok=True)

    (skill_a / "SKILL.md").write_text(
        "---\n"
        "name: skill-a\n"
        "description: First batch skill.\n"
        "---\n"
        "# Skill A Instructions\n",
        encoding="utf-8",
    )
    (skill_b / "SKILL.md").write_text(
        "---\n"
        "name: skill-b\n"
        "description: Second batch skill.\n"
        "---\n"
        "# Skill B Instructions\n",
        encoding="utf-8",
    )
    return batch_dir


# ==============================================================================
# SECTION 2: Minimal Setup Validation
# ==============================================================================


def test_section2_minimal_setup_init(runner, tmp_path):
    """Section 2: `osr init` generates osr.config.yaml with semantic search enabled."""
    config_file = tmp_path / "osr.config.yaml"
    result = runner.invoke(cli_app, ["init", "--output", str(config_file)])
    assert result.exit_code == 0
    assert config_file.exists()

    content = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    assert content["mode"] in ("embedded", "server")
    search_cfg = content.get("search", {})
    assert search_cfg.get("semantic_enabled") is True
    assert search_cfg.get("provider") == "fastembed"
    assert search_cfg.get("model") == "BAAI/bge-small-en-v1.5"

    loaded_cfg = RegistryConfig.load(config_file)
    assert loaded_cfg.search.semantic_enabled is True
    assert loaded_cfg.search.provider == "fastembed"


# ==============================================================================
# SECTION 3: Embedded Library Validation Flow
# ==============================================================================


@pytest.mark.asyncio
async def test_section3_embedded_library_flow(tmp_path, sample_weather_skill):
    """Section 3: SkillRegistry in embedded mode: init, publish, semantic search, get."""
    db_file = tmp_path / "registry.db"
    config_yaml = tmp_path / "osr.config.yaml"
    config_yaml.write_text(
        f"""
version: "1.0"
mode: "embedded"
database:
  driver: "sqlite"
  url: "sqlite+aiosqlite:///{db_file}"
storage:
  driver: "sqlite"
search:
  semantic_enabled: true
  provider: "none"
""",
        encoding="utf-8",
    )

    registry = SkillRegistry.from_config(str(config_yaml))
    await registry.initialize()

    skill_md_path = sample_weather_skill / "SKILL.md"
    result = await registry.publish(
        path=str(skill_md_path),
        namespace="public",
        version="1.0.0",
    )
    assert result.slug == "weather-lookup"
    assert len(result.content_hash) == 64

    matches = await registry.search(query="weather", limit=5)
    found_slugs = [m.slug for m in matches.items]
    assert "weather-lookup" in found_slugs
    assert len(matches.items) > 0

    skill = await registry.get(namespace="public", slug="weather-lookup")
    assert skill is not None
    assert "Weather Lookup Instructions" in skill.instructions


# ==============================================================================
# SECTION 4: Hosted Registry Health
# ==============================================================================


@pytest.mark.asyncio
async def test_section4_hosted_registry_health():
    """Section 4: Hosted registry /health endpoint reports status: ok."""
    app = create_app()
    if hasattr(app.state, "config") and app.state.config:
        app.state.config.search.provider = "none"

    await init_db(app.state.engine)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost:8080"
    ) as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("code") == 0
        assert data.get("msg") == "success"
        payload = data.get("data", {})
        assert payload.get("status") == "ok"
        assert payload.get("db") == "connected"
        assert "embeddings" in payload


# ==============================================================================
# SECTION 5: CLI Validation Flow
# ==============================================================================


@pytest.mark.asyncio
async def test_section5_cli_validation_flow(
    runner,
    tmp_path,
    sample_weather_skill,
    sample_standalone_skill,
    sample_batch_skills,
):
    """Section 5: End-to-end CLI commands against server."""
    app = create_app()
    if hasattr(app.state, "config") and app.state.config:
        app.state.config.search.provider = "none"
    await init_db(app.state.engine)

    test_client = TestClient(app)
    transport = test_client._transport
    cli_obj = {
        "transport": transport,
        "registry_url": "http://testserver",
        "format": "text",
    }

    # 1. Directory publish: osr push ./samples/weather-skill --namespace public --version 1.0.0
    res_push_dir = runner.invoke(
        cli_app,
        ["push", str(sample_weather_skill), "--namespace", "public", "--version", "1.0.0"],
        obj=cli_obj,
    )
    assert res_push_dir.exit_code == 0
    assert "Successfully published public/weather-lookup @ 1.0.0" in res_push_dir.stdout

    # 2. Inspect published skill: osr info public/weather-lookup
    res_info = runner.invoke(cli_app, ["info", "public/weather-lookup"], obj=cli_obj)
    assert res_info.exit_code == 0
    assert "weather-lookup" in res_info.stdout
    assert "1.0.0" in res_info.stdout

    # 3. Search: osr search "weather"
    res_search = runner.invoke(cli_app, ["search", "weather"], obj=cli_obj)
    assert res_search.exit_code == 0
    assert "weather-lookup" in res_search.stdout

    # 4. Pull & Verify content integrity
    download_dir = tmp_path / "downloaded-skills"
    res_pull = runner.invoke(
        cli_app,
        [
            "pull",
            "public/weather-lookup",
            "--version",
            "1.0.0",
            "--output",
            f"{download_dir}/",
        ],
        obj=cli_obj,
    )
    assert res_pull.exit_code == 0, f"res_pull failed: {res_pull.stdout}"
    assert (download_dir / "weather-lookup" / "SKILL.md").exists()

    res_verify = runner.invoke(
        cli_app,
        ["verify", str(download_dir / "weather-lookup")],
        obj=cli_obj,
    )
    assert res_verify.exit_code == 0
    assert "match release SHA-256 manifest" in res_verify.stdout

    # 5. Single file publish: osr push ./samples/standalone-skill.md --namespace public
    res_push_file = runner.invoke(
        cli_app,
        ["push", str(sample_standalone_skill), "--namespace", "public"],
        obj=cli_obj,
    )
    assert res_push_file.exit_code == 0
    assert "Successfully published" in res_push_file.stdout
    assert "quick-math" in res_push_file.stdout

    res_info_math = runner.invoke(cli_app, ["info", "public/quick-math"], obj=cli_obj)
    assert res_info_math.exit_code == 0
    assert "quick-math" in res_info_math.stdout

    # 6. Batch publish: osr push ./samples/batch-skills/ --batch --namespace public
    res_push_batch = runner.invoke(
        cli_app,
        ["push", str(sample_batch_skills), "--batch", "--namespace", "public"],
        obj=cli_obj,
    )
    assert res_push_batch.exit_code == 0
    assert "skill-a" in res_push_batch.stdout
    assert "skill-b" in res_push_batch.stdout

    res_search_batch = runner.invoke(cli_app, ["search", "batch"], obj=cli_obj)
    assert res_search_batch.exit_code == 0
    assert "skill-a" in res_search_batch.stdout or "skill-b" in res_search_batch.stdout


# ==============================================================================
# SECTION 6: Web UI Validation Flow
# ==============================================================================


@pytest.mark.asyncio
async def test_section6_web_ui_flow():
    """Section 6: Web UI serves index.html, styles.css, app.js."""
    app = create_app()
    if hasattr(app.state, "config") and app.state.config:
        app.state.config.search.provider = "none"
    await init_db(app.state.engine)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost:8080"
    ) as client:
        # GET / serves HTML
        resp_root = await client.get("/")
        assert resp_root.status_code == 200
        assert "text/html" in resp_root.headers.get("content-type", "")
        assert "Open Skill Registry" in resp_root.text
        assert "catalog-grid" in resp_root.text

        # GET /static/styles.css serves CSS
        resp_css = await client.get("/static/styles.css")
        assert resp_css.status_code == 200
        assert "text/css" in resp_css.headers.get("content-type", "")
        assert "--brand-primary" in resp_css.text

        # GET /static/app.js serves JS
        resp_js = await client.get("/static/app.js")
        assert resp_js.status_code == 200
        assert "javascript" in resp_js.headers.get("content-type", "")
        assert "loadCatalog" in resp_js.text


# ==============================================================================
# SECTION 7: Google ADK Dynamic Discovery Flow
# ==============================================================================


@pytest.mark.asyncio
async def test_section7_adk_discovery_embedded(tmp_path, sample_weather_skill):
    """Section 7 Mode A: Embedded mode OpenSkillRegistry(registry=embedded_registry)."""
    db_file = tmp_path / "registry.db"
    config_yaml = tmp_path / "osr.config.yaml"
    config_yaml.write_text(
        f"""
version: "1.0"
mode: "embedded"
database:
  driver: "sqlite"
  url: "sqlite+aiosqlite:///{db_file}"
storage:
  driver: "sqlite"
search:
  semantic_enabled: true
  provider: "none"
""",
        encoding="utf-8",
    )

    embedded_registry = SkillRegistry.from_config(str(config_yaml))
    await embedded_registry.initialize()

    await embedded_registry.publish(
        path=str(sample_weather_skill / "SKILL.md"),
        namespace="public",
        version="1.0.0",
    )

    adk_registry = OpenSkillRegistry(registry=embedded_registry)

    # 1. Test search_skills
    matches = await adk_registry.search_skills(query="weather")
    skill_names = [m.name for m in matches]
    assert "weather-lookup" in skill_names or "public/weather-lookup" in skill_names

    # 2. Test get_skill
    skill = await adk_registry.get_skill(name="public/weather-lookup")
    assert "Weather Lookup Instructions" in skill.instructions


@pytest.mark.asyncio
async def test_section7_adk_discovery_hosted(sample_weather_skill):
    """Section 7 Mode B: Hosted mode OpenSkillRegistry(endpoint=...)."""
    app = create_app()
    if hasattr(app.state, "config") and app.state.config:
        app.state.config.search.provider = "none"
    await init_db(app.state.engine)

    # Publish weather skill into hosted app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        await client.post(
            "/api/v1/skills/publish",
            data={"namespace": "public", "slug": "weather-lookup", "version": "1.0.0"},
            files={
                "file": (
                    "SKILL.md",
                    (sample_weather_skill / "SKILL.md").read_bytes(),
                    "text/markdown",
                )
            },
        )

    test_client = TestClient(app)
    adk_registry = OpenSkillRegistry(
        endpoint="http://testserver",
        transport=test_client._transport,
    )

    # 1. Test search_skills
    matches = await adk_registry.search_skills(query="weather")
    skill_names = [m.name for m in matches]
    assert "weather-lookup" in skill_names or "public/weather-lookup" in skill_names

    # 2. Test get_skill
    skill = await adk_registry.get_skill(name="public/weather-lookup")
    assert "Weather Lookup Instructions" in skill.instructions
