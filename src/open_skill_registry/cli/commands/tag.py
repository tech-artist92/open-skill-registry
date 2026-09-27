import sys

import typer
from httpx import Client, HTTPError
from rich.console import Console

console = Console()
app = typer.Typer(help="Manage release tags for skills.")

@app.command("tag")
def tag(
    skill_identifier: str = typer.Argument(..., help="Namespace and slug of the skill (e.g. public/my-skill)"),
    version: str = typer.Argument(..., help="Version to tag (e.g. 1.0.0)"),
    tag_name: str = typer.Argument(..., help="Name of the tag (e.g. production)"),
    url: str = typer.Option("http://localhost:8080", "--url", "-u", help="Base URL of the registry API")
):
    """
    Assign a release tag to a specific version of a skill.
    """
    if "/" in skill_identifier:
        namespace, slug = skill_identifier.split("/", 1)
    else:
        namespace = "public"
        slug = skill_identifier

    endpoint = f"{url.rstrip('/')}/api/v1/skills/{namespace}/{slug}/tags/{tag_name}"

    try:
        with Client() as client:
            response = client.put(endpoint, json={"version": version})
            
            if response.status_code == 200:
                console.print(f"[green]Successfully assigned tag '{tag_name}' to {namespace}/{slug} @ {version}[/green]")
            else:
                try:
                    error_data = response.json()
                    detail = error_data.get("detail", response.text)
                except ValueError:
                    detail = response.text
                console.print(f"[red]Error {response.status_code}: {detail}[/red]")
                sys.exit(1)
    except HTTPError as e:
        console.print(f"[red]Connection error: {e}[/red]")
        sys.exit(1)
