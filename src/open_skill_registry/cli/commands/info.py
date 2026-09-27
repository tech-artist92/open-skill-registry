import typer
from rich.console import Console
import json
from open_skill_registry.client.main import SkillRegistryClient
from open_skill_registry.client.exceptions import NotFoundError

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
    registry_url = (ctx.obj or {}).get("registry_url") or "http://localhost:8080"
    transport = (ctx.obj or {}).get("transport")
    
    ns, slug = parse_skill_name(skill)
    
    client_kwargs = {
        "base_url": registry_url,
        "api_key": (ctx.obj or {}).get("api_key"),
    }
    if transport is not None:
        client_kwargs["transport"] = transport

    try:
        with SkillRegistryClient(**client_kwargs) as client:
            if version:
                data = client.get_version(ns, slug, version)
            else:
                data = client.get_skill(ns, slug)
    except NotFoundError:
        console.print(f"[red]Skill '{skill}' not found.[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
        
    out_format = (ctx.obj or {}).get("format", "text")
    if out_format == "json":
        console.print_json(data=data)
    else:
        if version:
            console.print(f"[bold cyan]Version:[/bold cyan] {data.get('version')}")
            console.print(f"[bold cyan]Content Hash:[/bold cyan] {data.get('content_hash')}")
            
            frontmatter = data.get("frontmatter", {})
            if frontmatter:
                console.print("\n[bold cyan]Frontmatter:[/bold cyan]")
                for k, v in frontmatter.items():
                    console.print(f"  {k}: {v}")
                    
            manifest = data.get("manifest", {})
            entries = manifest.get("entries", [])
            console.print(f"\n[bold cyan]Manifest Files Count:[/bold cyan] {len(entries)}")
            
            compliance = data.get("compliance_snapshot", {})
            if compliance:
                console.print("\n[bold cyan]Compliance Snapshot:[/bold cyan]")
                for k, v in compliance.items():
                    console.print(f"  {k}: {v}")
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
                    if isinstance(v, dict):
                        console.print(f"  {v.get('version')} (Created: {v.get('created_at')})")
                    else:
                        console.print(f"  {v}")

