import io
import zipfile
import typer
import httpx
from pathlib import Path
from typing import Optional

app = typer.Typer(help="Push a skill to the registry.")

@app.callback(invoke_without_command=True)
def push_command(
    ctx: typer.Context,
    path: Path = typer.Argument(..., exists=True, help="Path to SKILL.md, zip archive or directory"),
    namespace: str = typer.Option("public", "--namespace", "-n", help="Namespace to publish under"),
    version: Optional[str] = typer.Option(None, "--version", "-v", help="Explicit version"),
    slug: Optional[str] = typer.Option(None, "--slug", "-s", help="Explicit slug"),
    batch: bool = typer.Option(False, "--batch", help="Batch publish directory")
):
    """Push a skill to the registry."""
    registry_url = (ctx.obj or {}).get("registry_url") if hasattr(ctx, "obj") and ctx.obj else None
    registry_url = registry_url or "http://localhost:8080"
    
    if batch and path.is_dir():
        for item in path.iterdir():
            if item.is_dir():
                _push_single(item, namespace, None, None, registry_url)
    else:
        _push_single(path, namespace, version, slug, registry_url)

def _push_single(p: Path, namespace: str, version: Optional[str], slug: Optional[str], registry_url: str):
    url = f"{registry_url.rstrip('/')}/api/v1/skills/publish"
    
    files_payload = []
    
    if p.is_file() and p.suffix == ".zip":
        files_payload.append(("file", (p.name, p.read_bytes(), "application/zip")))
    elif p.is_file() and p.name == "SKILL.md":
        files_payload.append(("file", (p.name, p.read_bytes(), "text/markdown")))
    elif p.is_dir():
        skill_md = p / "SKILL.md"
        if not skill_md.exists():
            typer.echo(f"Skipping {p}: No SKILL.md found.")
            return
        
        # Package directory contents into an in-memory zip
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in p.rglob("*"):
                if file_path.is_file():
                    rel_parts = file_path.relative_to(p).parts
                    if any(part.startswith(".") or part == "__pycache__" for part in rel_parts):
                        continue
                    zf.write(file_path, arcname=str(file_path.relative_to(p)))
        zip_buf.seek(0)
        zip_name = f"{slug or p.name}.zip"
        files_payload.append(("file", (zip_name, zip_buf.getvalue(), "application/zip")))
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
            typer.echo(
                f"Successfully published {res_data.get('namespace')}/{res_data.get('slug')} @ {res_data.get('version')} "
                f"(hash: {res_data.get('content_hash', 'unknown')})"
            )
        else:
            typer.echo(f"Failed to publish: {response.text}")
    except Exception as e:
        typer.echo(f"Error publishing: {e}")
