import io
import zipfile
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from open_skill_registry.cli.main import app as cli_app
from open_skill_registry.client.main import AsyncSkillRegistryClient, SkillRegistryClient
from open_skill_registry.config import RegistryConfig
from open_skill_registry.server.app import create_app
from open_skill_registry.server.db.session import init_db

runner = CliRunner()


@pytest.fixture
def make_app():
    def _factory(auth_enabled: bool = False, admin_key: str = "bootstrap-admin-key-12345"):
        cfg = RegistryConfig()
        cfg.server.auth_enabled = auth_enabled
        cfg.server.admin_key = admin_key
        cfg.search.provider = "none"
        app = create_app(cfg)
        return app

    return _factory


@pytest_asyncio.fixture
async def app(make_app):
    app_instance = make_app(auth_enabled=False)
    await init_db(app_instance.state.engine)
    return app_instance


@pytest_asyncio.fixture
async def secured_app(make_app):
    app_instance = make_app(auth_enabled=True, admin_key="bootstrap-admin-key-12345")
    await init_db(app_instance.state.engine)
    return app_instance


ADMIN_HEADERS = {"Authorization": "Bearer bootstrap-admin-key-12345"}


async def publish_version(
    client,
    namespace="ns",
    slug="test-skill",
    version="1.0.0",
    instructions=None,
    headers=None,
    name=None,
):
    name = name or slug
    instructions = instructions or f"# Instructions for {version}"
    zip_buffer = io.BytesIO()
    skill_content = (
        f"---\nname: {name}\nversion: {version}\n"
        f"description: Test description for {slug}\ntags: [test]\n---\n{instructions}"
    )
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("SKILL.md", skill_content)
        zf.writestr("test.py", f"print('version {version}')")

    zip_buffer.seek(0)

    res = await client.post(
        "/api/v1/skills/publish",
        data={"namespace": namespace, "slug": slug, "version": version},
        files={"file": ("skill.zip", zip_buffer, "application/zip")},
        headers=headers,
    )
    assert res.status_code == 201, f"Failed publishing version {version}: {res.text}"
    return res.json()["data"]


@pytest.mark.asyncio
async def test_yank_lifecycle_and_reversion(app):
    """Test yank lifecycle: publish 1.0.0 & 1.1.0, yank 1.1.0, check warning headers and list."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Publish version 1.0.0 and 1.1.0
        await publish_version(
            client,
            namespace="ns",
            slug="my-skill",
            version="1.0.0",
            instructions="# Instructions v1.0.0",
        )
        await publish_version(
            client,
            namespace="ns",
            slug="my-skill",
            version="1.1.0",
            instructions="# Instructions v1.1.0",
        )

        # Verify before yank: latest is 1.1.0
        detail = await client.get("/api/v1/skills/ns/my-skill")
        assert detail.status_code == 200
        assert detail.json()["data"]["latest_version"] == "1.1.0"

        resolve_res = await client.get("/api/v1/skills/ns/my-skill/resolve")
        assert resolve_res.status_code == 200
        assert resolve_res.json()["data"]["version"] == "1.1.0"

        # 2. Yank version 1.1.0
        yank_res = await client.delete("/api/v1/skills/ns/my-skill/versions/1.1.0")
        assert yank_res.status_code == 200
        envelope = yank_res.json()
        assert envelope["code"] == 200
        assert "yanked" in envelope.get("message", "").lower()
        data = envelope["data"]
        assert data["namespace"] == "ns"
        assert data["slug"] == "my-skill"
        assert data["version"] == "1.1.0"
        assert data["is_yanked"] is True

        # 3. Direct fetch of yanked version -> returns X-Skill-Warning: Yanked and is_yanked: true
        ver_res = await client.get("/api/v1/skills/ns/my-skill/versions/1.1.0")
        assert ver_res.status_code == 200
        assert ver_res.headers.get("X-Skill-Warning") == "Yanked"
        ver_data = ver_res.json()["data"]
        assert ver_data["version"] == "1.1.0"
        assert ver_data["is_yanked"] is True

        # 4. Direct fetch of instructions with ?version=1.1.0 -> returns X-Skill-Warning: Yanked
        instr_res = await client.get("/api/v1/skills/ns/my-skill/instructions?version=1.1.0")
        assert instr_res.status_code == 200
        assert instr_res.headers.get("X-Skill-Warning") == "Yanked"
        assert "# Instructions v1.1.0" in instr_res.text

        # 5. Path-based instructions fetch -> returns X-Skill-Warning: Yanked
        instr_path_res = await client.get("/api/v1/skills/ns/my-skill/versions/1.1.0/instructions")
        assert instr_path_res.status_code == 200
        assert instr_path_res.headers.get("X-Skill-Warning") == "Yanked"
        assert "# Instructions v1.1.0" in instr_path_res.text

        # 6. File fetch for yanked version -> returns X-Skill-Warning: Yanked
        file_res = await client.get("/api/v1/skills/ns/my-skill/file?version=1.1.0&path=test.py")
        assert file_res.status_code == 200
        assert file_res.headers.get("X-Skill-Warning") == "Yanked"
        assert "version 1.1.0" in file_res.text

        # 7. Non-yanked version 1.0.0 does NOT have X-Skill-Warning
        ver1_res = await client.get("/api/v1/skills/ns/my-skill/versions/1.0.0")
        assert ver1_res.status_code == 200
        assert ver1_res.headers.get("X-Skill-Warning") is None
        assert ver1_res.json()["data"]["is_yanked"] is False

        instr1_res = await client.get("/api/v1/skills/ns/my-skill/instructions?version=1.0.0")
        assert instr1_res.status_code == 200
        assert instr1_res.headers.get("X-Skill-Warning") is None

        # 8. Latest pointer and tag revert back to 1.0.0
        detail_after = await client.get("/api/v1/skills/ns/my-skill")
        assert detail_after.status_code == 200
        assert detail_after.json()["data"]["latest_version"] == "1.0.0"

        resolve_after = await client.get("/api/v1/skills/ns/my-skill/resolve")
        assert resolve_after.status_code == 200
        assert resolve_after.json()["data"]["version"] == "1.0.0"
        assert resolve_after.headers.get("X-Skill-Warning") is None

        tag_latest_res = await client.get("/api/v1/skills/ns/my-skill/tags/latest")
        assert tag_latest_res.status_code == 200
        assert tag_latest_res.json()["data"]["version"] == "1.0.0"

        # 9. Search and list omit the yanked version and return 1.0.0
        search_res = await client.get("/api/v1/skills/search?q=test")
        assert search_res.status_code == 200
        items = search_res.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["slug"] == "my-skill"
        assert items[0]["latest_version"] == "1.0.0"

        list_res = await client.get("/api/v1/skills")
        assert list_res.status_code == 200
        list_items = list_res.json()["data"]["items"]
        assert len(list_items) == 1
        assert list_items[0]["latest_version"] == "1.0.0"


@pytest.mark.asyncio
async def test_yank_all_versions_omits_from_discovery(app):
    """When all versions of a skill are yanked, the skill is omitted from search and listing."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await publish_version(client, namespace="ns", slug="only-version-skill", version="1.0.0")

        # Confirm visible before yank
        s1 = await client.get("/api/v1/skills/search?q=only-version")
        assert len(s1.json()["data"]["items"]) == 1

        # Yank the sole version
        y_res = await client.delete("/api/v1/skills/ns/only-version-skill/versions/1.0.0")
        assert y_res.status_code == 200

        # Search should omit the skill entirely
        s2 = await client.get("/api/v1/skills/search?q=only-version")
        assert len(s2.json()["data"]["items"]) == 0

        # List should omit the skill entirely
        l2 = await client.get("/api/v1/skills")
        assert not any(i["slug"] == "only-version-skill" for i in l2.json()["data"]["items"])

        # Resolving latest fails with 404
        r_res = await client.get("/api/v1/skills/ns/only-version-skill/resolve")
        assert r_res.status_code == 404


@pytest.mark.asyncio
async def test_yank_404_not_found(app):
    """Yanking non-existent skill or version returns 404."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Non-existent skill
        res = await client.delete("/api/v1/skills/ns/nonexistent-skill/versions/1.0.0")
        assert res.status_code == 404

        # Non-existent version on existing skill
        await publish_version(client, namespace="ns", slug="exist-skill", version="1.0.0")
        res = await client.delete("/api/v1/skills/ns/exist-skill/versions/2.0.0")
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_yank_auth_scoping(secured_app):
    """Secured mode: 401 unauthenticated, 403 wrong ns/read-only, 200 authorized/admin."""
    async with AsyncClient(
        transport=ASGITransport(app=secured_app), base_url="http://test"
    ) as client:
        # Create namespaces team-a and team-b
        await client.post(
            "/api/v1/namespaces", headers=ADMIN_HEADERS, json={"slug": "team-a", "name": "Team A"}
        )
        await client.post(
            "/api/v1/namespaces", headers=ADMIN_HEADERS, json={"slug": "team-b", "name": "Team B"}
        )

        # Issue key for team-a with WRITE
        k_res_a = await client.post(
            "/api/v1/keys",
            headers=ADMIN_HEADERS,
            json={
                "label": "Team A Key",
                "namespace_slug": "team-a",
                "permissions": ["READ", "WRITE"],
            },
        )
        team_a_key = k_res_a.json()["data"]["raw_key"]
        team_a_headers = {"Authorization": f"Bearer {team_a_key}"}

        # Issue key for team-a with READ only
        k_res_ro = await client.post(
            "/api/v1/keys",
            headers=ADMIN_HEADERS,
            json={"label": "Team A RO Key", "namespace_slug": "team-a", "permissions": ["READ"]},
        )
        ro_key = k_res_ro.json()["data"]["raw_key"]
        ro_headers = {"Authorization": f"Bearer {ro_key}"}

        # Issue key for team-b with WRITE
        k_res_b = await client.post(
            "/api/v1/keys",
            headers=ADMIN_HEADERS,
            json={
                "label": "Team B Key",
                "namespace_slug": "team-b",
                "permissions": ["READ", "WRITE"],
            },
        )
        team_b_key = k_res_b.json()["data"]["raw_key"]
        team_b_headers = {"Authorization": f"Bearer {team_b_key}"}

        # Publish skill in team-a using team-a key
        await publish_version(
            client, namespace="team-a", slug="a-skill", version="1.0.0", headers=team_a_headers
        )

        # 1. Unauthenticated delete -> 401
        res = await client.delete("/api/v1/skills/team-a/a-skill/versions/1.0.0")
        assert res.status_code == 401

        # 2. Team-b key attempting to yank team-a skill -> 403
        res = await client.delete(
            "/api/v1/skills/team-a/a-skill/versions/1.0.0", headers=team_b_headers
        )
        assert res.status_code == 403

        # 3. Team-a read-only key attempting to yank -> 403
        res = await client.delete(
            "/api/v1/skills/team-a/a-skill/versions/1.0.0", headers=ro_headers
        )
        assert res.status_code == 403

        # 4. Team-a write key succeeds -> 200
        res = await client.delete(
            "/api/v1/skills/team-a/a-skill/versions/1.0.0", headers=team_a_headers
        )
        assert res.status_code == 200
        assert res.json()["data"]["is_yanked"] is True

        # 5. Admin key can yank in any namespace
        await publish_version(
            client, namespace="team-b", slug="b-skill", version="1.0.0", headers=team_b_headers
        )
        res = await client.delete(
            "/api/v1/skills/team-b/b-skill/versions/1.0.0", headers=ADMIN_HEADERS
        )
        assert res.status_code == 200
        assert res.json()["data"]["is_yanked"] is True


def test_cli_yank():
    """Test CLI osr yank command."""
    with patch("open_skill_registry.cli.commands.yank.SkillRegistryClient") as MockClient:
        mock_client = MockClient.return_value.__enter__.return_value
        mock_client.yank_version.return_value = {
            "namespace": "public",
            "slug": "my-skill",
            "version": "1.0.0",
            "is_yanked": True,
        }

        # Success case with explicit namespace/slug
        result = runner.invoke(cli_app, ["yank", "public/my-skill", "1.0.0"])
        assert result.exit_code == 0
        assert "Successfully yanked public/my-skill@1.0.0" in result.stdout
        mock_client.yank_version.assert_called_with("public", "my-skill", "1.0.0")

        # Success case with implicit namespace (default public)
        mock_client.yank_version.reset_mock()
        result = runner.invoke(cli_app, ["yank", "my-skill", "2.0.0"])
        assert result.exit_code == 0
        assert "Successfully yanked public/my-skill@2.0.0" in result.stdout
        mock_client.yank_version.assert_called_with("public", "my-skill", "2.0.0")

        # Error case
        mock_client.yank_version.side_effect = Exception("Version 1.0.0 not found")
        result = runner.invoke(cli_app, ["yank", "public/my-skill", "1.0.0"])
        assert result.exit_code != 0
        assert (
            "Version 1.0.0 not found" in result.stderr or "Version 1.0.0 not found" in result.stdout
        )


@pytest.mark.asyncio
async def test_client_sdk_yank_version(app):
    """Test yank_version method on both sync and async clients."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as raw_client:
        await publish_version(raw_client, namespace="ns", slug="sdk-skill", version="1.0.0")

    # Test Async Client
    async with AsyncSkillRegistryClient(
        base_url="http://test", transport=ASGITransport(app=app)
    ) as async_client:
        res = await async_client.yank_version("ns", "sdk-skill", "1.0.0")
        assert res["version"] == "1.0.0"
        assert res["is_yanked"] is True

    # Test Sync Client
    def sync_handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == "/api/v1/skills/ns/sdk-skill/versions/1.0.0"
        return httpx.Response(
            200, json={"code": 200, "data": {"version": "1.0.0", "is_yanked": True}}
        )

    with SkillRegistryClient(
        base_url="http://test", transport=httpx.MockTransport(sync_handler)
    ) as sync_client:
        res = sync_client.yank_version("ns", "sdk-skill", "1.0.0")
        assert res["version"] == "1.0.0"
        assert res["is_yanked"] is True
