"""Git Import Service for Open Skill Registry (T068).

Enables direct discovery, extraction, and publishing of skills from remote Git repositories.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# Directories ignored during skill discovery
IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
}


class GitImportError(Exception):
    """Base exception for git import service errors."""


class GitCloneError(GitImportError, RuntimeError):
    """Raised when cloning a git repository fails."""


@dataclass(frozen=True)
class GitRepoSpec:
    """Specification of a remote Git repository to import."""

    url: str
    ref: str | None = None
    subpath: str | None = None


@dataclass(frozen=True)
class DiscoveredSkill:
    """A skill discovered within a Git repository."""

    slug: str
    name: str
    version: str
    description: str
    files: dict[str, bytes]
    path: Path


@dataclass(frozen=True)
class ImportResult:
    """Result of publishing an imported skill."""

    namespace: str
    slug: str
    version: str
    content_hash: str | None = None
    success: bool = True
    error: str | None = None
    name: str | None = None
    files_count: int = 0
    status: str = "published"

    def __post_init__(self) -> None:
        if not self.success and self.status == "published":
            object.__setattr__(self, "status", "failed")
        if self.name is None:
            object.__setattr__(self, "name", self.slug)


def _slugify(text: str) -> str:
    """Convert a human-readable title into a URL/registry slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text.strip("-") or "skill"


def _parse_frontmatter(content: bytes) -> dict[str, Any]:
    """Extract YAML frontmatter from SKILL.md bytes if present."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return {}
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                data = yaml.safe_load(parts[1])
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
    return {}


def parse_git_specifier(
    specifier: str, ref: str | None = None, subpath: str | None = None
) -> GitRepoSpec:
    """Parse a git repository specifier into a GitRepoSpec.

    Supports:
        - `github:owner/repo`
        - `github:owner/repo@ref`
        - `https://...` or `git@...`
        - Embedded subpath syntax using `//sub/path`
        - Explicit ref and subpath overrides
    """
    spec = specifier.strip()
    if not spec:
        raise ValueError("Git specifier cannot be empty")

    embedded_subpath: str | None = None
    proto_idx = spec.find("://")
    search_start = proto_idx + 3 if proto_idx != -1 else 0

    subpath_idx = spec.find("//", search_start)
    if subpath_idx != -1:
        embedded_subpath = spec[subpath_idx + 2 :]
        spec = spec[:subpath_idx]

    extracted_ref: str | None = None

    if spec.startswith("github:"):
        body = spec[len("github:") :]
        if "@" in body:
            repo_part, extracted_ref = body.split("@", 1)
        else:
            repo_part = body

        parts = repo_part.strip("/").split("/")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f"Invalid GitHub specifier: {specifier}")

        owner, repo = parts
        if not repo.endswith(".git"):
            repo = f"{repo}.git"
        url = f"https://github.com/{owner}/{repo}"

    elif spec.startswith("git@"):
        if spec.count("@") > 1:
            last_at = spec.rfind("@")
            extracted_ref = spec[last_at + 1 :]
            url = spec[:last_at]
        else:
            url = spec

    elif spec.startswith(("https://", "http://", "ssh://", "git://")):
        parsed = urllib.parse.urlsplit(spec)
        if "@" in parsed.path:
            path_part, extracted_ref = parsed.path.rsplit("@", 1)
            url = urllib.parse.urlunsplit(
                (parsed.scheme, parsed.netloc, path_part, parsed.query, parsed.fragment)
            )
        else:
            url = spec

    else:
        raise ValueError(f"Invalid or unsupported git specifier: {specifier}")

    if embedded_subpath and "@" in embedded_subpath and extracted_ref is None:
        embedded_subpath, extracted_ref = embedded_subpath.split("@", 1)

    final_ref = ref if ref is not None else extracted_ref
    final_subpath = subpath if subpath is not None else embedded_subpath
    if final_subpath is not None:
        final_subpath = final_subpath.strip("/")

    return GitRepoSpec(url=url, ref=final_ref, subpath=final_subpath)


def clone_repo(spec: GitRepoSpec, target_dir: Path) -> None:
    """Clone a Git repository into target_dir using shallow clone."""
    if spec.url.startswith("-") or (spec.ref and spec.ref.startswith("-")):
        raise ValueError("Invalid Git repository URL or ref: cannot start with a dash ('-')")

    target_dir.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["git", "clone", "--depth", "1"]
    if spec.ref:
        cmd.extend(["--branch", spec.ref])
    cmd.extend(["--", spec.url, str(target_dir)])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError as e:
        raise GitCloneError("Git executable not found. Please ensure git is installed.") from e
    except Exception as e:
        raise GitCloneError(f"Failed to execute git clone: {e}") from e

    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip() or f"Process exited with {proc.returncode}"
        raise GitCloneError(f"Failed to clone repository: {err}")


def discover_skills_in_dir(repo_dir: Path, subpath: str | None = None) -> list[DiscoveredSkill]:
    """Discover all valid skills inside a repository directory.

    Searches for `SKILL.md` files while ignoring non-skill directories (.git, .venv, etc.).
    """
    resolved_repo = repo_dir.resolve()
    if subpath:
        search_root = (resolved_repo / subpath).resolve()
        if not search_root.is_relative_to(resolved_repo):
            raise ValueError(f"Invalid subpath traversal: {subpath}")
    else:
        search_root = resolved_repo

    if not search_root.exists() or not search_root.is_dir():
        return []

    # Find SKILL.md candidates avoiding ignored directories
    candidate_skill_files: list[Path] = []
    for skill_file in sorted(search_root.rglob("SKILL.md")):
        rel_parts = skill_file.relative_to(resolved_repo).parts
        if any(part in IGNORED_DIRS for part in rel_parts):
            continue
        candidate_skill_files.append(skill_file)

    all_skill_dirs = [sf.parent for sf in candidate_skill_files]
    discovered: list[DiscoveredSkill] = []

    for skill_file in candidate_skill_files:
        skill_dir = skill_file.parent
        content = skill_file.read_bytes()
        fm = _parse_frontmatter(content)

        name = fm.get("name") or skill_dir.name
        description = fm.get("description") or f"{name} skill"
        slug = fm.get("slug") or _slugify(name)
        version = str(fm.get("version") or "0.1.0")

        # Collect skill files
        files: dict[str, bytes] = {}
        for f in sorted(skill_dir.rglob("*")):
            if not f.is_file() or f.is_symlink():
                continue
            if not f.resolve().is_relative_to(skill_dir.resolve()):
                continue
            rel = f.relative_to(skill_dir)
            if any(
                part in IGNORED_DIRS or (part.startswith(".") and part != ".env.example")
                for part in rel.parts
            ):
                continue
            # Check if file belongs to a child skill directory
            is_child_skill_file = any(
                other_dir != skill_dir
                and other_dir in all_skill_dirs
                and f.is_relative_to(other_dir)
                for other_dir in all_skill_dirs
            )
            if is_child_skill_file:
                continue
            files[rel.as_posix()] = f.read_bytes()

        discovered.append(
            DiscoveredSkill(
                slug=slug,
                name=name,
                version=version,
                description=description,
                files=files,
                path=skill_dir,
            )
        )

    return discovered


def import_from_git(
    specifier: str,
    ref: str | None = None,
    subpath: str | None = None,
    namespace: str = "public",
    client: Any = None,
    registry: Any = None,
) -> list[ImportResult]:
    """Import and publish skills directly from a remote Git repository."""
    spec = parse_git_specifier(specifier, ref=ref, subpath=subpath)
    ns = namespace or "public"

    with tempfile.TemporaryDirectory() as tmp_dir:
        clone_target = Path(tmp_dir) / "repo"
        clone_repo(spec, clone_target)
        discovered = discover_skills_in_dir(clone_target, subpath=spec.subpath)
        if not discovered:
            return []

        results: list[ImportResult] = []
        active_client = client
        created_client = None
        if active_client is None and registry is None:
            from open_skill_registry.client.main import SkillRegistryClient

            created_client = SkillRegistryClient()
            created_client.__enter__()
            active_client = created_client

        try:
            for skill in discovered:
                try:
                    version = skill.version
                    content_hash = None
                    pub_slug = skill.slug
                    pub_ns = ns

                    if active_client is not None:
                        if hasattr(active_client, "publish_skill"):
                            res = active_client.publish_skill(
                                namespace=ns,
                                slug=skill.slug,
                                version=version,
                                files=skill.files,
                            )
                        elif hasattr(active_client, "publish"):
                            res = active_client.publish(
                                namespace=ns,
                                slug=skill.slug,
                                version=version,
                                files=skill.files,
                            )
                        else:
                            raise ValueError(
                                "Provided client does not have publish or publish_skill method"
                            )

                        if isinstance(res, dict):
                            content_hash = res.get("content_hash")
                            version = res.get("version", version)
                            pub_slug = res.get("slug", pub_slug)
                            pub_ns = res.get("namespace", pub_ns)
                        else:
                            content_hash = getattr(res, "content_hash", None)
                            version = getattr(res, "version", version)
                            pub_slug = getattr(res, "slug", pub_slug)
                            pub_ns = getattr(res, "namespace", pub_ns)

                    elif registry is not None:
                        if hasattr(registry, "publish"):
                            res = registry.publish(
                                namespace=ns,
                                slug=skill.slug,
                                version=version,
                                files=skill.files,
                            )
                        elif hasattr(registry, "publish_skill"):
                            res = registry.publish_skill(
                                namespace=ns,
                                slug=skill.slug,
                                version=version,
                                files=skill.files,
                            )
                        else:
                            raise ValueError(
                                "Provided registry does not have publish or publish_skill method"
                            )

                        if isinstance(res, dict):
                            content_hash = res.get("content_hash")
                            version = res.get("version", version)
                            pub_slug = res.get("slug", pub_slug)
                            pub_ns = res.get("namespace", pub_ns)
                        else:
                            content_hash = getattr(res, "content_hash", None)
                            version = getattr(res, "version", version)
                            pub_slug = getattr(res, "slug", pub_slug)
                            pub_ns = getattr(res, "namespace", pub_ns)

                    results.append(
                        ImportResult(
                            namespace=pub_ns,
                            slug=pub_slug,
                            version=version,
                            name=skill.name,
                            files_count=len(skill.files),
                            content_hash=content_hash,
                            success=True,
                            error=None,
                            status="published",
                        )
                    )
                except Exception as e:
                    results.append(
                        ImportResult(
                            namespace=ns,
                            slug=skill.slug,
                            version=skill.version,
                            name=skill.name,
                            files_count=len(skill.files),
                            content_hash=None,
                            success=False,
                            error=str(e),
                            status="failed",
                        )
                    )
        finally:
            if created_client is not None:
                created_client.__exit__(None, None, None)

        return results
