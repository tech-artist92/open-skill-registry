import typer
from rich.console import Console
from pathlib import Path
import hashlib
from open_skill_registry.client.main import SkillRegistryClient
from open_skill_registry.registry.core.validator import validate_package
from open_skill_registry.registry.core.manifest import compute_manifest


console = Console()

def parse_skill_name(skill: str) -> tuple[str, str]:
    if "/" in skill:
        ns, slug = skill.split("/", 1)
        return ns, slug
    return "public", skill


def verify(
    ctx: typer.Context,
    local_dir: str = typer.Argument(..., help="Path to local directory to verify."),
    remote: str = typer.Option(None, "--remote", help="Remote skill to verify against (e.g., namespace/slug)."),
    version: str = typer.Option(None, "--version", help="Specific remote version to verify against.")
):
    """Verify cryptographic hashes of a local skill package."""
    target_dir = Path(local_dir)
    if not target_dir.exists():
        console.print(f"[red]Directory not found: {local_dir}[/red]")
        raise typer.Exit(1)

    if remote:
        registry_url = (ctx.obj or {}).get("registry_url") or "http://localhost:8080"
        ns, slug = parse_skill_name(remote)
        
        try:
            with SkillRegistryClient(
                base_url=registry_url,
                api_key=(ctx.obj or {}).get("api_key")
            ) as client:
                if not version:
                    skill_info = client.get_skill(ns, slug)
                    version = skill_info.get("release_tags", {}).get("latest")
                    if not version:
                        version = skill_info.get("tags", {}).get("latest") or skill_info.get("latest_version") or skill_info.get("version")
                    if not version:
                        console.print(f"[red]Could not resolve latest version for {remote}[/red]")
                        raise typer.Exit(1)
                
                version_info = client.get_version(ns, slug, version)
                manifest = version_info.get("manifest", {})
                entries = manifest.get("entries", [])
                
                for entry in entries:
                    path = entry.get("path")
                    expected_hash = entry.get("hash")
                    
                    local_file = target_dir / path
                    if not local_file.exists():
                        console.print(f"[red]Missing file: {path}[/red]")
                        raise typer.Exit(1)
                    
                    content = local_file.read_bytes()
                    computed_hash = hashlib.sha256(content).hexdigest()
                    
                    if computed_hash != expected_hash:
                        console.print(f"[red]Hash mismatch for {path}: expected {expected_hash}, got {computed_hash}[/red]")
                        raise typer.Exit(1)
                        
                console.print("[green]All files verified against remote manifest.[/green]")
        except typer.Exit:
            raise
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
    else:
        # Local verification
        try:
            # compute_manifest takes a dictionary of path -> bytes
            files = {}
            for file_path in target_dir.rglob("*"):
                if file_path.is_file():
                    rel_path = file_path.relative_to(target_dir).as_posix()
                    files[rel_path] = file_path.read_bytes()

            errors = validate_package(files)
            if errors:
                for err in errors:
                    console.print(f"[red]Error: {err}[/red]")
                raise typer.Exit(code=1)
                
            manifest = compute_manifest(files)
            console.print("[green]Local package is valid.[/green]")
            for p in sorted(files.keys()):
                typer.echo(f"  - {p}")
            console.print(f"Content Hash: {manifest.content_hash}")
        except typer.Exit:
            raise
        except Exception as e:
            console.print(f"[red]Validation failed:[/red] {e}")
            raise typer.Exit(1)

