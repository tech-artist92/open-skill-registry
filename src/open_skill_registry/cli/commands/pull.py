import typer
from rich.console import Console
import hashlib
from pathlib import Path
from open_skill_registry.client.main import SkillRegistryClient


console = Console()

def parse_skill_name(skill: str) -> tuple[str, str]:
    if "/" in skill:
        ns, slug = skill.split("/", 1)
        return ns, slug
    return "public", skill


def pull(
    ctx: typer.Context,
    skill: str = typer.Argument(..., help="Skill name in format <namespace>/<slug> or <slug>"),
    version: str = typer.Option(None, "--version", help="Specific version to pull."),
    tag: str = typer.Option(None, "--tag", help="Specific tag to pull (e.g. latest)."),
    output: str = typer.Option(None, "--output", help="Directory to pull the skill into.")
):
    """Pull a skill from the registry to local disk."""
    registry_url = (ctx.obj or {}).get("registry_url") or "http://localhost:8080"
    ns, slug = parse_skill_name(skill)

    try:
        with SkillRegistryClient(
            base_url=registry_url,
            api_key=(ctx.obj or {}).get("api_key")
        ) as client:
            if not version:
                if not tag:
                    tag = "latest"
                skill_info = client.get_skill(ns, slug)
                version = skill_info.get("release_tags", {}).get(tag)
                if not version:
                    version = skill_info.get("tags", {}).get(tag) or skill_info.get("latest_version") or skill_info.get("version")
                if not version:
                    console.print(f"[red]Could not resolve tag {tag} for {skill}[/red]")
                    raise typer.Exit(1)
            
            version_info = client.get_version(ns, slug, version)
            manifest = version_info.get("manifest", {})
            entries = manifest.get("entries", [])
            content_hash = manifest.get("content_hash", "unknown")
            
            if output:
                target_dir = Path(output)
            else:
                if Path(".agents").exists():
                    target_dir = Path(".agents/skills") / slug
                else:
                    target_dir = Path.home() / ".osr/skills" / slug
                    
            target_dir.mkdir(parents=True, exist_ok=True)
            
            for entry in entries:
                path = entry.get("path")
                expected_hash = entry.get("hash")
                
                content = client.get_file(ns, slug, version, path)
                computed_hash = hashlib.sha256(content).hexdigest()
                
                if computed_hash != expected_hash:
                    console.print(f"[red]Hash mismatch for {path}: expected {expected_hash}, got {computed_hash}[/red]")
                    raise typer.Exit(1)
                    
                out_file = target_dir / path
                out_file.parent.mkdir(parents=True, exist_ok=True)
                out_file.write_bytes(content)
                
            console.print(f"[green]Successfully pulled {skill}@{version}[/green]")
            console.print(f"Verified {len(entries)} files.")
            console.print(f"Content Hash: {content_hash}")
            
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

