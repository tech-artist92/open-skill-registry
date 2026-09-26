import typer
import httpx
from pathlib import Path
from typing import Optional

app = typer.Typer(help="Push a skill to the registry.")

@app.callback(invoke_without_command=True)
def push_command(
    path: Path = typer.Argument(..., exists=True, help="Path to SKILL.md, zip archive or directory"),
    namespace: str = typer.Option("public", "--namespace", "-n", help="Namespace to publish under"),
    version: Optional[str] = typer.Option(None, "--version", "-v", help="Explicit version"),
    slug: Optional[str] = typer.Option(None, "--slug", "-s", help="Explicit slug"),
    batch: bool = typer.Option(False, "--batch", help="Batch publish directory")
):
    """Push a skill to the registry."""
    if batch and path.is_dir():
        for item in path.iterdir():
            if item.is_dir():
                _push_single(item, namespace, None, None)
    else:
        _push_single(path, namespace, version, slug)

def _push_single(p: Path, namespace: str, version: Optional[str], slug: Optional[str]):
    url = "http://localhost:8000/api/v1/skills/publish"
    
    files_payload = []
    
    if p.is_file() and p.suffix == ".zip":
        files_payload.append(("file", (p.name, p.read_bytes(), "application/zip")))
    elif p.is_file() and p.name == "SKILL.md":
        files_payload.append(("file", (p.name, p.read_bytes(), "text/markdown")))
    elif p.is_dir():
        skill_md = p / "SKILL.md"
        if skill_md.exists():
            files_payload.append(("file", ("SKILL.md", skill_md.read_bytes(), "text/markdown")))
        else:
            typer.echo(f"Skipping {p}: No SKILL.md found.")
            return
    else:
        typer.echo("Invalid path. Must be SKILL.md, zip archive or directory containing SKILL.md")
        return
        
    data = {"namespace": namespace}
    if slug:
        data["slug"] = slug
    if version:
        data["version"] = version
        
    try:
        response = httpx.post(url, data=data, files=files_payload)
        if response.status_code == 201:
            res_data = response.json().get("data", {})
            typer.echo(f"Successfully published {res_data.get('namespace')}/{res_data.get('slug')} @ {res_data.get('version')}")
        else:
            typer.echo(f"Failed to publish: {response.text}")
    except Exception as e:
        typer.echo(f"Error publishing: {e}")
