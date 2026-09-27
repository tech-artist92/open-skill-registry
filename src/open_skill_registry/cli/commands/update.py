"""Universal Workspace Update command for Open Skill Registry (T065)."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from packaging.version import InvalidVersion
from packaging.version import parse as parse_version
from rich.console import Console

from open_skill_registry.cli.commands.install import (
    detect_workspace_target,
    install_skill_files,
    load_installed_manifest,
    resolve_target_dir,
    save_installed_manifest,
)
from open_skill_registry.client.main import SkillRegistryClient

console = Console(soft_wrap=True)


def is_newer_version(candidate: str, current: str) -> bool:
    """Compare candidate version against current version using semver or lexical fallback."""
    try:
        return bool(parse_version(candidate) > parse_version(current))
    except InvalidVersion:
        return bool(candidate != current)


def find_installed_skill_key(manifest: dict[str, Any], slug_or_name: str) -> str | None:
    """Find the manifest key for a given slug or namespace/slug."""
    if slug_or_name in manifest:
        return slug_or_name

    public_key = f"public/{slug_or_name}"
    if public_key in manifest:
        return public_key

    for key, val in manifest.items():
        if val.get("slug") == slug_or_name or key.endswith(f"/{slug_or_name}"):
            return key

    return None


def update(
    ctx: typer.Context,
    slug: str | None = typer.Argument(None, help="Optional skill name or slug to update."),
) -> None:
    """Update installed skills to their latest versions."""
    workspace = Path.cwd()
    manifest = load_installed_manifest(workspace)

    if slug is not None:
        matched_key = find_installed_skill_key(manifest, slug)
        if not matched_key:
            console.print(f"[red]Error: Skill '{slug}' is not installed.[/red]")
            raise typer.Exit(1)
    elif not manifest:
        console.print("No installed skills found to update.")
        return

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
            if slug is not None:
                matched_key = find_installed_skill_key(manifest, slug)
                if not matched_key:
                    console.print(f"[red]Error: Skill '{slug}' is not installed.[/red]")
                    raise typer.Exit(1)

                item = manifest[matched_key]
                ns = item.get("namespace", "public")
                s = item.get("slug", slug)
                current_version = item.get("version", "0.0.0")
                target = item.get("target") or detect_workspace_target(workspace)

                skill_info = client.get_skill(ns, s)
                latest_version = (
                    skill_info.get("release_tags", {}).get("latest")
                    or skill_info.get("tags", {}).get("latest")
                    or skill_info.get("latest_version")
                    or skill_info.get("version")
                )
                if not latest_version:
                    console.print(f"[red]Could not determine latest version for {ns}/{s}[/red]")
                    raise typer.Exit(1)

                if is_newer_version(latest_version, current_version):
                    target_dir, display_path, is_global = resolve_target_dir(target, s, workspace)
                    content_hash, _ = install_skill_files(client, ns, s, latest_version, target_dir)
                    item["version"] = latest_version
                    item["content_hash"] = content_hash
                    item["installed_at"] = datetime.now(UTC).isoformat()
                    manifest[matched_key] = item
                    save_installed_manifest(manifest, workspace, is_global=is_global)
                    console.print(
                        f"[green]Successfully updated {ns}/{s} from {current_version} "
                        f"to {latest_version}[/green]"
                    )
                else:
                    console.print(f"{ns}/{s} is already up to date ({current_version}).")
            else:
                updated: list[tuple[str, str, str]] = []
                up_to_date: list[tuple[str, str]] = []
                failed: list[tuple[str, str]] = []

                for key, item in list(manifest.items()):
                    ns = item.get("namespace", "public")
                    s = item.get("slug", key.split("/")[-1])
                    current_version = item.get("version", "0.0.0")
                    target = item.get("target") or detect_workspace_target(workspace)

                    try:
                        skill_info = client.get_skill(ns, s)
                        latest_version = (
                            skill_info.get("release_tags", {}).get("latest")
                            or skill_info.get("tags", {}).get("latest")
                            or skill_info.get("latest_version")
                            or skill_info.get("version")
                        )
                        if not latest_version:
                            failed.append((f"{ns}/{s}", "Could not resolve latest version"))
                            continue

                        if is_newer_version(latest_version, current_version):
                            target_dir, display_path, is_global = resolve_target_dir(
                                target, s, workspace
                            )
                            content_hash, _ = install_skill_files(
                                client, ns, s, latest_version, target_dir
                            )
                            item["version"] = latest_version
                            item["content_hash"] = content_hash
                            item["installed_at"] = datetime.now(UTC).isoformat()
                            manifest[key] = item
                            save_installed_manifest(manifest, workspace, is_global=is_global)
                            updated.append((f"{ns}/{s}", current_version, latest_version))
                        else:
                            up_to_date.append((f"{ns}/{s}", current_version))
                    except Exception as e:
                        failed.append((f"{ns}/{s}", str(e)))

                console.print("[bold]Skill Update Summary:[/bold]")
                if updated:
                    console.print("[green]Updated skills:[/green]")
                    for skill_name, old_ver, new_ver in updated:
                        console.print(f"  • {skill_name}: {old_ver} -> {new_ver}")
                if up_to_date:
                    console.print("[cyan]Up-to-date skills:[/cyan]")
                    for skill_name, ver in up_to_date:
                        console.print(f"  • {skill_name}: {ver}")
                if failed:
                    console.print("[red]Failed updates:[/red]")
                    for skill_name, err in failed:
                        console.print(f"  • {skill_name}: {err}")
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e
