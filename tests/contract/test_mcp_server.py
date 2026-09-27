"""Contract and integration tests for native Model Context Protocol (MCP) server.

Covers:
- JSON-RPC 2.0 lifecycle: initialize, notifications/initialized, ping, unknown method, invalid json
- Standard MCP Tools: tools/list, tools/call (search_skills, get_skill, list_skills,
  read_skill_resource)
- SEP-2640 Skills Protocol: skills/list, skills/get
- Resources Protocol: resources/list, resources/read (skill://<namespace>/<slug>/<version>/<path>)
- Stdio Transport: line-delimited JSON-RPC and CLI command osr mcp
- SSE Transport: GET /mcp/sse and POST /mcp/messages
"""

import io
import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from open_skill_registry.cli.main import app as cli_app
from open_skill_registry.config import DatabaseConfig, RegistryConfig, SearchConfig, StorageConfig
from open_skill_registry.registry.core.manifest import compute_manifest
from open_skill_registry.registry.main import AsyncSkillRegistry
from open_skill_registry.server.app import create_app
from open_skill_registry.server.db.session import init_db
from open_skill_registry.server.mcp import (
    MCPHandler,
    run_stdio_server,
)


@pytest.fixture
def memory_config():
    return RegistryConfig(
        database=DatabaseConfig(driver="sqlite", url="sqlite+aiosqlite:///:memory:"),
        storage=StorageConfig(driver="sqlite"),
        search=SearchConfig(provider="none"),
    )


@pytest_asyncio.fixture
async def seeded_registry(memory_config):
    registry = AsyncSkillRegistry(config=memory_config)
    await registry.initialize()

    files = {
        "SKILL.md": (
            b"---\n"
            b"name: Web Scraper\n"
            b"description: Scrapes HTML pages and extracts data\n"
            b"version: 1.0.0\n"
            b"tags: [scraping, web]\n"
            b"---\n"
            b"# Web Scraper\n\n"
            b"Use this skill to extract content from web pages.\n"
        ),
        "scraper.py": b"def scrape(url):\n    return '<html></html>'\n",
    }
    await registry.publish(
        namespace="demo",
        slug="web-scraper",
        files=files,
    )
    yield registry
    if hasattr(registry, "engine"):
        await registry.engine.dispose()


@pytest.fixture
def mcp_handler(seeded_registry):
    return MCPHandler(registry=seeded_registry)


# -----------------------------------------------------------------------------
# 1. JSON-RPC 2.0 Lifecycle Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_initialize(mcp_handler):
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        },
    }
    resp = await mcp_handler.handle_request(request)
    assert resp is not None
    data = resp.model_dump()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    assert data["error"] is None
    result = data["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert "tools" in result["capabilities"]
    assert "resources" in result["capabilities"]
    assert "skills" in result["capabilities"]
    assert result["serverInfo"]["name"] == "open-skill-registry"
    assert result["serverInfo"]["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_mcp_notifications_initialized(mcp_handler):
    # Standard JSON-RPC notification has no 'id' and must not yield a response
    notification = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    }
    resp = await mcp_handler.handle_request(notification)
    assert resp is None

    # If sent as a request with an id, it should acknowledge cleanly
    request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "notifications/initialized",
    }
    resp = await mcp_handler.handle_request(request)
    assert resp is not None
    assert resp.error is None


@pytest.mark.asyncio
async def test_mcp_ping(mcp_handler):
    request = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "ping",
    }
    resp = await mcp_handler.handle_request(request)
    assert resp is not None
    data = resp.model_dump()
    assert data["id"] == 3
    assert data["result"] == {}


@pytest.mark.asyncio
async def test_mcp_unknown_method(mcp_handler):
    request = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "unknown/nonexistent_method",
    }
    resp = await mcp_handler.handle_request(request)
    assert resp is not None
    data = resp.model_dump()
    assert data["id"] == 4
    assert data["error"] is not None
    assert data["error"]["code"] == -32601
    assert "Method not found" in data["error"]["message"]


@pytest.mark.asyncio
async def test_mcp_invalid_json(mcp_handler):
    raw = "{ invalid json line"
    resp = await mcp_handler.handle_raw(raw)
    assert resp is not None
    data = resp.model_dump()
    assert data["id"] is None
    assert data["error"] is not None
    assert data["error"]["code"] == -32700


@pytest.mark.asyncio
async def test_mcp_invalid_request_structure(mcp_handler):
    raw = json.dumps({"jsonrpc": "2.0", "params": {}})
    resp = await mcp_handler.handle_raw(raw)
    assert resp is not None
    data = resp.model_dump()
    assert data["error"] is not None
    assert data["error"]["code"] == -32600


# -----------------------------------------------------------------------------
# 2. Standard MCP Tools (tools/list & tools/call)
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tools_list(mcp_handler):
    request = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/list",
    }
    resp = await mcp_handler.handle_request(request)
    assert resp is not None
    result = resp.result
    assert "tools" in result
    tool_names = [t["name"] for t in result["tools"]]
    assert "search_skills" in tool_names
    assert "get_skill" in tool_names
    assert "list_skills" in tool_names
    assert "read_skill_resource" in tool_names

    # Check inputSchema on search_skills
    search_tool = next(t for t in result["tools"] if t["name"] == "search_skills")
    assert "query" in search_tool["inputSchema"]["properties"]


@pytest.mark.asyncio
async def test_tools_call_search_skills(mcp_handler):
    request = {
        "jsonrpc": "2.0",
        "id": 11,
        "method": "tools/call",
        "params": {
            "name": "search_skills",
            "arguments": {"query": "Scraper", "limit": 5},
        },
    }
    resp = await mcp_handler.handle_request(request)
    assert resp is not None
    result = resp.result
    assert result["isError"] is False
    assert len(result["content"]) >= 1
    assert result["content"][0]["type"] == "text"
    text = result["content"][0]["text"]
    assert "web-scraper" in text


@pytest.mark.asyncio
async def test_tools_call_get_skill(mcp_handler):
    request = {
        "jsonrpc": "2.0",
        "id": 12,
        "method": "tools/call",
        "params": {
            "name": "get_skill",
            "arguments": {"namespace": "demo", "slug": "web-scraper"},
        },
    }
    resp = await mcp_handler.handle_request(request)
    assert resp is not None
    result = resp.result
    assert result["isError"] is False
    assert len(result["content"]) >= 1
    text = result["content"][0]["text"]
    assert "Web Scraper" in text
    assert "Use this skill to extract content" in text


@pytest.mark.asyncio
async def test_tools_call_get_skill_not_found(mcp_handler):
    request = {
        "jsonrpc": "2.0",
        "id": 13,
        "method": "tools/call",
        "params": {
            "name": "get_skill",
            "arguments": {"namespace": "demo", "slug": "non-existent-skill"},
        },
    }
    resp = await mcp_handler.handle_request(request)
    assert resp is not None
    result = resp.result
    assert result["isError"] is True
    assert "not found" in result["content"][0]["text"].lower()


@pytest.mark.asyncio
async def test_tools_call_list_skills(mcp_handler):
    request = {
        "jsonrpc": "2.0",
        "id": 14,
        "method": "tools/call",
        "params": {
            "name": "list_skills",
            "arguments": {"namespace": "demo"},
        },
    }
    resp = await mcp_handler.handle_request(request)
    assert resp is not None
    result = resp.result
    assert result["isError"] is False
    text = result["content"][0]["text"]
    assert "web-scraper" in text


@pytest.mark.asyncio
async def test_tools_call_read_skill_resource(mcp_handler):
    request = {
        "jsonrpc": "2.0",
        "id": 15,
        "method": "tools/call",
        "params": {
            "name": "read_skill_resource",
            "arguments": {
                "uri": "skill://demo/web-scraper/1.0.0/scraper.py",
            },
        },
    }
    resp = await mcp_handler.handle_request(request)
    assert resp is not None
    result = resp.result
    assert result["isError"] is False
    text = result["content"][0]["text"]
    assert "def scrape" in text


@pytest.mark.asyncio
async def test_tools_call_unknown_tool(mcp_handler):
    request = {
        "jsonrpc": "2.0",
        "id": 16,
        "method": "tools/call",
        "params": {
            "name": "no_such_tool",
            "arguments": {},
        },
    }
    resp = await mcp_handler.handle_request(request)
    assert resp is not None
    result = resp.result
    assert result["isError"] is True
    assert "Unknown tool" in result["content"][0]["text"]


# -----------------------------------------------------------------------------
# 3. SEP-2640 Skills Protocol (skills/list & skills/get)
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skills_list_all(mcp_handler):
    request = {
        "jsonrpc": "2.0",
        "id": 20,
        "method": "skills/list",
        "params": {},
    }
    resp = await mcp_handler.handle_request(request)
    assert resp is not None
    assert resp.error is None
    skills = resp.result["skills"]
    assert len(skills) >= 1
    item = next((s for s in skills if s["slug"] == "web-scraper"), None)
    assert item is not None
    assert item["namespace"] == "demo"
    assert item["name"] == "Web Scraper"
    assert item["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_skills_list_filter_query(mcp_handler):
    request = {
        "jsonrpc": "2.0",
        "id": 21,
        "method": "skills/list",
        "params": {"query": "scraper"},
    }
    resp = await mcp_handler.handle_request(request)
    assert resp is not None
    skills = resp.result["skills"]
    assert any(s["slug"] == "web-scraper" for s in skills)


@pytest.mark.asyncio
async def test_skills_get(mcp_handler):
    request = {
        "jsonrpc": "2.0",
        "id": 22,
        "method": "skills/get",
        "params": {"namespace": "demo", "slug": "web-scraper", "version": "1.0.0"},
    }
    resp = await mcp_handler.handle_request(request)
    assert resp is not None
    assert resp.error is None
    data = resp.result
    assert data["namespace"] == "demo"
    assert data["slug"] == "web-scraper"
    assert "instructions" in data
    assert "Use this skill to extract content" in data["instructions"]
    assert "manifest" in data
    assert "files" in data["manifest"] or "scraper.py" in str(data["manifest"])


@pytest.mark.asyncio
async def test_skills_get_not_found(mcp_handler):
    request = {
        "jsonrpc": "2.0",
        "id": 23,
        "method": "skills/get",
        "params": {"namespace": "demo", "slug": "unknown"},
    }
    resp = await mcp_handler.handle_request(request)
    assert resp is not None
    assert resp.error is not None
    assert resp.error["code"] in (-32602, -32004)


# -----------------------------------------------------------------------------
# 4. Resources Protocol (resources/list & resources/read)
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resources_list(mcp_handler):
    request = {
        "jsonrpc": "2.0",
        "id": 30,
        "method": "resources/list",
        "params": {},
    }
    resp = await mcp_handler.handle_request(request)
    assert resp is not None
    assert resp.error is None
    resources = resp.result["resources"]
    assert len(resources) >= 1
    uris = [r["uri"] for r in resources]
    assert any("demo/web-scraper" in u for u in uris)


@pytest.mark.asyncio
async def test_resources_read_with_version(mcp_handler):
    request = {
        "jsonrpc": "2.0",
        "id": 31,
        "method": "resources/read",
        "params": {
            "uri": "skill://demo/web-scraper/1.0.0/scraper.py",
        },
    }
    resp = await mcp_handler.handle_request(request)
    assert resp is not None
    assert resp.error is None
    contents = resp.result["contents"]
    assert len(contents) == 1
    assert contents[0]["uri"] == "skill://demo/web-scraper/1.0.0/scraper.py"
    assert "def scrape" in contents[0]["text"]


@pytest.mark.asyncio
async def test_resources_read_without_version(mcp_handler):
    request = {
        "jsonrpc": "2.0",
        "id": 32,
        "method": "resources/read",
        "params": {
            "uri": "skill://demo/web-scraper/scraper.py",
        },
    }
    resp = await mcp_handler.handle_request(request)
    assert resp is not None
    assert resp.error is None
    contents = resp.result["contents"]
    assert len(contents) == 1
    assert "def scrape" in contents[0]["text"]


@pytest.mark.asyncio
async def test_resources_read_not_found(mcp_handler):
    request = {
        "jsonrpc": "2.0",
        "id": 33,
        "method": "resources/read",
        "params": {
            "uri": "skill://demo/web-scraper/1.0.0/does_not_exist.txt",
        },
    }
    resp = await mcp_handler.handle_request(request)
    assert resp is not None
    assert resp.error is not None
    assert resp.error["code"] in (-32602, -32002)


# -----------------------------------------------------------------------------
# 5. Stdio Transport & CLI Command (T072)
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stdio_server_stream(mcp_handler):
    input_lines = (
        '{"jsonrpc": "2.0", "id": 100, "method": "ping"}\n'
        '{"jsonrpc": "2.0", "method": "notifications/initialized"}\n'
        '{"jsonrpc": "2.0", "id": 101, "method": "tools/list"}\n'
    )
    input_stream = io.StringIO(input_lines)
    output_stream = io.StringIO()

    await run_stdio_server(mcp_handler, reader=input_stream, writer=output_stream)

    output_lines = [line.strip() for line in output_stream.getvalue().splitlines() if line.strip()]
    # Notification must not produce an output line, so exactly 2 responses expected
    assert len(output_lines) == 2

    resp1 = json.loads(output_lines[0])
    assert resp1["id"] == 100
    assert resp1["result"] == {}

    resp2 = json.loads(output_lines[1])
    assert resp2["id"] == 101
    assert "tools" in resp2["result"]


def test_cli_mcp_command_help():
    runner = CliRunner()
    result = runner.invoke(cli_app, ["mcp", "--help"])
    assert result.exit_code == 0
    assert "mcp" in result.output.lower()


def test_cli_mcp_stdio_invocation(tmp_path):
    runner = CliRunner()
    # Provide a single ping request over stdin
    input_data = '{"jsonrpc": "2.0", "id": 999, "method": "ping"}\n'
    result = runner.invoke(cli_app, ["mcp"], input=input_data)
    assert result.exit_code == 0
    assert '"id": 999' in result.output or '"id":999' in result.output
    assert '"result"' in result.output


# -----------------------------------------------------------------------------
# 6. SSE Transport Endpoints (T073)
# -----------------------------------------------------------------------------


@pytest_asyncio.fixture
async def mcp_web_app():
    config = RegistryConfig(
        database=DatabaseConfig(driver="sqlite", url="sqlite+aiosqlite:///:memory:"),
        storage=StorageConfig(driver="sqlite"),
        search=SearchConfig(provider="none"),
    )
    app_instance = create_app(config=config)
    await init_db(app_instance.state.engine)

    # Publish a sample skill
    files = {
        "SKILL.md": (
            b"---\n"
            b"name: SSE Test Skill\n"
            b"description: Testing SSE endpoints\n"
            b"version: 1.0.0\n"
            b"---\n"
            b"# SSE Instructions\n"
        )
    }
    manifest = compute_manifest(files)
    await app_instance.state.storage.save_skill_version(
        namespace="demo",
        slug="sse-skill",
        name="SSE Test Skill",
        description="Testing SSE endpoints",
        version="1.0.0",
        manifest=manifest,
        files=files,
        parsed_frontmatter={"name": "SSE Test Skill", "version": "1.0.0"},
        instructions="# SSE Instructions\n",
    )
    yield app_instance
    if hasattr(app_instance.state, "engine"):
        await app_instance.state.engine.dispose()


@pytest.mark.asyncio
async def test_mcp_sse_flow(mcp_web_app):
    transport = ASGITransport(app=mcp_web_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Direct message dispatch without session returns JSON-RPC response directly
        direct_resp = await client.post(
            "/mcp/messages",
            json={"jsonrpc": "2.0", "id": 501, "method": "ping"},
        )
        assert direct_resp.status_code == 200
        data = direct_resp.json()
        assert data["id"] == 501
        assert data["result"] == {}

        # 2. Test api/v1 route alias
        v1_resp = await client.post(
            "/api/v1/mcp/messages",
            json={"jsonrpc": "2.0", "id": 502, "method": "ping"},
        )
        assert v1_resp.status_code == 200
        assert v1_resp.json()["id"] == 502

        # 3. Test SSE stream handshake
        sse_resp = await client.get("/mcp/sse?max_events=1")
        assert sse_resp.status_code == 200
        assert "text/event-stream" in sse_resp.headers.get("content-type", "")
        body = sse_resp.text
        assert "event: endpoint" in body
        assert "/mcp/messages?sessionId=" in body

        # Extract sessionId
        session_id = None
        for line in body.splitlines():
            if "sessionId=" in line:
                session_id = line.split("sessionId=")[1].strip()
                break
        assert session_id is not None

        # 4. Now send message to endpoint for active session
        msg_resp = await client.post(
            f"/mcp/messages?sessionId={session_id}",
            json={
                "jsonrpc": "2.0",
                "id": 777,
                "method": "skills/list",
                "params": {},
            },
        )
        assert msg_resp.status_code == 202
        assert msg_resp.json() == {"status": "accepted"}

        # 5. Read response from SSE stream for this session
        sse_receive = await client.get(f"/mcp/sse?sessionId={session_id}&max_events=1")
        assert sse_receive.status_code == 200
        assert "event: message" in sse_receive.text
        assert "777" in sse_receive.text
        assert "sse-skill" in sse_receive.text
