import typer
from rich.console import Console
import json
from open_skill_registry.client.main import SkillRegistryClient
from open_skill_registry.client.exceptions import NotFoundError

app = typer.Typer()
console = Console()

def parse_skill_name(skill: str) -> tuple[str, str]:
    if "/" in skill:
        ns, slug = skill.split("/", 1)
        return ns, slug
    return "public", skill


def info(
    ctx: typer.Context,
    skill: str = typer.Argument(..., help="Skill name in format <namespace>/<slug> or <slug>"),
    version: str = typer.Option(None, "--version", help="Specific version to get info for.")
):
    """Get detailed information about a skill."""
    client = SkillRegistryClient(
        base_url=ctx.obj.get("registry_url"),
        api_key=ctx.obj.get("api_key")
    )
    
    ns, slug = parse_skill_name(skill)
    try:
        data = client.get_skill(ns, slug)
    except NotFoundError:
        console.print(f"[red]Skill '{skill}' not found.[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
        
    out_format = ctx.obj.get("format", "text")
    if out_format == "json":
        console.print_json(data=data)
    else:
        console.print(f"[bold cyan]Name:[/bold cyan] {data.get('name')}")
        console.print(f"[bold cyan]Slug:[/bold cyan] {data.get('slug')}")
        console.print(f"[bold cyan]Namespace:[/bold cyan] {data.get('namespace')}")
        console.print(f"[bold cyan]Description:[/bold cyan] {data.get('description')}")
        console.print(f"[bold cyan]Latest Version:[/bold cyan] {data.get('latest_version')}")
        console.print(f"[bold cyan]Download Count:[/bold cyan] {data.get('download_count')}")
        
        tags = data.get("release_tags", {})
        if tags:
            console.print("\n[bold cyan]Release Tags:[/bold cyan]")
            for tag, ver in tags.items():
                console.print(f"  {tag}: {ver}")
                
        versions = data.get("versions", [])
        if versions:
            console.print("\n[bold cyan]Versions:[/bold cyan]")
            for v in versions:
                console.print(f"  {v.get('version')} (Created: {v.get('created_at')})")

