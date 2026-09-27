"""Namespace CLI management commands (T048)."""


import typer
from rich.console import Console
from rich.table import Table

from open_skill_registry.client.main import SkillRegistryClient

app = typer.Typer(help="Manage namespaces in the registry.", no_args_is_help=True)
console = Console()


def get_client(ctx: typer.Context) -> SkillRegistryClient:
    obj = ctx.obj or {}
    url = obj.get("registry_url") or "http://localhost:8080"
    api_key = obj.get("api_key")
    return SkillRegistryClient(base_url=url, api_key=api_key)


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    page: int = typer.Option(1, "--page", help="Page number"),
    size: int = typer.Option(20, "--size", help="Page size"),
):
    """List namespaces."""
    try:
        with get_client(ctx) as client:
            result = client.list_namespaces(page=page, size=size)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)

    items = result.get("items", result) if isinstance(result, dict) else result

    out_format = (ctx.obj or {}).get("format", "text")
    if out_format == "json":
        console.print_json(data=result)
    else:
        table = Table(title="Namespaces")
        table.add_column("SLUG", style="cyan")
        table.add_column("NAME", style="magenta")
        table.add_column("VISIBILITY", style="green")
        table.add_column("DESCRIPTION")

        for ns in items:
            table.add_row(
                ns.get("slug", ""),
                ns.get("name", ""),
                ns.get("visibility", "PUBLIC"),
                ns.get("description", "") or "",
            )
        console.print(table)


@app.command("create")
def create_cmd(
    ctx: typer.Context,
    slug: str = typer.Argument(..., help="Namespace slug (e.g. team-a)"),
    name: str | None = typer.Option(None, "--name", help="Display name"),
    description: str | None = typer.Option(None, "--description", help="Description"),
    visibility: str = typer.Option(
        "PUBLIC", "--visibility", help="PUBLIC, NAMESPACE_ONLY, or PRIVATE"
    ),
):
    """Create a new namespace."""
    display_name = name or slug
    try:
        with get_client(ctx) as client:
            result = client.create_namespace(
                slug=slug,
                name=display_name,
                description=description,
                visibility=visibility,
            )
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)

    out_format = (ctx.obj or {}).get("format", "text")
    if out_format == "json":
        console.print_json(data=result)
    else:
        console.print(f"[green]Successfully created namespace '{slug}'[/green]")


@app.command("info")
def info_cmd(
    ctx: typer.Context,
    slug: str = typer.Argument(..., help="Namespace slug"),
):
    """Get namespace details."""
    try:
        with get_client(ctx) as client:
            result = client.get_namespace(slug=slug)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)

    out_format = (ctx.obj or {}).get("format", "text")
    if out_format == "json":
        console.print_json(data=result)
    else:
        console.print(f"[bold cyan]Namespace:[/bold cyan] {result.get('slug')}")
        console.print(f"[bold]Name:[/bold] {result.get('name')}")
        console.print(f"[bold]Visibility:[/bold] {result.get('visibility')}")
        console.print(f"[bold]Skill Count:[/bold] {result.get('skill_count', 0)}")
        if result.get("description"):
            console.print(f"[bold]Description:[/bold] {result.get('description')}")
