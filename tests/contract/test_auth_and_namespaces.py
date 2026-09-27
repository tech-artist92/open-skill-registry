from datetime import UTC

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from open_skill_registry.config import RegistryConfig
from open_skill_registry.server.app import create_app
from open_skill_registry.server.db.session import init_db


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
async def open_app(make_app):
    app = make_app(auth_enabled=False)
    await init_db(app.state.engine)
    return app


@pytest_asyncio.fixture
async def secured_app(make_app):
    app = make_app(auth_enabled=True, admin_key="bootstrap-admin-key-12345")
    await init_db(app.state.engine)
    return app


ADMIN_HEADERS = {"Authorization": "Bearer bootstrap-admin-key-12345"}


@pytest.mark.asyncio
async def test_open_mode_allows_unauthenticated_operations(open_app):
    """When auth_enabled is False, mutations and reads work without credentials."""
    async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
        # 1. Publish skill without auth
        skill_content = (
            b"---\nname: open skill\nversion: 1.0.0\ndescription: an open skill\n---\ninstructions"
        )
        res = await client.post(
            "/api/v1/skills/publish",
            data={"namespace": "public", "slug": "open-skill"},
            files={"file": ("SKILL.md", skill_content, "text/markdown")},
        )
        assert res.status_code == 201

        # 2. Search without auth
        res = await client.get("/api/v1/skills/search", params={"q": "open"})
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["total"] >= 1

        # 3. Direct fetch without auth
        res = await client.get("/api/v1/skills/public/open-skill")
        assert res.status_code == 200
        assert res.json()["data"]["slug"] == "open-skill"


@pytest.mark.asyncio
async def test_secured_mode_bootstrap_admin_key(secured_app):
    """Secured mode accepts bootstrap admin key and rejects unauthorized access."""
    async with AsyncClient(
        transport=ASGITransport(app=secured_app), base_url="http://test"
    ) as client:
        # Unauthorized mutation without auth header -> 401
        res = await client.post(
            "/api/v1/namespaces", json={"slug": "team-a", "name": "Team A", "visibility": "PUBLIC"}
        )
        assert res.status_code == 401

        # Unauthorized mutation with invalid key -> 401
        res = await client.post(
            "/api/v1/namespaces",
            headers={"Authorization": "Bearer invalid-key"},
            json={"slug": "team-a", "name": "Team A", "visibility": "PUBLIC"},
        )
        assert res.status_code == 401

        # Bootstrap admin key succeeds -> 201
        res = await client.post(
            "/api/v1/namespaces",
            headers=ADMIN_HEADERS,
            json={"slug": "team-a", "name": "Team A", "visibility": "PUBLIC"},
        )
        assert res.status_code == 201
        assert res.json()["data"]["slug"] == "team-a"


@pytest.mark.asyncio
async def test_api_key_lifecycle(secured_app):
    """Issuing, listing, and revoking API keys."""
    async with AsyncClient(
        transport=ASGITransport(app=secured_app), base_url="http://test"
    ) as client:
        # 1. Create a namespace
        await client.post(
            "/api/v1/namespaces",
            headers=ADMIN_HEADERS,
            json={"slug": "core-team", "name": "Core Team", "visibility": "PUBLIC"},
        )

        # 2. Issue API key scoped to namespace
        res = await client.post(
            "/api/v1/keys",
            headers=ADMIN_HEADERS,
            json={
                "label": "CI Deploy Key",
                "namespace_slug": "core-team",
                "permissions": ["READ", "WRITE"],
            },
        )
        assert res.status_code == 201
        key_data = res.json()["data"]
        raw_key = key_data["raw_key"]
        key_id = key_data["id"]
        assert raw_key.startswith("osr_live_")
        assert key_data["key_prefix"] == raw_key[:12]
        assert len(key_data["key_prefix"]) == 12
        assert key_data["namespace_slug"] == "core-team"

        # 3. List keys - raw key must not be exposed
        res = await client.get("/api/v1/keys", headers=ADMIN_HEADERS)
        assert res.status_code == 200
        keys_list = res.json()["data"]
        assert any(k["id"] == key_id for k in keys_list)
        for k in keys_list:
            assert "raw_key" not in k
            assert "key_hash" not in k

        # 4. Use issued key to publish
        team_headers = {"Authorization": f"Bearer {raw_key}"}
        skill_content = (
            b"---\nname: core skill\nversion: 1.0.0\ndescription: core\n---\ninstructions"
        )
        res = await client.post(
            "/api/v1/skills/publish",
            headers=team_headers,
            data={"namespace": "core-team", "slug": "core-skill"},
            files={"file": ("SKILL.md", skill_content, "text/markdown")},
        )
        assert res.status_code == 201

        # 5. Revoke key
        res = await client.delete(f"/api/v1/keys/{key_id}", headers=ADMIN_HEADERS)
        assert res.status_code == 200
        assert res.json()["data"]["is_active"] is False

        # 6. Attempting to use revoked key -> 401
        res = await client.post(
            "/api/v1/skills/publish",
            headers=team_headers,
            data={"namespace": "core-team", "slug": "core-skill-2"},
            files={"file": ("SKILL.md", skill_content, "text/markdown")},
        )
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_namespace_crud_and_uniqueness(secured_app):
    """Namespace creation, retrieval, listing, updating, and duplicate conflict."""
    async with AsyncClient(
        transport=ASGITransport(app=secured_app), base_url="http://test"
    ) as client:
        # Create namespace
        res = await client.post(
            "/api/v1/namespaces",
            headers=ADMIN_HEADERS,
            json={
                "slug": "marketing",
                "name": "Marketing Team",
                "description": "Marketing skills",
                "visibility": "PUBLIC",
            },
        )
        assert res.status_code == 201
        assert res.json()["data"]["slug"] == "marketing"

        # Duplicate slug returns 409
        res = await client.post(
            "/api/v1/namespaces",
            headers=ADMIN_HEADERS,
            json={"slug": "marketing", "name": "Marketing Duplicate"},
        )
        assert res.status_code == 409

        # Get namespace detail with skill count
        res = await client.get("/api/v1/namespaces/marketing", headers=ADMIN_HEADERS)
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["slug"] == "marketing"
        assert data["skill_count"] == 0

        # Update namespace
        res = await client.put(
            "/api/v1/namespaces/marketing",
            headers=ADMIN_HEADERS,
            json={
                "name": "Global Marketing",
                "description": "Updated description",
                "visibility": "NAMESPACE_ONLY",
            },
        )
        assert res.status_code == 200
        assert res.json()["data"]["name"] == "Global Marketing"
        assert res.json()["data"]["visibility"] == "NAMESPACE_ONLY"

        # List namespaces
        res = await client.get("/api/v1/namespaces", headers=ADMIN_HEADERS)
        assert res.status_code == 200
        page = res.json()["data"]
        assert any(ns["slug"] == "marketing" for ns in page["items"])


@pytest.mark.asyncio
async def test_namespace_write_scoping(secured_app):
    """API key scoped to team-a cannot publish to team-b (403 Forbidden)."""
    async with AsyncClient(
        transport=ASGITransport(app=secured_app), base_url="http://test"
    ) as client:
        # Create team-a and team-b
        await client.post(
            "/api/v1/namespaces", headers=ADMIN_HEADERS, json={"slug": "team-a", "name": "Team A"}
        )
        await client.post(
            "/api/v1/namespaces", headers=ADMIN_HEADERS, json={"slug": "team-b", "name": "Team B"}
        )

        # Issue key scoped to team-a
        res = await client.post(
            "/api/v1/keys",
            headers=ADMIN_HEADERS,
            json={
                "label": "Team A Key",
                "namespace_slug": "team-a",
                "permissions": ["READ", "WRITE"],
            },
        )
        team_a_key = res.json()["data"]["raw_key"]
        team_a_headers = {"Authorization": f"Bearer {team_a_key}"}

        skill_content = (
            b"---\nname: scoped skill\nversion: 1.0.0\ndescription: test\n---\ninstructions"
        )

        # Publish to team-b using team-a key -> 403 Forbidden
        res = await client.post(
            "/api/v1/skills/publish",
            headers=team_a_headers,
            data={"namespace": "team-b", "slug": "scoped-skill"},
            files={"file": ("SKILL.md", skill_content, "text/markdown")},
        )
        assert res.status_code == 403

        # Publish to team-a using team-a key -> 201 Created
        res = await client.post(
            "/api/v1/skills/publish",
            headers=team_a_headers,
            data={"namespace": "team-a", "slug": "scoped-skill"},
            files={"file": ("SKILL.md", skill_content, "text/markdown")},
        )
        assert res.status_code == 201


@pytest.mark.asyncio
async def test_visibility_filtering(secured_app):
    """Multi-tier visibility: NAMESPACE_ONLY skills hidden from unauthorized callers."""
    async with AsyncClient(
        transport=ASGITransport(app=secured_app), base_url="http://test"
    ) as client:
        # Create namespaces: public-ns (PUBLIC) and private-ns (NAMESPACE_ONLY)
        await client.post(
            "/api/v1/namespaces",
            headers=ADMIN_HEADERS,
            json={"slug": "pub-ns", "name": "Public NS", "visibility": "PUBLIC"},
        )
        await client.post(
            "/api/v1/namespaces",
            headers=ADMIN_HEADERS,
            json={"slug": "priv-ns", "name": "Private NS", "visibility": "NAMESPACE_ONLY"},
        )
        await client.post(
            "/api/v1/namespaces",
            headers=ADMIN_HEADERS,
            json={"slug": "other-ns", "name": "Other NS", "visibility": "PUBLIC"},
        )

        # Issue key for priv-ns and other-ns
        res = await client.post(
            "/api/v1/keys",
            headers=ADMIN_HEADERS,
            json={
                "label": "Priv Key",
                "namespace_slug": "priv-ns",
                "permissions": ["READ", "WRITE"],
            },
        )
        priv_key = res.json()["data"]["raw_key"]
        res = await client.post(
            "/api/v1/keys",
            headers=ADMIN_HEADERS,
            json={
                "label": "Other Key",
                "namespace_slug": "other-ns",
                "permissions": ["READ", "WRITE"],
            },
        )
        other_key = res.json()["data"]["raw_key"]

        # Publish public skill in pub-ns
        pub_skill = (
            b"---\nname: public search skill\nversion: 1.0.0\n"
            b"description: searchable by all\n---\ninstructions"
        )
        res = await client.post(
            "/api/v1/skills/publish",
            headers=ADMIN_HEADERS,
            data={"namespace": "pub-ns", "slug": "pub-skill"},
            files={"file": ("SKILL.md", pub_skill, "text/markdown")},
        )
        assert res.status_code == 201

        # Publish namespace-only skill in priv-ns
        priv_skill = (
            b"---\nname: private search skill\nversion: 1.0.0\n"
            b"description: searchable only by priv-ns\n---\ninstructions"
        )
        res = await client.post(
            "/api/v1/skills/publish",
            headers={"Authorization": f"Bearer {priv_key}"},
            data={"namespace": "priv-ns", "slug": "priv-skill", "visibility": "NAMESPACE_ONLY"},
            files={"file": ("SKILL.md", priv_skill, "text/markdown")},
        )
        assert res.status_code == 201

        # 1. Unauthenticated search: should see pub-skill, NOT priv-skill
        res = await client.get("/api/v1/skills/search", params={"q": "search"})
        assert res.status_code == 200
        slugs = [item["slug"] for item in res.json()["data"]["items"]]
        assert "pub-skill" in slugs
        assert "priv-skill" not in slugs

        # 2. Unauthenticated list: should see pub-skill, NOT priv-skill
        res = await client.get("/api/v1/skills")
        assert res.status_code == 200
        slugs = [item["slug"] for item in res.json()["data"]["items"]]
        assert "pub-skill" in slugs
        assert "priv-skill" not in slugs

        # 3. Direct fetch unauthenticated -> 401 Unauthorized
        res = await client.get("/api/v1/skills/priv-ns/priv-skill")
        assert res.status_code == 401

        # 4. Direct fetch with other-ns key -> 403 Forbidden
        res = await client.get(
            "/api/v1/skills/priv-ns/priv-skill", headers={"Authorization": f"Bearer {other_key}"}
        )
        assert res.status_code == 403

        # 5. Authenticated search with other-ns key: should NOT see priv-skill
        res = await client.get(
            "/api/v1/skills/search",
            headers={"Authorization": f"Bearer {other_key}"},
            params={"q": "search"},
        )
        slugs = [item["slug"] for item in res.json()["data"]["items"]]
        assert "pub-skill" in slugs
        assert "priv-skill" not in slugs

        # 6. Authenticated search with priv-ns key: should see BOTH pub-skill and priv-skill
        res = await client.get(
            "/api/v1/skills/search",
            headers={"Authorization": f"Bearer {priv_key}"},
            params={"q": "search"},
        )
        slugs = [item["slug"] for item in res.json()["data"]["items"]]
        assert "pub-skill" in slugs
        assert "priv-skill" in slugs

        # 7. Direct fetch with priv-ns key -> 200 OK
        res = await client.get(
            "/api/v1/skills/priv-ns/priv-skill", headers={"Authorization": f"Bearer {priv_key}"}
        )
        assert res.status_code == 200
        assert res.json()["data"]["slug"] == "priv-skill"


def test_cli_login_and_namespace(tmp_path):
    """Test CLI commands for login and namespace management."""
    from unittest.mock import MagicMock, patch

    from open_skill_registry.cli.main import app

    runner = CliRunner()

    # 1. Test osr login
    config_file = tmp_path / "osr.config.yaml"
    result = runner.invoke(
        app,
        [
            "login",
            "https://registry.example.com",
            "--api-key",
            "osr_live_secret1234567890abcdef",
            "--namespace",
            "team-x",
            "--config",
            str(config_file),
        ],
    )
    assert result.exit_code == 0
    assert "https://registry.example.com" in result.stdout
    assert "osr_live" in result.stdout
    assert "secret1234567890abcdef" not in result.stdout  # masked
    assert config_file.exists()

    # 2. Test osr namespace commands with mocked client
    with patch("open_skill_registry.cli.commands.namespace.SkillRegistryClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client_cls.return_value = mock_client

        # namespace list
        mock_client.list_namespaces.return_value = [
            {"slug": "public", "name": "Public", "visibility": "PUBLIC"},
            {"slug": "team-a", "name": "Team A", "visibility": "NAMESPACE_ONLY"},
        ]
        res = runner.invoke(app, ["namespace", "list"])
        assert res.exit_code == 0
        assert "team-a" in res.stdout

        # namespace create
        mock_client.create_namespace.return_value = {
            "slug": "team-b",
            "name": "Team B",
            "visibility": "PUBLIC",
        }
        res = runner.invoke(app, ["namespace", "create", "team-b", "--name", "Team B"])
        assert res.exit_code == 0
        assert "Created namespace 'team-b'" in res.stdout or "team-b" in res.stdout

        # namespace info
        mock_client.get_namespace.return_value = {
            "slug": "team-b",
            "name": "Team B",
            "visibility": "PUBLIC",
            "skill_count": 3,
        }
        res = runner.invoke(app, ["namespace", "info", "team-b"])
        assert res.exit_code == 0
        assert "team-b" in res.stdout


@pytest.mark.asyncio
async def test_auth_edge_cases(secured_app, monkeypatch):
    """Test expired keys, read-only permissions, and tagging scoping."""
    from datetime import datetime, timedelta

    async with AsyncClient(
        transport=ASGITransport(app=secured_app), base_url="http://test"
    ) as client:
        # Create namespace
        await client.post(
            "/api/v1/namespaces", headers=ADMIN_HEADERS, json={"slug": "edge-ns", "name": "Edge NS"}
        )

        # 1. Expired Key
        past_time = datetime.now(UTC) - timedelta(hours=1)
        res = await client.post(
            "/api/v1/keys",
            headers=ADMIN_HEADERS,
            json={
                "label": "Expired Key",
                "namespace_slug": "edge-ns",
                "permissions": ["READ", "WRITE"],
                "expires_at": past_time.isoformat(),
            },
        )
        expired_key = res.json()["data"]["raw_key"]

        # Using expired key fails with 401
        res = await client.get(
            "/api/v1/namespaces/edge-ns", headers={"Authorization": f"Bearer {expired_key}"}
        )
        assert res.status_code == 401

        # 2. Read-only key attempting to publish -> 403
        res = await client.post(
            "/api/v1/keys",
            headers=ADMIN_HEADERS,
            json={
                "label": "Readonly Key",
                "namespace_slug": "edge-ns",
                "permissions": ["READ"],
            },
        )
        ro_key = res.json()["data"]["raw_key"]
        skill_content = b"---\nname: ro skill\nversion: 1.0.0\ndescription: ro\n---\ninstructions"
        res = await client.post(
            "/api/v1/skills/publish",
            headers={"Authorization": f"Bearer {ro_key}"},
            data={"namespace": "edge-ns", "slug": "ro-skill"},
            files={"file": ("SKILL.md", skill_content, "text/markdown")},
        )
        assert res.status_code == 403

        # 3. Publish with admin key, then test tag scoping
        res = await client.post(
            "/api/v1/skills/publish",
            headers=ADMIN_HEADERS,
            data={"namespace": "edge-ns", "slug": "tagged-skill", "version": "1.0.0"},
            files={"file": ("SKILL.md", skill_content, "text/markdown")},
        )
        assert res.status_code == 201

        # Readonly key cannot assign tag -> 403
        res = await client.put(
            "/api/v1/skills/edge-ns/tagged-skill/tags/prod",
            headers={"Authorization": f"Bearer {ro_key}"},
            json={"version": "1.0.0"},
        )
        assert res.status_code == 403

        # Admin key can assign tag -> 200
        res = await client.put(
            "/api/v1/skills/edge-ns/tagged-skill/tags/prod",
            headers=ADMIN_HEADERS,
            json={"version": "1.0.0"},
        )
        assert res.status_code == 200

        # 4. Invalid namespace visibility on create -> 400
        res = await client.post(
            "/api/v1/namespaces",
            headers=ADMIN_HEADERS,
            json={"slug": "bad-vis-ns", "name": "Bad Vis", "visibility": "INVALID"},
        )
        assert res.status_code == 400


@pytest.mark.asyncio
async def test_invalid_visibility_on_publish(secured_app):
    """Publishing a skill with invalid visibility returns 400 Bad Request."""
    async with AsyncClient(
        transport=ASGITransport(app=secured_app), base_url="http://test"
    ) as client:
        # Create namespace
        await client.post(
            "/api/v1/namespaces",
            headers=ADMIN_HEADERS,
            json={"slug": "vis-test-ns", "name": "Vis Test NS"},
        )

        skill_content = (
            b"---\nname: vis skill\nversion: 1.0.0\ndescription: vis test\n---\ninstructions"
        )

        # 1. Invalid visibility -> 400
        res = await client.post(
            "/api/v1/skills/publish",
            headers=ADMIN_HEADERS,
            data={"namespace": "vis-test-ns", "slug": "vis-skill-bad", "visibility": "INVALID_VIS"},
            files={"file": ("SKILL.md", skill_content, "text/markdown")},
        )
        assert res.status_code == 400
        err_msg = res.json().get("detail") or res.json().get("error") or ""
        assert "Invalid visibility" in err_msg

        # 2. Case normalization (e.g. lowercase "private" is normalized to "PRIVATE" and succeeds)
        res = await client.post(
            "/api/v1/skills/publish",
            headers=ADMIN_HEADERS,
            data={"namespace": "vis-test-ns", "slug": "vis-skill-good", "visibility": "private"},
            files={"file": ("SKILL.md", skill_content, "text/markdown")},
        )
        assert res.status_code == 201

        # Check detail returns visibility as "PRIVATE"
        res = await client.get("/api/v1/skills/vis-test-ns/vis-skill-good", headers=ADMIN_HEADERS)
        assert res.status_code == 200
        assert res.json()["data"]["visibility"] == "PRIVATE"


@pytest.mark.asyncio
async def test_write_only_key_cannot_read_private_skills(secured_app):
    """Keys with only WRITE permission cannot read private skills in their namespace."""
    async with AsyncClient(
        transport=ASGITransport(app=secured_app), base_url="http://test"
    ) as client:
        # 1. Create namespace
        await client.post(
            "/api/v1/namespaces",
            headers=ADMIN_HEADERS,
            json={"slug": "write-only-ns", "name": "Write Only NS", "visibility": "PRIVATE"},
        )

        # 2. Issue a write-only key (permissions=["WRITE"])
        res = await client.post(
            "/api/v1/keys",
            headers=ADMIN_HEADERS,
            json={
                "label": "Write-Only Key",
                "namespace_slug": "write-only-ns",
                "permissions": ["WRITE"],
            },
        )
        assert res.status_code == 201
        write_key = res.json()["data"]["raw_key"]
        write_headers = {"Authorization": f"Bearer {write_key}"}

        # 3. Publish a private skill using write-only key
        skill_content = (
            b"---\nname: secret skill\nversion: 1.0.0\ndescription: write only\n---\ninstructions"
        )
        res = await client.post(
            "/api/v1/skills/publish",
            headers=write_headers,
            data={"namespace": "write-only-ns", "slug": "secret-skill", "visibility": "PRIVATE"},
            files={"file": ("SKILL.md", skill_content, "text/markdown")},
        )
        assert res.status_code == 201

        # 4. Attempt to read skill metadata using write-only key -> 403 Forbidden
        res = await client.get("/api/v1/skills/write-only-ns/secret-skill", headers=write_headers)
        assert res.status_code == 403
        err_msg = res.json().get("detail") or res.json().get("error") or ""
        assert "insufficient permissions" in err_msg.lower()

        # 5. Attempt to read version data -> 403 Forbidden
        res = await client.get(
            "/api/v1/skills/write-only-ns/secret-skill/versions/1.0.0",
            headers=write_headers,
        )
        assert res.status_code == 403

        # 6. Attempt to read instructions -> 403 Forbidden
        res = await client.get(
            "/api/v1/skills/write-only-ns/secret-skill/versions/1.0.0/instructions",
            headers=write_headers,
        )
        assert res.status_code == 403

        # 7. Search skills with write-only key -> private skill is excluded
        res = await client.get(
            "/api/v1/skills/search",
            headers=write_headers,
            params={"q": "secret"},
        )
        assert res.status_code == 200
        items = res.json()["data"]["items"]
        assert not any(item["slug"] == "secret-skill" for item in items)

        # 8. Admin key CAN read the private skill -> 200 OK
        res = await client.get("/api/v1/skills/write-only-ns/secret-skill", headers=ADMIN_HEADERS)
        assert res.status_code == 200
        assert res.json()["data"]["slug"] == "secret-skill"


@pytest.mark.asyncio
async def test_invalid_permission_on_key_creation(secured_app):
    """Issuing an API key with invalid permissions returns 400 Bad Request."""
    async with AsyncClient(
        transport=ASGITransport(app=secured_app), base_url="http://test"
    ) as client:
        # Invalid permission in list
        res = await client.post(
            "/api/v1/keys",
            headers=ADMIN_HEADERS,
            json={
                "label": "Invalid Perm Key",
                "permissions": ["SUPERADMIN"],
            },
        )
        assert res.status_code == 400
        err_msg = res.json().get("detail") or res.json().get("error") or ""
        assert "Invalid permission" in err_msg

        # Another invalid permission
        res = await client.post(
            "/api/v1/keys",
            headers=ADMIN_HEADERS,
            json={
                "label": "Invalid Perm Key 2",
                "permissions": ["READ", "EXECUTE"],
            },
        )
        assert res.status_code == 400

        # Empty permissions list
        res = await client.post(
            "/api/v1/keys",
            headers=ADMIN_HEADERS,
            json={
                "label": "Empty Perm Key",
                "permissions": [],
            },
        )
        assert res.status_code == 400

