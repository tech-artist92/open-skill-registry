import pytest
from unittest.mock import patch, MagicMock, mock_open
from typer.testing import CliRunner
from open_skill_registry.cli.main import app
import json
import hashlib
from pathlib import Path

runner = CliRunner()

@pytest.fixture
def mock_client_class():
    with patch("open_skill_registry.cli.commands.search.SkillRegistryClient") as mock_search, \
         patch("open_skill_registry.cli.commands.info.SkillRegistryClient") as mock_info, \
         patch("open_skill_registry.cli.commands.pull.SkillRegistryClient") as mock_pull, \
         patch("open_skill_registry.cli.commands.verify.SkillRegistryClient") as mock_verify:
        
        mock_instance = MagicMock()
        mock_instance.__enter__.return_value = mock_instance
        mock_search.return_value = mock_instance
        mock_info.return_value = mock_instance
        mock_pull.return_value = mock_instance
        mock_verify.return_value = mock_instance
        yield mock_instance

def test_search_text(mock_client_class):
    mock_client_class.search.return_value = [
        {"namespace": "public", "slug": "test-skill", "name": "Test Skill", "description": "A test skill", "similarity": 0.9, "latest_version": "1.0.0"}
    ]
    result = runner.invoke(app, ["search", "test", "--limit", "5"])
    assert result.exit_code == 0
    assert "Test Skill" in result.stdout
    mock_client_class.search.assert_called_once_with(query="test", limit=5, namespace=None)

def test_search_json(mock_client_class):
    mock_client_class.search.return_value = [
        {"namespace": "public", "slug": "test-skill", "name": "Test Skill", "description": "A test skill", "similarity": 0.9, "latest_version": "1.0.0"}
    ]
    result = runner.invoke(app, ["--format", "json", "search", "test"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert len(data) == 1
    assert data[0]["name"] == "Test Skill"

def test_info(mock_client_class):
    mock_client_class.get_skill.return_value = {
        "namespace": "public",
        "slug": "test-skill",
        "name": "Test Skill",
        "description": "A test skill",
        "latest_version": "1.0.0",
        "download_count": 42,
        "release_tags": {"latest": "1.0.0"},
        "versions": [{"version": "1.0.0", "created_at": "2023-01-01T00:00:00Z"}]
    }
    result = runner.invoke(app, ["info", "test-skill"])
    assert result.exit_code == 0
    assert "Test Skill" in result.stdout
    assert "1.0.0" in result.stdout
    assert "42" in result.stdout
    mock_client_class.get_skill.assert_called_once_with("public", "test-skill")

def test_info_not_found(mock_client_class):
    from open_skill_registry.client.exceptions import NotFoundError
    mock_client_class.get_skill.side_effect = NotFoundError("Not found")
    result = runner.invoke(app, ["info", "missing-skill"])
    assert result.exit_code != 0

def test_pull_success(mock_client_class, tmp_path):
    mock_client_class.get_skill.return_value = {
        "namespace": "public",
        "slug": "test-skill",
        "latest_version": "1.0.0",
        "release_tags": {"latest": "1.0.0"}
    }
    
    file_content = b"test content"
    file_hash = hashlib.sha256(file_content).hexdigest()
    
    mock_client_class.get_version.return_value = {
        "version": "1.0.0",
        "manifest": {
            "entries": [
                {"path": "instructions.md", "hash": file_hash, "size": len(file_content)}
            ]
        }
    }
    mock_client_class.get_file.return_value = file_content
    
    output_dir = tmp_path / "skills" / "test-skill"
    result = runner.invoke(app, ["pull", "test-skill", "--output", str(output_dir)])
    
    assert result.exit_code == 0
    assert output_dir.exists()
    assert (output_dir / "instructions.md").read_bytes() == file_content
    assert "Verified 1 files" in result.stdout

def test_pull_hash_mismatch(mock_client_class, tmp_path):
    mock_client_class.get_skill.return_value = {
        "namespace": "public",
        "slug": "test-skill",
        "latest_version": "1.0.0",
        "release_tags": {"latest": "1.0.0"}
    }
    
    file_content = b"test content"
    # Provide a wrong hash
    wrong_hash = hashlib.sha256(b"wrong").hexdigest()
    
    mock_client_class.get_version.return_value = {
        "version": "1.0.0",
        "manifest": {
            "entries": [
                {"path": "instructions.md", "hash": wrong_hash, "size": len(file_content)}
            ]
        }
    }
    mock_client_class.get_file.return_value = file_content
    
    output_dir = tmp_path / "skills" / "test-skill"
    result = runner.invoke(app, ["pull", "test-skill", "--output", str(output_dir)])
    
    assert result.exit_code != 0
    assert "Hash mismatch" in result.stdout

def test_verify_remote(mock_client_class, tmp_path):
    output_dir = tmp_path / "skills" / "test-skill"
    output_dir.mkdir(parents=True)
    
    file_content = b"test content"
    file_hash = hashlib.sha256(file_content).hexdigest()
    (output_dir / "instructions.md").write_bytes(file_content)
    
    mock_client_class.get_skill.return_value = {
        "namespace": "public",
        "slug": "test-skill",
        "latest_version": "1.0.0",
        "release_tags": {"latest": "1.0.0"}
    }
    
    mock_client_class.get_version.return_value = {
        "version": "1.0.0",
        "manifest": {
            "entries": [
                {"path": "instructions.md", "hash": file_hash, "size": len(file_content)}
            ]
        }
    }
    
    result = runner.invoke(app, ["verify", str(output_dir), "--remote", "public/test-skill"])
    assert result.exit_code == 0
    assert "All files verified" in result.stdout

def test_verify_remote_mismatch(mock_client_class, tmp_path):
    output_dir = tmp_path / "skills" / "test-skill"
    output_dir.mkdir(parents=True)
    
    file_content = b"test content"
    (output_dir / "instructions.md").write_bytes(file_content)
    
    wrong_hash = hashlib.sha256(b"wrong").hexdigest()
    
    mock_client_class.get_skill.return_value = {
        "namespace": "public",
        "slug": "test-skill",
        "latest_version": "1.0.0",
        "release_tags": {"latest": "1.0.0"}
    }
    
    mock_client_class.get_version.return_value = {
        "version": "1.0.0",
        "manifest": {
            "entries": [
                {"path": "instructions.md", "hash": wrong_hash, "size": len(file_content)}
            ]
        }
    }
    
    result = runner.invoke(app, ["verify", str(output_dir), "--remote", "public/test-skill"])
    assert result.exit_code != 0
    assert "mismatch" in result.stdout.lower()

def test_verify_local_only(tmp_path):
    output_dir = tmp_path / "skills" / "test-skill"
    output_dir.mkdir(parents=True)
    (output_dir / "instructions.md").write_bytes(b"test content")
    
    # Needs valid osr.yaml? The prompt says "scans LOCAL_DIR, runs validate_package and compute_manifest".
    # We might need to mock validate_package or provide a valid osr.yaml
    
    # Just mock open_skill_registry.packaging.manifest.compute_manifest?
    with patch("open_skill_registry.cli.commands.verify.validate_package") as mock_validate, \
         patch("open_skill_registry.cli.commands.verify.compute_manifest") as mock_compute:
        mock_validate.return_value = []
        mock_compute.return_value = MagicMock(content_hash="mocked_hash", entries=[])
        result = runner.invoke(app, ["verify", str(output_dir)])
        assert result.exit_code == 0
        assert "mocked_hash" in result.stdout


def test_default_base_url():
    with patch("open_skill_registry.cli.commands.search.SkillRegistryClient") as mock_class:
        mock_instance = MagicMock()
        mock_instance.__enter__.return_value = mock_instance
        mock_class.return_value = mock_instance
        
        result = runner.invoke(app, ["search", "test"])
        assert result.exit_code == 0
        mock_class.assert_called_once_with(base_url="http://localhost:8080", api_key=None)

def test_info_with_version():
    with patch("open_skill_registry.cli.commands.info.SkillRegistryClient") as mock_class:
        mock_instance = MagicMock()
        mock_instance.__enter__.return_value = mock_instance
        mock_class.return_value = mock_instance
        mock_instance.get_version.return_value = {
            "version": "1.0.0",
            "content_hash": "test_hash",
            "manifest": {"entries": [{}, {}]}
        }
        
        result = runner.invoke(app, ["info", "test-skill", "--version", "1.0.0"])
        assert result.exit_code == 0
        assert "Version:" in result.stdout
        assert "test_hash" in result.stdout
        assert "2" in result.stdout

def test_verify_local_invalid(tmp_path):
    output_dir = tmp_path / "skills" / "test-skill"
    output_dir.mkdir(parents=True)
    
    with patch("open_skill_registry.cli.commands.verify.validate_package") as mock_validate:
        mock_validate.return_value = ["Missing SKILL.md"]
        result = runner.invoke(app, ["verify", str(output_dir)])
        assert result.exit_code == 1
        assert "Error: Missing SKILL.md" in result.stdout

def test_pull_content_hash(tmp_path):
    with patch("open_skill_registry.cli.commands.pull.SkillRegistryClient") as mock_class:
        mock_instance = MagicMock()
        mock_instance.__enter__.return_value = mock_instance
        mock_class.return_value = mock_instance
        
        mock_instance.get_skill.return_value = {
            "release_tags": {"latest": "1.0.0"}
        }
        mock_instance.get_version.return_value = {
            "version": "1.0.0",
            "manifest": {
                "content_hash": "testhash",
                "entries": []
            }
        }
        
        output_dir = tmp_path / "skills" / "test-skill"
        result = runner.invoke(app, ["pull", "test-skill", "--output", str(output_dir)])
        assert result.exit_code == 0
        assert "Content Hash: testhash" in result.stdout


def test_yank_command():
    with patch("open_skill_registry.cli.commands.yank.SkillRegistryClient") as mock_class:
        mock_instance = MagicMock()
        mock_instance.__enter__.return_value = mock_instance
        mock_class.return_value = mock_instance

        result = runner.invoke(app, ["yank", "public/my-skill", "1.0.0"])
        assert result.exit_code == 0
        assert "Successfully yanked public/my-skill@1.0.0" in result.stdout
        mock_instance.yank_version.assert_called_once_with("public", "my-skill", "1.0.0")


def test_yank_command_error():
    with patch("open_skill_registry.cli.commands.yank.SkillRegistryClient") as mock_class:
        mock_instance = MagicMock()
        mock_instance.__enter__.return_value = mock_instance
        mock_class.return_value = mock_instance
        mock_instance.yank_version.side_effect = RuntimeError("Failed to yank")

        result = runner.invoke(app, ["yank", "public/my-skill", "1.0.0"])
        assert result.exit_code != 0
        assert "Failed to yank" in result.stderr or "Failed to yank" in result.stdout


