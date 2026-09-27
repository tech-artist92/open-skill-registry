"""Unit tests for Git Import Service and CLI import command (T067)."""

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from open_skill_registry.cli.main import app
from open_skill_registry.registry.git_import import (
    DiscoveredSkill,
    GitCloneError,
    GitImportError,
    GitRepoSpec,
    ImportResult,
    clone_repo,
    discover_skills_in_dir,
    import_from_git,
    parse_git_specifier,
)

runner = CliRunner()


# ============================================================================
# 1. Specifier Parsing Tests
# ============================================================================


class TestParseGitSpecifier:
    def test_github_shortcut(self):
        spec = parse_git_specifier("github:owner/repo")
        assert spec.url == "https://github.com/owner/repo.git"
        assert spec.ref is None
        assert spec.subpath is None

    def test_github_shortcut_with_ref(self):
        spec = parse_git_specifier("github:owner/repo@v1.0.0")
        assert spec.url == "https://github.com/owner/repo.git"
        assert spec.ref == "v1.0.0"
        assert spec.subpath is None

    def test_github_shortcut_already_ending_with_dot_git(self):
        spec = parse_git_specifier("github:owner/repo.git@v1.2.3")
        assert spec.url == "https://github.com/owner/repo.git"
        assert spec.ref == "v1.2.3"

    def test_https_git_url(self):
        spec = parse_git_specifier("https://github.com/owner/repo.git")
        assert spec.url == "https://github.com/owner/repo.git"
        assert spec.ref is None
        assert spec.subpath is None

    def test_https_git_url_with_ref(self):
        spec = parse_git_specifier("https://github.com/owner/repo.git@main")
        assert spec.url == "https://github.com/owner/repo.git"
        assert spec.ref == "main"
        assert spec.subpath is None

    def test_https_url_without_git_suffix(self):
        spec = parse_git_specifier("https://github.com/owner/repo@feat")
        assert spec.url == "https://github.com/owner/repo"
        assert spec.ref == "feat"

    def test_ssh_git_url(self):
        spec = parse_git_specifier("git@github.com:owner/repo.git")
        assert spec.url == "git@github.com:owner/repo.git"
        assert spec.ref is None

    def test_ssh_git_url_with_ref(self):
        spec = parse_git_specifier("git@github.com:owner/repo.git@v2.0.0")
        assert spec.url == "git@github.com:owner/repo.git"
        assert spec.ref == "v2.0.0"

    def test_explicit_ref_overrides_specifier_ref(self):
        spec = parse_git_specifier("github:owner/repo@v1.0.0", ref="v2.0.0")
        assert spec.url == "https://github.com/owner/repo.git"
        assert spec.ref == "v2.0.0"

    def test_explicit_ref_sets_ref_when_none(self):
        spec = parse_git_specifier("github:owner/repo", ref="main")
        assert spec.url == "https://github.com/owner/repo.git"
        assert spec.ref == "main"

    def test_explicit_subpath(self):
        spec = parse_git_specifier("github:owner/repo", subpath="skills/weather")
        assert spec.subpath == "skills/weather"

    def test_specifier_with_embedded_subpath(self):
        spec = parse_git_specifier("github:owner/repo//skills/weather@v1.0")
        assert spec.url == "https://github.com/owner/repo.git"
        assert spec.subpath == "skills/weather"
        assert spec.ref == "v1.0"

    def test_explicit_subpath_overrides_embedded(self):
        spec = parse_git_specifier("github:owner/repo//skills/old", subpath="skills/new")
        assert spec.subpath == "skills/new"

    @pytest.mark.parametrize(
        "invalid_spec",
        [
            "",
            "   ",
            "not-a-repo",
            "github:",
            "github:/repo",
            "github:owner/",
            "github:a/b/c",
            "ftp://github.com/owner/repo.git",
        ],
    )
    def test_invalid_specifier_raises_value_error(self, invalid_spec):
        with pytest.raises(ValueError):
            parse_git_specifier(invalid_spec)


# ============================================================================
# 2. Git Clone Tests
# ============================================================================


class TestCloneRepo:
    @patch("open_skill_registry.registry.git_import.subprocess.run")
    def test_clone_without_ref(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        spec = GitRepoSpec(url="https://github.com/owner/repo.git")
        target_dir = tmp_path / "repo"

        clone_repo(spec, target_dir)

        mock_run.assert_called_once_with(
            ["git", "clone", "--depth", "1", "https://github.com/owner/repo.git", str(target_dir)],
            capture_output=True,
            text=True,
            check=False,
        )

    @patch("open_skill_registry.registry.git_import.subprocess.run")
    def test_clone_with_ref(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        spec = GitRepoSpec(url="https://github.com/owner/repo.git", ref="v1.0.0")
        target_dir = tmp_path / "repo"

        clone_repo(spec, target_dir)

        mock_run.assert_called_once_with(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                "v1.0.0",
                "https://github.com/owner/repo.git",
                str(target_dir),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    @patch("open_skill_registry.registry.git_import.subprocess.run")
    def test_clone_failure_raises_git_clone_error(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=128, stdout="", stderr="fatal: Remote branch v99.0 not found"
        )
        spec = GitRepoSpec(url="https://github.com/owner/repo.git", ref="v99.0")
        target_dir = tmp_path / "repo"

        with pytest.raises(GitCloneError) as exc_info:
            clone_repo(spec, target_dir)
        assert "fatal: Remote branch v99.0 not found" in str(exc_info.value)
        assert issubclass(GitCloneError, RuntimeError)
        assert issubclass(GitCloneError, GitImportError)

    @patch("open_skill_registry.registry.git_import.subprocess.run")
    def test_git_not_found_raises_git_clone_error(self, mock_run, tmp_path):
        mock_run.side_effect = FileNotFoundError("No such file: 'git'")
        spec = GitRepoSpec(url="https://github.com/owner/repo.git")
        target_dir = tmp_path / "repo"

        with pytest.raises(GitCloneError) as exc_info:
            clone_repo(spec, target_dir)
        assert "git executable not found" in str(exc_info.value).lower()


# ============================================================================
# 3. Skill Discovery Tests
# ============================================================================


class TestDiscoverSkillsInDir:
    def test_root_skill_discovery(self, tmp_path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        skill_md = repo_dir / "SKILL.md"
        skill_md.write_text(
            """---
name: Root Skill
description: A root skill
version: 1.2.3
slug: root-skill
---
# Root Skill Instructions
"""
        )
        (repo_dir / "helper.py").write_text("print('hello')")

        skills = discover_skills_in_dir(repo_dir)
        assert len(skills) == 1
        s = skills[0]
        assert isinstance(s, DiscoveredSkill)
        assert s.name == "Root Skill"
        assert s.slug == "root-skill"
        assert s.version == "1.2.3"
        assert s.description == "A root skill"
        assert "SKILL.md" in s.files
        assert "helper.py" in s.files
        assert s.path == repo_dir

    def test_default_version_and_slug(self, tmp_path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        skill_md = repo_dir / "SKILL.md"
        skill_md.write_text(
            """---
name: Weather Forecast Tool
description: Weather forecast provider
---
# Weather
"""
        )
        skills = discover_skills_in_dir(repo_dir)
        assert len(skills) == 1
        s = skills[0]
        assert s.name == "Weather Forecast Tool"
        assert s.slug == "weather-forecast-tool"
        assert s.version == "0.1.0"

    def test_multi_skill_repository(self, tmp_path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        # Skill 1: skills/weather
        s1_dir = repo_dir / "skills" / "weather"
        s1_dir.mkdir(parents=True)
        (s1_dir / "SKILL.md").write_text(
            """---
name: Weather Skill
description: Weather service
version: 1.0.0
---
"""
        )
        (s1_dir / "weather.py").write_text("# code")

        # Skill 2: skills/search
        s2_dir = repo_dir / "skills" / "search"
        s2_dir.mkdir(parents=True)
        (s2_dir / "SKILL.md").write_text(
            """---
name: Search Skill
description: Search service
version: 2.1.0
---
"""
        )

        # Skill 3: .agents/skills/coder
        s3_dir = repo_dir / ".agents" / "skills" / "coder"
        s3_dir.mkdir(parents=True)
        (s3_dir / "SKILL.md").write_text(
            """---
name: Coder Agent Skill
description: Coding assistant
---
"""
        )

        skills = discover_skills_in_dir(repo_dir)
        assert len(skills) == 3
        slugs = {s.slug for s in skills}
        assert slugs == {"weather-skill", "search-skill", "coder-agent-skill"}

    def test_ignores_hidden_and_build_dirs(self, tmp_path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        # Real skill
        real_dir = repo_dir / "my_skill"
        real_dir.mkdir()
        (real_dir / "SKILL.md").write_text(
            """---
name: Real Skill
description: Valid
---
"""
        )

        # Ignored dirs
        for ign in [".git", ".venv", "venv", "node_modules", "__pycache__"]:
            ign_dir = repo_dir / ign / "sub"
            ign_dir.mkdir(parents=True)
            (ign_dir / "SKILL.md").write_text(
                f"""---
name: Ignored {ign}
description: Should not be found
---
"""
            )

        skills = discover_skills_in_dir(repo_dir)
        assert len(skills) == 1
        assert skills[0].name == "Real Skill"

    def test_subpath_filtering(self, tmp_path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        s1_dir = repo_dir / "skills" / "weather"
        s1_dir.mkdir(parents=True)
        (s1_dir / "SKILL.md").write_text(
            """---
name: Weather
description: Weather
---
"""
        )

        s2_dir = repo_dir / "skills" / "calc"
        s2_dir.mkdir(parents=True)
        (s2_dir / "SKILL.md").write_text(
            """---
name: Calc
description: Calculator
---
"""
        )

        skills = discover_skills_in_dir(repo_dir, subpath="skills/weather")
        assert len(skills) == 1
        assert skills[0].name == "Weather"

    def test_subpath_not_found_returns_empty_list(self, tmp_path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        skills = discover_skills_in_dir(repo_dir, subpath="does/not/exist")
        assert skills == []

    def test_subpath_path_traversal_raises_error(self, tmp_path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        with pytest.raises(ValueError, match="Invalid subpath traversal"):
            discover_skills_in_dir(repo_dir, subpath="../../etc")


# ============================================================================
# 4. Import Service Execution Tests
# ============================================================================


class TestImportFromGit:
    @patch("open_skill_registry.registry.git_import.clone_repo")
    def test_import_with_client(self, mock_clone, tmp_path):
        def fake_clone(spec, target_dir):
            target_dir.mkdir(parents=True, exist_ok=True)
            skill_dir = target_dir / "skills" / "demo"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                """---
name: Demo Skill
description: A demo skill
version: 1.0.0
---
"""
            )
            (skill_dir / "run.py").write_text("print('demo')")

        mock_clone.side_effect = fake_clone

        mock_client = MagicMock()
        mock_client.publish_skill.return_value = {
            "namespace": "public",
            "slug": "demo-skill",
            "version": "1.0.0",
            "content_hash": "sha256:123456abcdef",
        }

        results = import_from_git(
            "github:owner/repo",
            client=mock_client,
        )

        assert len(results) == 1
        res = results[0]
        assert res.success is True
        assert res.status == "published"
        assert res.namespace == "public"
        assert res.slug == "demo-skill"
        assert res.version == "1.0.0"
        assert res.content_hash == "sha256:123456abcdef"

        mock_client.publish_skill.assert_called_once()
        kwargs = mock_client.publish_skill.call_args.kwargs
        assert kwargs["namespace"] == "public"
        assert kwargs["slug"] == "demo-skill"
        assert kwargs["version"] == "1.0.0"
        assert "SKILL.md" in kwargs["files"]

    @patch("open_skill_registry.registry.git_import.clone_repo")
    def test_import_with_embedded_registry(self, mock_clone, tmp_path):
        def fake_clone(spec, target_dir):
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "SKILL.md").write_text(
                """---
name: Embedded Skill
description: Embedded
version: 0.5.0
---
"""
            )

        mock_clone.side_effect = fake_clone

        mock_registry = MagicMock()
        mock_sv = MagicMock()
        mock_sv.namespace = "team-ai"
        mock_sv.slug = "embedded-skill"
        mock_sv.version = "0.5.0"
        mock_sv.content_hash = "sha256:embedded123"
        mock_registry.publish.return_value = mock_sv

        results = import_from_git(
            "github:owner/repo",
            namespace="team-ai",
            registry=mock_registry,
        )

        assert len(results) == 1
        res = results[0]
        assert res.success is True
        assert res.namespace == "team-ai"
        assert res.slug == "embedded-skill"
        assert res.version == "0.5.0"
        assert res.content_hash == "sha256:embedded123"

        mock_registry.publish.assert_called_once()
        kwargs = mock_registry.publish.call_args.kwargs
        assert kwargs["namespace"] == "team-ai"
        assert kwargs["slug"] == "embedded-skill"

    @patch("open_skill_registry.registry.git_import.clone_repo")
    def test_import_multi_skill_repo(self, mock_clone):
        def fake_clone(spec, target_dir):
            target_dir.mkdir(parents=True, exist_ok=True)
            for name in ["alpha", "beta"]:
                d = target_dir / name
                d.mkdir()
                (d / "SKILL.md").write_text(f"---\nname: {name.title()}\ndescription: desc\n---")

        mock_clone.side_effect = fake_clone

        mock_client = MagicMock()
        mock_client.publish_skill.side_effect = [
            {"namespace": "public", "slug": "alpha", "version": "0.1.0", "content_hash": "h1"},
            {"namespace": "public", "slug": "beta", "version": "0.1.0", "content_hash": "h2"},
        ]

        results = import_from_git("github:owner/repo", client=mock_client)
        assert len(results) == 2
        assert [r.slug for r in results] == ["alpha", "beta"]
        assert all(r.success for r in results)

    @patch("open_skill_registry.registry.git_import.clone_repo")
    def test_import_no_skills_found(self, mock_clone):
        mock_clone.side_effect = lambda spec, d: d.mkdir(parents=True, exist_ok=True)
        mock_client = MagicMock()

        results = import_from_git("github:owner/empty", client=mock_client)
        assert results == []
        mock_client.publish_skill.assert_not_called()

    @patch("open_skill_registry.registry.git_import.clone_repo")
    def test_import_publish_failure_recorded(self, mock_clone):
        def fake_clone(spec, target_dir):
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "SKILL.md").write_text("---\nname: Fail Skill\n---\n")

        mock_clone.side_effect = fake_clone

        mock_client = MagicMock()
        mock_client.publish_skill.side_effect = ValueError("Version already exists")

        results = import_from_git("github:owner/fail", client=mock_client)
        assert len(results) == 1
        res = results[0]
        assert res.success is False
        assert res.status == "failed"
        assert "Version already exists" in res.error

    @patch("open_skill_registry.registry.git_import.clone_repo")
    def test_clone_failure_propagates(self, mock_clone):
        mock_clone.side_effect = GitCloneError("fatal: clone failed")
        mock_client = MagicMock()

        with pytest.raises(GitCloneError):
            import_from_git("github:owner/bad", client=mock_client)


# ============================================================================
# 5. CLI Import Command Tests
# ============================================================================


class TestCliImport:
    @patch("open_skill_registry.cli.commands.import_cmd.import_from_git")
    def test_cli_single_skill_import_success(self, mock_import):
        mock_import.return_value = [
            ImportResult(
                namespace="public",
                slug="weather",
                version="1.0.0",
                name="Weather Skill",
                files_count=3,
                content_hash="sha256:abc12345",
                success=True,
                status="published",
            )
        ]

        result = runner.invoke(app, ["import", "github:owner/weather"])
        assert result.exit_code == 0
        assert "Weather Skill" in result.stdout or "weather" in result.stdout
        assert "1.0.0" in result.stdout
        assert "published" in result.stdout
        assert "public" in result.stdout

    @patch("open_skill_registry.cli.commands.import_cmd.import_from_git")
    def test_cli_multi_skill_import_success(self, mock_import):
        mock_import.return_value = [
            ImportResult(
                namespace="custom-ns",
                slug="skill-a",
                version="0.1.0",
                name="Skill A",
                files_count=2,
                content_hash="sha256:h1",
                success=True,
                status="published",
            ),
            ImportResult(
                namespace="custom-ns",
                slug="skill-b",
                version="0.2.0",
                name="Skill B",
                files_count=5,
                content_hash="sha256:h2",
                success=True,
                status="published",
            ),
        ]

        result = runner.invoke(
            app,
            ["import", "github:owner/multi", "--namespace", "custom-ns", "--ref", "v2.0"],
        )
        assert result.exit_code == 0
        assert "Skill A" in result.stdout or "skill-a" in result.stdout
        assert "Skill B" in result.stdout or "skill-b" in result.stdout
        assert "custom-ns" in result.stdout

    @patch("open_skill_registry.cli.commands.import_cmd.import_from_git")
    def test_cli_json_format_output(self, mock_import):
        mock_import.return_value = [
            ImportResult(
                namespace="public",
                slug="json-skill",
                version="1.0.0",
                name="Json Skill",
                files_count=2,
                content_hash="sha256:xyz",
                success=True,
                status="published",
            )
        ]

        result = runner.invoke(app, ["import", "github:owner/repo", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["slug"] == "json-skill"
        assert data[0]["status"] == "published"

    @patch("open_skill_registry.cli.commands.import_cmd.import_from_git")
    def test_cli_no_skills_found_exits_code_1(self, mock_import):
        mock_import.return_value = []

        result = runner.invoke(app, ["import", "github:owner/empty"])
        assert result.exit_code == 1
        assert "No skills found" in result.stdout or "No skills found" in result.stderr

    @patch("open_skill_registry.cli.commands.import_cmd.import_from_git")
    def test_cli_import_failure_exits_code_1(self, mock_import):
        mock_import.return_value = [
            ImportResult(
                namespace="public",
                slug="failed-skill",
                version="1.0.0",
                name="Failed Skill",
                files_count=1,
                content_hash=None,
                success=False,
                error="Security check failed",
                status="failed",
            )
        ]

        result = runner.invoke(app, ["import", "github:owner/bad"])
        assert result.exit_code == 1
        assert "failed" in result.stdout.lower() or "error" in result.stdout.lower()

    @patch("open_skill_registry.cli.commands.import_cmd.import_from_git")
    def test_cli_clone_error_exits_code_1(self, mock_import):
        mock_import.side_effect = GitCloneError("Repository not found")

        result = runner.invoke(app, ["import", "github:owner/nonexistent"])
        assert result.exit_code == 1
        assert "Repository not found" in result.stdout or "Repository not found" in result.stderr

    def test_cli_invalid_specifier_exits_code_1(self):
        result = runner.invoke(app, ["import", "not-a-valid-repo"])
        assert result.exit_code == 1
        assert "Invalid" in result.stdout or "Invalid" in result.stderr
