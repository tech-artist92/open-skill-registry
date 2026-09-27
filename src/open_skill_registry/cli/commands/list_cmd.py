"""Universal Workspace and Registry List command for Open Skill Registry (T066)."""

from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from open_skill_registry.cli.commands.install import load_installed_manifest
from open_skill_registry.client.main import SkillRegistryClient

console = Console(soft_wrap=True)


def list_command(
    ctx: typer.Context,
    installed: bool = typer.Option(
        False, "--installed", help="List locally installed skills instead of remote registry."
    ),
    namespace: str | None = typer.Option(None, "--namespace", help="Filter by namespace."),
    page: int = typer.Option(1, "--page", help="Page number for remote registry listing."),
    size: int = typer.Option(20, "--size", help="Page size for remote registry listing."),
    format: str | None = typer.Option(None, "--format", help="Output format (text | json)."),
) -> None:
    """List skills in the remote registry or locally installed skills."""
    out_format = format or (ctx.obj or {}).get("format", "text")
    workspace = Path.cwd()

    if installed:
        manifest = load_installed_manifest(workspace)
        if out_format == "json":
            installed_list = []
            for key, val in manifest.items():
                item = dict(val)
                if "name" not in item:
                    item["name"] = key
                installed_list.append(item)
            console.print_json(data=installed_list)
        else:
            if not manifest:
                console.print("No installed skills found.")
                return

            table = Table(title="Installed Skills")
            table.add_column("NAME", style="cyan")
            table.add_column("VERSION", style="magenta")
            table.add_column("TARGET", style="green")
            table.add_column("PATH")

            for key, val in sorted(manifest.items()):
                name = key
                ver = val.get("version", "N/A")
                target = val.get("target", "N/A")
                path = val.get("path", "N/A")
                table.add_row(name, ver, target, path)

            console.print(table)
    else:
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
                results = client.list_skills(page=page, size=size, namespace=namespace)
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(code=1) from e

        if out_format == "json":
            console.print_json(data=results)
        else:
            table = Table(title="Registry Skills")
            table.add_column("NAME", style="cyan")
            table.add_column("NAMESPACE", style="green")
            table.add_column("LATEST VERSION", style="magenta")
            table.add_column("DESCRIPTION")

            items = results.get("items", []) if isinstance(results, dict) else results
            if not items:
                console.print("No skills found in registry.")
                return

            for item in items:
                name = item.get("name") or item.get("slug", "")
                ns = item.get("namespace", "")
                ver = item.get("latest_version") or item.get("version", "N/A")
                desc = item.get("description", "")
                table.add_row(name, ns, ver, desc)

            console.print(table)
