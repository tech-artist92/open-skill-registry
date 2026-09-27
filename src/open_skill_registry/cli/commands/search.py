import typer
from rich.console import Console
from rich.table import Table
import json
from open_skill_registry.client.main import SkillRegistryClient


console = Console()


def search(
    ctx: typer.Context,
    query: str,
    limit: int = typer.Option(10, "--limit", help="Maximum number of results to return."),
    namespace: str = typer.Option(None, "--namespace", help="Filter by namespace.")
):
    """Search for skills in the registry."""
    registry_url = (ctx.obj or {}).get("registry_url") or "http://localhost:8080"
    transport = (ctx.obj or {}).get("transport")
    
    client_kwargs = {
        "base_url": registry_url,
        "api_key": (ctx.obj or {}).get("api_key"),
    }
    if transport is not None:
        client_kwargs["transport"] = transport

    try:
        with SkillRegistryClient(**client_kwargs) as client:
            results = client.search(query=query, limit=limit, namespace=namespace)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)

    out_format = (ctx.obj or {}).get("format", "text")
    if out_format == "json":
        console.print_json(data=results)
    else:
        table = Table(title="Search Results")
        table.add_column("NAME", style="cyan")
        table.add_column("VERSION", style="magenta")
        table.add_column("NAMESPACE", style="green")
        table.add_column("SIMILARITY", justify="right")
        table.add_column("DESCRIPTION")

        items_list = results.get("items", []) if isinstance(results, dict) else results
        for item in items_list:
            table.add_row(
                item.get("name", item.get("slug", "")),
                item.get("latest_version", "N/A"),
                item.get("namespace", ""),
                f"{item.get('similarity', 0.0):.2f}" if "similarity" in item else "N/A",
                item.get("description", "")
            )
        console.print(table)
