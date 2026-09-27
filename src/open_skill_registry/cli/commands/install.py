"""Universal Workspace Installer command for Open Skill Registry (T065)."""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from open_skill_registry.client.main import SkillRegistryClient

console = Console(soft_wrap=True)

SUPPORTED_TARGETS = {"cursor", "claude", "adk", "agents", "local"}


def parse_skill_name(skill: str) -> tuple[str, str]:
    """Parse a skill identifier into (namespace, slug). Defaults namespace to 'public'."""
    if "/" in skill:
        ns, slug = skill.split("/", 1)
    else:
        ns, slug = "public", skill

    if not re.match(r"^[a-zA-Z0-9_\-]+$", slug):
        console.print(
            f"[red]Error: Invalid skill slug '{slug}'. "
            "Must be alphanumeric with hyphens or underscores.[/red]"
        )
        raise typer.Exit(1)
    if not re.match(r"^[a-zA-Z0-9_\-]+$", ns):
        console.print(
            f"[red]Error: Invalid namespace '{ns}'. "
            "Must be alphanumeric with hyphens or underscores.[/red]"
        )
        raise typer.Exit(1)
    return ns, slug


def detect_workspace_target(workspace: Path | None = None) -> str:
    """
    Detect the agent environment target for the given workspace.

    Heuristic precedence:
    1. .cursor/ -> cursor
    2. .claude/ -> claude
    3. .agents/ -> agents
    4. fallback -> local
    """
    if workspace is None:
        workspace = Path.cwd()

    if (workspace / ".cursor").is_dir():
        return "cursor"
    if (workspace / ".claude").is_dir():
        return "claude"
    if (workspace / ".agents").is_dir():
        return "agents"
    return "local"


def resolve_target_dir(
    target: str,
    slug: str,
    workspace: Path | None = None,
) -> tuple[Path, str, bool]:
    """
    Resolve the filesystem destination directory for the skill.

    Returns:
        tuple of (absolute_target_dir, relative_or_display_path, is_global)
    """
    if workspace is None:
        workspace = Path.cwd()

    target_lower = target.lower()
    if target_lower not in SUPPORTED_TARGETS:
        targets_str = ", ".join(sorted(SUPPORTED_TARGETS))
        raise ValueError(f"Unsupported target '{target}'. Supported targets: {targets_str}")

    if target_lower == "cursor":
        target_dir = workspace / ".cursor" / "skills" / slug
        display_path = f".cursor/skills/{slug}"
        is_global = False
    elif target_lower == "claude":
        target_dir = workspace / ".claude" / "skills" / slug
        display_path = f".claude/skills/{slug}"
        is_global = False
    elif target_lower in ("adk", "agents"):
        target_dir = workspace / ".agents" / "skills" / slug
        display_path = f".agents/skills/{slug}"
        is_global = False
    elif target_lower == "local":
        if (workspace / ".agents").is_dir():
            target_dir = workspace / ".agents" / "skills" / slug
            display_path = f".agents/skills/{slug}"
            is_global = False
        else:
            target_dir = Path.home() / ".osr" / "skills" / slug
            display_path = str(target_dir)
            is_global = True
    else:
        raise ValueError(f"Unsupported target '{target}'")

    return target_dir, display_path, is_global


def get_manifest_path(workspace: Path | None = None, is_global: bool = False) -> Path:
    """Return the tracking manifest path for workspace or global installs."""
    if workspace is None:
        workspace = Path.cwd()
    if is_global:
        return Path.home() / ".osr" / "installed.json"
    return workspace / ".osr-installed.json"


def load_installed_manifest(
    workspace: Path | None = None, is_global: bool | None = None
) -> dict[str, Any]:
    """Load installed skills manifest.

    If is_global is True: loads from global manifest (~/.osr/installed.json).
    If is_global is False: loads from workspace manifest (<workspace>/.osr-installed.json).
    If is_global is None: loads workspace manifest if it exists, otherwise global manifest.
    """
    if workspace is None:
        workspace = Path.cwd()

    if is_global is True:
        global_manifest = Path.home() / ".osr" / "installed.json"
        if global_manifest.exists():
            try:
                data = json.loads(global_manifest.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {}

    if is_global is False:
        ws_manifest = workspace / ".osr-installed.json"
        if ws_manifest.exists():
            try:
                data = json.loads(ws_manifest.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {}

    ws_manifest = workspace / ".osr-installed.json"
    if ws_manifest.exists():
        try:
            data = json.loads(ws_manifest.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    global_manifest = Path.home() / ".osr" / "installed.json"
    if global_manifest.exists():
        try:
            data = json.loads(global_manifest.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return {}


def save_installed_manifest(
    manifest: dict[str, Any],
    workspace: Path | None = None,
    is_global: bool = False,
) -> None:
    """Save installed skills manifest."""
    if workspace is None:
        workspace = Path.cwd()
    manifest_path = get_manifest_path(workspace, is_global=is_global)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def install_skill_files(
    client: SkillRegistryClient,
    namespace: str,
    slug: str,
    version: str,
    target_dir: Path,
) -> tuple[str, int]:
    """Download skill package files, verify sha256 checksums, and write to destination."""
    version_info = client.get_version(namespace, slug, version)
    manifest = version_info.get("manifest", {})
    entries = manifest.get("files") or manifest.get("entries", [])
    content_hash = manifest.get("content_hash") or version_info.get("content_hash", "unknown")

    target_dir.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        path = entry.get("path")
        if not path or ".." in path or path.startswith("/") or path.startswith("\\"):
            console.print(
                f"[red]Error: Path traversal attempt detected in package file '{path}'[/red]"
            )
            raise typer.Exit(1)

        out_file = (target_dir / path).resolve()
        if not out_file.is_relative_to(target_dir.resolve()):
            console.print(f"[red]Error: File path '{path}' escapes target directory[/red]")
            raise typer.Exit(1)

        expected_hash = entry.get("hash")

        content = client.get_file(namespace, slug, version, path)
        if expected_hash:
            computed_hash = hashlib.sha256(content).hexdigest()
            if computed_hash != expected_hash:
                console.print(
                    f"[red]Hash mismatch for {path}: "
                    f"expected {expected_hash}, got {computed_hash}[/red]"
                )
                raise typer.Exit(1)

        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(content)

    return content_hash, len(entries)


def install(
    ctx: typer.Context,
    skill: str = typer.Argument(..., help="Skill name in format <namespace>/<slug> or <slug>"),
    target: str | None = typer.Option(
        None, "--target", help="Target agent environment (cursor, claude, adk, agents, local)."
    ),
    version: str | None = typer.Option(None, "--version", help="Specific version to install."),
) -> None:
    """Install a skill into workspace or local agent environment."""
    workspace = Path.cwd()

    if target is not None and target.lower() not in SUPPORTED_TARGETS:
        targets_str = ", ".join(sorted(SUPPORTED_TARGETS))
        console.print(f"[red]Invalid target '{target}'. Supported targets: {targets_str}[/red]")
        raise typer.Exit(1)

    effective_target = target.lower() if target else detect_workspace_target(workspace)
    namespace, slug = parse_skill_name(skill)

    try:
        target_dir, display_path, is_global = resolve_target_dir(effective_target, slug, workspace)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    registry_url = (ctx.obj or {}).get("registry_url") or "http://localhost:8080"
    transport = (ctx.obj or {}).get("transport")
    client_kwargs: dict[str, Any] = {
        "base_url": registry_url,
        "api_key": (ctx.obj or {}).get("api_key"),
    }
    if transport is not None:
        client_kwargs["transport"] = transport

    try:
        with SkillRegistryClient(**client_kwargs) as client:
            if not version:
                tag = "latest"
                skill_info = client.get_skill(namespace, slug)
                version = (
                    skill_info.get("release_tags", {}).get(tag)
                    or skill_info.get("tags", {}).get(tag)
                    or skill_info.get("latest_version")
                    or skill_info.get("version")
                )
                if not version:
                    console.print(f"[red]Could not resolve version for {skill}[/red]")
                    raise typer.Exit(1)

            content_hash, file_count = install_skill_files(
                client, namespace, slug, version, target_dir
            )

            manifest_data = load_installed_manifest(workspace, is_global=is_global)
            manifest_key = f"{namespace}/{slug}"
            manifest_data[manifest_key] = {
                "namespace": namespace,
                "slug": slug,
                "version": version,
                "target": effective_target,
                "path": str(display_path),
                "content_hash": content_hash,
                "installed_at": datetime.now(UTC).isoformat(),
                "is_global": is_global,
            }
            save_installed_manifest(manifest_data, workspace, is_global=is_global)

            console.print(
                f"[green]Successfully installed {namespace}/{slug}@{version} "
                f"into {display_path}[/green]"
            )
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e
