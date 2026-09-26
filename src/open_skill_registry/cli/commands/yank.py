"""CLI command for yanking a faulty skill version (T052)."""

import typer
from rich.console import Console

from open_skill_registry.client.main import SkillRegistryClient

console = Console()
err_console = Console(stderr=True)


def parse_skill_name(skill: str) -> tuple[str, str]:
    """Parse namespace and slug from skill identifier, defaulting namespace to 'public'."""
    if "/" in skill:
        ns, slug = skill.split("/", 1)
        return ns, slug
    return "public", skill


def yank(
    ctx: typer.Context,
    skill: str = typer.Argument(
        ..., help="Skill identifier in format <namespace>/<slug> or <slug> (defaults to public)"
    ),
    version: str = typer.Argument(..., help="Version to yank (e.g. 1.1.0)"),
    url: str | None = typer.Option(None, "--url", "-u", help="Base URL of the registry API"),
) -> None:
    """Yank a faulty skill version from the registry."""
    registry_url = url or (ctx.obj or {}).get("registry_url") or "http://localhost:8080"
    api_key = (ctx.obj or {}).get("api_key")

    namespace, slug = parse_skill_name(skill)

    try:
        with SkillRegistryClient(base_url=registry_url, api_key=api_key) as client:
            client.yank_version(namespace, slug, version)
            console.print(f"[green]Successfully yanked {namespace}/{slug}@{version}[/green]")
    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e
