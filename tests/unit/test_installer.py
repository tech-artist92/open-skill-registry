import hashlib
import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from open_skill_registry.cli.commands.install import (
    detect_workspace_target,
    install_skill_files,
    load_installed_manifest,
    parse_skill_name,
    resolve_target_dir,
    save_installed_manifest,
)
from open_skill_registry.cli.main import app
from open_skill_registry.client.exceptions import NotFoundError

runner = CliRunner()


@pytest.fixture
def mock_registry_client():
    with (
        patch(
            "open_skill_registry.cli.commands.install.SkillRegistryClient"
        ) as mock_install_client,
        patch("open_skill_registry.cli.commands.update.SkillRegistryClient") as mock_update_client,
        patch("open_skill_registry.cli.commands.list_cmd.SkillRegistryClient") as mock_list_client,
    ):
        mock_instance = MagicMock()
        mock_instance.__enter__.return_value = mock_instance

        mock_install_client.return_value = mock_instance
        mock_update_client.return_value = mock_instance
        mock_list_client.return_value = mock_instance
        yield mock_instance


# ---------------------------------------------------------------------------
# Unit tests: Auto-detection heuristic and target resolution
# ---------------------------------------------------------------------------


def test_detect_workspace_target_cursor(tmp_path):
    (tmp_path / ".cursor").mkdir()
    assert detect_workspace_target(tmp_path) == "cursor"


def test_detect_workspace_target_claude(tmp_path):
    (tmp_path / ".claude").mkdir()
    assert detect_workspace_target(tmp_path) == "claude"


def test_detect_workspace_target_agents(tmp_path):
    (tmp_path / ".agents").mkdir()
    assert detect_workspace_target(tmp_path) == "agents"


def test_detect_workspace_target_precedence(tmp_path):
    (tmp_path / ".cursor").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".agents").mkdir()
    # .cursor takes highest precedence
    assert detect_workspace_target(tmp_path) == "cursor"


def test_detect_workspace_target_fallback_local(tmp_path):
    assert detect_workspace_target(tmp_path) == "local"


def test_resolve_target_dir_cursor(tmp_path):
    target_dir, rel_path, is_global = resolve_target_dir("cursor", "weather-lookup", tmp_path)
    assert target_dir == tmp_path / ".cursor" / "skills" / "weather-lookup"
    assert rel_path == ".cursor/skills/weather-lookup"
    assert not is_global


def test_resolve_target_dir_claude(tmp_path):
    target_dir, rel_path, is_global = resolve_target_dir("claude", "weather-lookup", tmp_path)
    assert target_dir == tmp_path / ".claude" / "skills" / "weather-lookup"
    assert rel_path == ".claude/skills/weather-lookup"
    assert not is_global


def test_resolve_target_dir_adk_and_agents(tmp_path):
    target_dir1, rel_path1, is_global1 = resolve_target_dir("adk", "weather-lookup", tmp_path)
    assert target_dir1 == tmp_path / ".agents" / "skills" / "weather-lookup"
    assert rel_path1 == ".agents/skills/weather-lookup"
    assert not is_global1

    target_dir2, rel_path2, is_global2 = resolve_target_dir("agents", "weather-lookup", tmp_path)
    assert target_dir2 == tmp_path / ".agents" / "skills" / "weather-lookup"
    assert rel_path2 == ".agents/skills/weather-lookup"
    assert not is_global2


def test_resolve_target_dir_local_with_agents_dir(tmp_path):
    (tmp_path / ".agents").mkdir()
    target_dir, rel_path, is_global = resolve_target_dir("local", "weather-lookup", tmp_path)
    assert target_dir == tmp_path / ".agents" / "skills" / "weather-lookup"
    assert rel_path == ".agents/skills/weather-lookup"
    assert not is_global


def test_resolve_target_dir_local_fallback_home(tmp_path, monkeypatch):
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    target_dir, rel_path, is_global = resolve_target_dir("local", "weather-lookup", tmp_path)
    assert target_dir == fake_home / ".osr" / "skills" / "weather-lookup"
    assert is_global


def test_resolve_target_dir_invalid(tmp_path):
    with pytest.raises(ValueError, match="Unsupported target"):
        resolve_target_dir("invalid-target", "weather-lookup", tmp_path)


# ---------------------------------------------------------------------------
# Unit tests: Installed manifest load and save
# ---------------------------------------------------------------------------


def test_manifest_load_and_save(tmp_path):
    manifest_data = {
        "public/weather-lookup": {
            "namespace": "public",
            "slug": "weather-lookup",
            "version": "1.0.0",
            "target": "cursor",
            "path": ".cursor/skills/weather-lookup",
            "content_hash": "abc123hash",
            "installed_at": "2026-09-27T12:00:00Z",
        }
    }
    save_installed_manifest(manifest_data, tmp_path, is_global=False)
    assert (tmp_path / ".osr-installed.json").exists()

    loaded = load_installed_manifest(tmp_path)
    assert "public/weather-lookup" in loaded
    assert loaded["public/weather-lookup"]["version"] == "1.0.0"


# ---------------------------------------------------------------------------
# CLI tests: osr install
# ---------------------------------------------------------------------------


def test_cli_install_auto_detect_cursor(tmp_path, monkeypatch, mock_registry_client):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".cursor").mkdir()

    file_content = b"# Weather Lookup Skill"
    file_hash = hashlib.sha256(file_content).hexdigest()

    mock_registry_client.get_skill.return_value = {
        "namespace": "public",
        "slug": "weather-lookup",
        "latest_version": "1.0.0",
        "release_tags": {"latest": "1.0.0"},
    }
    mock_registry_client.get_version.return_value = {
        "version": "1.0.0",
        "manifest": {
            "content_hash": "c-hash-123",
            "entries": [{"path": "SKILL.md", "hash": file_hash, "size": len(file_content)}],
        },
    }
    mock_registry_client.get_file.return_value = file_content

    result = runner.invoke(app, ["install", "weather-lookup"])
    assert result.exit_code == 0
    assert (
        "Successfully installed public/weather-lookup@1.0.0 into .cursor/skills/weather-lookup"
        in result.stdout
    )

    installed_file = tmp_path / ".cursor" / "skills" / "weather-lookup" / "SKILL.md"
    assert installed_file.exists()
    assert installed_file.read_bytes() == file_content

    manifest = json.loads((tmp_path / ".osr-installed.json").read_text(encoding="utf-8"))
    assert "public/weather-lookup" in manifest
    assert manifest["public/weather-lookup"]["target"] == "cursor"
    assert manifest["public/weather-lookup"]["version"] == "1.0.0"


def test_cli_install_auto_detect_claude(tmp_path, monkeypatch, mock_registry_client):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".claude").mkdir()

    file_content = b"# Claude Skill"
    file_hash = hashlib.sha256(file_content).hexdigest()

    mock_registry_client.get_skill.return_value = {
        "namespace": "public",
        "slug": "weather-lookup",
        "latest_version": "1.0.0",
    }
    mock_registry_client.get_version.return_value = {
        "version": "1.0.0",
        "manifest": {
            "content_hash": "c-hash-456",
            "entries": [{"path": "SKILL.md", "hash": file_hash, "size": len(file_content)}],
        },
    }
    mock_registry_client.get_file.return_value = file_content

    result = runner.invoke(app, ["install", "weather-lookup"])
    assert result.exit_code == 0
    assert (
        "Successfully installed public/weather-lookup@1.0.0 into .claude/skills/weather-lookup"
        in result.stdout
    )
    assert (tmp_path / ".claude" / "skills" / "weather-lookup" / "SKILL.md").exists()


def test_cli_install_auto_detect_agents(tmp_path, monkeypatch, mock_registry_client):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".agents").mkdir()

    file_content = b"# Agents Skill"
    file_hash = hashlib.sha256(file_content).hexdigest()

    mock_registry_client.get_skill.return_value = {
        "namespace": "public",
        "slug": "weather-lookup",
        "latest_version": "1.0.0",
    }
    mock_registry_client.get_version.return_value = {
        "version": "1.0.0",
        "manifest": {
            "content_hash": "c-hash-789",
            "entries": [{"path": "SKILL.md", "hash": file_hash, "size": len(file_content)}],
        },
    }
    mock_registry_client.get_file.return_value = file_content

    result = runner.invoke(app, ["install", "weather-lookup"])
    assert result.exit_code == 0
    assert (
        "Successfully installed public/weather-lookup@1.0.0 into .agents/skills/weather-lookup"
        in result.stdout
    )
    assert (tmp_path / ".agents" / "skills" / "weather-lookup" / "SKILL.md").exists()


def test_cli_install_explicit_target_override(tmp_path, monkeypatch, mock_registry_client):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".cursor").mkdir()  # Auto-detection would pick cursor

    file_content = b"# Explicit Claude"
    file_hash = hashlib.sha256(file_content).hexdigest()

    mock_registry_client.get_skill.return_value = {
        "namespace": "public",
        "slug": "weather-lookup",
        "latest_version": "1.0.0",
    }
    mock_registry_client.get_version.return_value = {
        "version": "1.0.0",
        "manifest": {
            "content_hash": "c-hash-override",
            "entries": [{"path": "SKILL.md", "hash": file_hash, "size": len(file_content)}],
        },
    }
    mock_registry_client.get_file.return_value = file_content

    result = runner.invoke(app, ["install", "weather-lookup", "--target", "claude"])
    assert result.exit_code == 0
    assert (
        "Successfully installed public/weather-lookup@1.0.0 into .claude/skills/weather-lookup"
        in result.stdout
    )
    assert (tmp_path / ".claude" / "skills" / "weather-lookup" / "SKILL.md").exists()


def test_cli_install_explicit_target_adk(tmp_path, monkeypatch, mock_registry_client):
    monkeypatch.chdir(tmp_path)

    file_content = b"# ADK Skill"
    file_hash = hashlib.sha256(file_content).hexdigest()

    mock_registry_client.get_skill.return_value = {
        "namespace": "public",
        "slug": "weather-lookup",
        "latest_version": "1.0.0",
    }
    mock_registry_client.get_version.return_value = {
        "version": "1.0.0",
        "manifest": {
            "content_hash": "c-hash-adk",
            "entries": [{"path": "SKILL.md", "hash": file_hash, "size": len(file_content)}],
        },
    }
    mock_registry_client.get_file.return_value = file_content

    result = runner.invoke(app, ["install", "weather-lookup", "--target", "adk"])
    assert result.exit_code == 0
    assert (
        "Successfully installed public/weather-lookup@1.0.0 into .agents/skills/weather-lookup"
        in result.stdout
    )
    assert (tmp_path / ".agents" / "skills" / "weather-lookup" / "SKILL.md").exists()


def test_cli_install_custom_namespace_and_version(tmp_path, monkeypatch, mock_registry_client):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".cursor").mkdir()

    file_content = b"# Custom Namespace Skill"
    file_hash = hashlib.sha256(file_content).hexdigest()

    mock_registry_client.get_version.return_value = {
        "version": "2.1.0",
        "manifest": {
            "content_hash": "c-hash-custom",
            "entries": [{"path": "SKILL.md", "hash": file_hash, "size": len(file_content)}],
        },
    }
    mock_registry_client.get_file.return_value = file_content

    result = runner.invoke(app, ["install", "myorg/custom-skill", "--version", "2.1.0"])
    assert result.exit_code == 0
    assert (
        "Successfully installed myorg/custom-skill@2.1.0 into .cursor/skills/custom-skill"
        in result.stdout
    )

    mock_registry_client.get_version.assert_called_once_with("myorg", "custom-skill", "2.1.0")


def test_cli_install_invalid_target(tmp_path, monkeypatch, mock_registry_client):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["install", "weather-lookup", "--target", "unsupported-target"])
    assert result.exit_code != 0
    assert "Invalid target" in result.stdout


def test_cli_install_missing_skill_404(tmp_path, monkeypatch, mock_registry_client):
    monkeypatch.chdir(tmp_path)
    mock_registry_client.get_skill.side_effect = NotFoundError("Skill not found")

    result = runner.invoke(app, ["install", "missing-skill"])
    assert result.exit_code != 0
    assert "Error:" in result.stdout or "not found" in result.stdout.lower()


def test_cli_install_hash_mismatch(tmp_path, monkeypatch, mock_registry_client):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".cursor").mkdir()

    mock_registry_client.get_skill.return_value = {
        "namespace": "public",
        "slug": "weather-lookup",
        "latest_version": "1.0.0",
    }
    mock_registry_client.get_version.return_value = {
        "version": "1.0.0",
        "manifest": {
            "entries": [{"path": "SKILL.md", "hash": "expected-hash-value", "size": 10}],
        },
    }
    mock_registry_client.get_file.return_value = b"different content"

    result = runner.invoke(app, ["install", "weather-lookup"])
    assert result.exit_code != 0
    assert "Hash mismatch" in result.stdout


# ---------------------------------------------------------------------------
# CLI tests: osr list [--installed]
# ---------------------------------------------------------------------------


def test_cli_list_installed_text(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    manifest_data = {
        "public/weather-lookup": {
            "namespace": "public",
            "slug": "weather-lookup",
            "version": "1.0.0",
            "target": "cursor",
            "path": ".cursor/skills/weather-lookup",
            "content_hash": "hash123",
            "installed_at": "2026-09-27T12:00:00Z",
        }
    }
    (tmp_path / ".osr-installed.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    result = runner.invoke(app, ["list", "--installed"])
    assert result.exit_code == 0
    assert "weather-lookup" in result.stdout
    assert "1.0.0" in result.stdout
    assert "cursor" in result.stdout
    assert ".cursor/skills/weather-lookup" in result.stdout


def test_cli_list_installed_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    manifest_data = {
        "public/weather-lookup": {
            "namespace": "public",
            "slug": "weather-lookup",
            "version": "1.0.0",
            "target": "cursor",
            "path": ".cursor/skills/weather-lookup",
            "content_hash": "hash123",
            "installed_at": "2026-09-27T12:00:00Z",
        }
    }
    (tmp_path / ".osr-installed.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    result = runner.invoke(app, ["list", "--installed", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["slug"] == "weather-lookup"
    assert data[0]["target"] == "cursor"


def test_cli_list_installed_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["list", "--installed"])
    assert result.exit_code == 0
    assert "No installed skills found" in result.stdout


def test_cli_list_remote_registry_text(mock_registry_client):
    mock_registry_client.list_skills.return_value = {
        "items": [
            {
                "namespace": "public",
                "slug": "search-assistant",
                "name": "Search Assistant",
                "latest_version": "1.2.0",
                "description": "Assistant for web search",
            }
        ]
    }
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "Search Assistant" in result.stdout or "search-assistant" in result.stdout
    assert "1.2.0" in result.stdout
    assert "Assistant for web search" in result.stdout


def test_cli_list_remote_registry_json(mock_registry_client):
    mock_registry_client.list_skills.return_value = [
        {
            "namespace": "public",
            "slug": "search-assistant",
            "name": "Search Assistant",
            "latest_version": "1.2.0",
            "description": "Assistant for web search",
        }
    ]
    result = runner.invoke(app, ["list", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert data[0]["slug"] == "search-assistant"


# ---------------------------------------------------------------------------
# CLI tests: osr update
# ---------------------------------------------------------------------------


def test_cli_update_single_skill_outdated(tmp_path, monkeypatch, mock_registry_client):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".cursor").mkdir()

    manifest_data = {
        "public/weather-lookup": {
            "namespace": "public",
            "slug": "weather-lookup",
            "version": "1.0.0",
            "target": "cursor",
            "path": ".cursor/skills/weather-lookup",
            "content_hash": "old-hash",
            "installed_at": "2026-09-27T10:00:00Z",
        }
    }
    (tmp_path / ".osr-installed.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    new_file_content = b"# Weather Lookup Skill v1.1.0"
    new_file_hash = hashlib.sha256(new_file_content).hexdigest()

    mock_registry_client.get_skill.return_value = {
        "namespace": "public",
        "slug": "weather-lookup",
        "latest_version": "1.1.0",
        "release_tags": {"latest": "1.1.0"},
    }
    mock_registry_client.get_version.return_value = {
        "version": "1.1.0",
        "manifest": {
            "content_hash": "new-hash",
            "entries": [{"path": "SKILL.md", "hash": new_file_hash, "size": len(new_file_content)}],
        },
    }
    mock_registry_client.get_file.return_value = new_file_content

    result = runner.invoke(app, ["update", "weather-lookup"])
    assert result.exit_code == 0
    assert "Successfully updated public/weather-lookup" in result.stdout or "1.1.0" in result.stdout

    updated_manifest = json.loads((tmp_path / ".osr-installed.json").read_text(encoding="utf-8"))
    assert updated_manifest["public/weather-lookup"]["version"] == "1.1.0"
    assert (
        tmp_path / ".cursor" / "skills" / "weather-lookup" / "SKILL.md"
    ).read_bytes() == new_file_content


def test_cli_update_single_skill_already_up_to_date(tmp_path, monkeypatch, mock_registry_client):
    monkeypatch.chdir(tmp_path)
    manifest_data = {
        "public/weather-lookup": {
            "namespace": "public",
            "slug": "weather-lookup",
            "version": "1.0.0",
            "target": "cursor",
            "path": ".cursor/skills/weather-lookup",
            "content_hash": "old-hash",
            "installed_at": "2026-09-27T10:00:00Z",
        }
    }
    (tmp_path / ".osr-installed.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    mock_registry_client.get_skill.return_value = {
        "namespace": "public",
        "slug": "weather-lookup",
        "latest_version": "1.0.0",
        "release_tags": {"latest": "1.0.0"},
    }

    result = runner.invoke(app, ["update", "weather-lookup"])
    assert result.exit_code == 0
    assert "already up to date" in result.stdout.lower()


def test_cli_update_single_skill_not_installed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["update", "not-installed"])
    assert result.exit_code != 0
    assert "not installed" in result.stdout.lower()


def test_cli_update_all_skills(tmp_path, monkeypatch, mock_registry_client):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".cursor").mkdir()

    manifest_data = {
        "public/skill-a": {
            "namespace": "public",
            "slug": "skill-a",
            "version": "1.0.0",
            "target": "cursor",
            "path": ".cursor/skills/skill-a",
            "content_hash": "hash-a",
            "installed_at": "2026-09-27T10:00:00Z",
        },
        "public/skill-b": {
            "namespace": "public",
            "slug": "skill-b",
            "version": "2.0.0",
            "target": "cursor",
            "path": ".cursor/skills/skill-b",
            "content_hash": "hash-b",
            "installed_at": "2026-09-27T10:00:00Z",
        },
    }
    (tmp_path / ".osr-installed.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    file_content_a = b"# Skill A v1.1.0"
    file_hash_a = hashlib.sha256(file_content_a).hexdigest()

    def mock_get_skill(ns, slug):
        if slug == "skill-a":
            return {
                "namespace": ns,
                "slug": slug,
                "latest_version": "1.1.0",
                "release_tags": {"latest": "1.1.0"},
            }
        else:
            return {
                "namespace": ns,
                "slug": slug,
                "latest_version": "2.0.0",
                "release_tags": {"latest": "2.0.0"},
            }

    mock_registry_client.get_skill.side_effect = mock_get_skill
    mock_registry_client.get_version.return_value = {
        "version": "1.1.0",
        "manifest": {
            "content_hash": "new-hash-a",
            "entries": [{"path": "SKILL.md", "hash": file_hash_a, "size": len(file_content_a)}],
        },
    }
    mock_registry_client.get_file.return_value = file_content_a

    result = runner.invoke(app, ["update"])
    assert result.exit_code == 0
    assert "skill-a" in result.stdout
    assert "skill-b" in result.stdout

    updated_manifest = json.loads((tmp_path / ".osr-installed.json").read_text(encoding="utf-8"))
    assert updated_manifest["public/skill-a"]["version"] == "1.1.0"
    assert updated_manifest["public/skill-b"]["version"] == "2.0.0"


def test_cli_update_all_skills_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["update"])
    assert result.exit_code == 0
    assert "No installed skills found" in result.stdout


# ---------------------------------------------------------------------------
# Unit tests: Path traversal, slug sanitization, and scope isolation (Reviewer Findings)
# ---------------------------------------------------------------------------


def test_parse_skill_name_valid():
    ns, slug = parse_skill_name("public/weather-lookup")
    assert ns == "public" and slug == "weather-lookup"

    ns2, slug2 = parse_skill_name("my_ns-1/custom_skill-99")
    assert ns2 == "my_ns-1" and slug2 == "custom_skill-99"

    ns3, slug3 = parse_skill_name("weather-lookup")
    assert ns3 == "public" and slug3 == "weather-lookup"


@pytest.mark.parametrize(
    "invalid_name",
    [
        "../../evil",
        "public/../../evil",
        "evil;rm -rf",
        "namespace/slug/extra",
        "bad name/spaces",
        "bad@name",
    ],
)
def test_parse_skill_name_invalid(invalid_name):
    import typer

    with pytest.raises(typer.Exit):
        parse_skill_name(invalid_name)


def test_install_skill_files_path_traversal_prevention(tmp_path):
    import typer

    target_dir = tmp_path / "installed_skills" / "my-skill"
    target_dir.mkdir(parents=True)

    mock_client = MagicMock()
    mock_client.get_version.return_value = {
        "manifest": {
            "entries": [
                {"path": "../evil.py", "hash": "somehash", "size": 10},
            ]
        }
    }

    with pytest.raises(typer.Exit):
        install_skill_files(mock_client, "public", "my-skill", "1.0.0", target_dir)

    # Verify no file was written outside target_dir
    assert not (tmp_path / "installed_skills" / "evil.py").exists()


def test_install_skill_files_absolute_path_traversal_prevention(tmp_path):
    import typer

    target_dir = tmp_path / "installed_skills" / "my-skill"
    target_dir.mkdir(parents=True)

    mock_client = MagicMock()
    mock_client.get_version.return_value = {
        "manifest": {
            "entries": [
                {"path": "/tmp/evil.py", "hash": "somehash", "size": 10},
            ]
        }
    }

    with pytest.raises(typer.Exit):
        install_skill_files(mock_client, "public", "my-skill", "1.0.0", target_dir)


def test_manifest_scope_isolation(tmp_path, monkeypatch, mock_registry_client):
    """Verify that installing into global scope does not pull in workspace manifest skills."""
    monkeypatch.chdir(tmp_path)
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    # Workspace has a pre-existing .osr-installed.json with local-skill
    ws_manifest = {
        "public/workspace-skill": {
            "namespace": "public",
            "slug": "workspace-skill",
            "version": "1.0.0",
            "target": "agents",
            "path": ".agents/skills/workspace-skill",
            "content_hash": "wshash",
            "installed_at": "2026-09-27T10:00:00Z",
            "is_global": False,
        }
    }
    (tmp_path / ".osr-installed.json").write_text(json.dumps(ws_manifest), encoding="utf-8")

    file_content = b"# Global Skill Content"
    file_hash = hashlib.sha256(file_content).hexdigest()

    mock_registry_client.get_skill.return_value = {
        "namespace": "public",
        "slug": "global-skill",
        "latest_version": "1.0.0",
    }
    mock_registry_client.get_version.return_value = {
        "version": "1.0.0",
        "manifest": {
            "content_hash": "ghash",
            "entries": [{"path": "SKILL.md", "hash": file_hash, "size": len(file_content)}],
        },
    }
    mock_registry_client.get_file.return_value = file_content

    # Target 'local' without .agents in tmp_path -> resolves to global (~/.osr/skills/...)
    result = runner.invoke(app, ["install", "global-skill", "--target", "local"])
    assert result.exit_code == 0

    # Global manifest must ONLY contain global-skill, not workspace-skill!
    global_manifest_path = fake_home / ".osr" / "installed.json"
    assert global_manifest_path.exists()
    global_data = json.loads(global_manifest_path.read_text(encoding="utf-8"))
    assert "public/global-skill" in global_data
    assert "public/workspace-skill" not in global_data

    # Workspace manifest must remain untouched
    ws_data = json.loads((tmp_path / ".osr-installed.json").read_text(encoding="utf-8"))
    assert "public/workspace-skill" in ws_data
    assert "public/global-skill" not in ws_data


def test_cli_update_batch_failure_exits_one(tmp_path, monkeypatch, mock_registry_client):
    """Verify that batch update exits with code 1 if any skill update fails."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".cursor").mkdir()

    manifest_data = {
        "public/skill-ok": {
            "namespace": "public",
            "slug": "skill-ok",
            "version": "1.0.0",
            "target": "cursor",
            "path": ".cursor/skills/skill-ok",
            "content_hash": "hash-ok",
            "installed_at": "2026-09-27T10:00:00Z",
        },
        "public/skill-fail": {
            "namespace": "public",
            "slug": "skill-fail",
            "version": "1.0.0",
            "target": "cursor",
            "path": ".cursor/skills/skill-fail",
            "content_hash": "hash-fail",
            "installed_at": "2026-09-27T10:00:00Z",
        },
    }
    (tmp_path / ".osr-installed.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    def mock_get_skill(ns, slug):
        if slug == "skill-ok":
            return {
                "namespace": ns,
                "slug": slug,
                "latest_version": "1.0.0",
                "release_tags": {"latest": "1.0.0"},
            }
        else:
            raise RuntimeError("Network error fetching skill-fail")

    mock_registry_client.get_skill.side_effect = mock_get_skill

    result = runner.invoke(app, ["update"])
    assert result.exit_code == 1
    assert "Failed updates" in result.stdout
    assert "skill-fail" in result.stdout

