"""Direct Git Import Command for Open Skill Registry (T069)."""

import typer
from rich.console import Console
from rich.table import Table

from open_skill_registry.client.main import SkillRegistryClient
from open_skill_registry.registry.git_import import (
    GitCloneError,
    GitImportError,
    import_from_git,
)

console = Console(soft_wrap=True)
err_console = Console(stderr=True, soft_wrap=True)


def import_command(
    ctx: typer.Context,
    specifier: str = typer.Argument(
        ..., help="Git repository specifier (e.g. github:owner/repo, https://...)"
    ),
    ref: str | None = typer.Option(
        None, "--ref", "-r", help="Git branch, tag, or commit ref to clone."
    ),
    path: str | None = typer.Option(
        None, "--path", "-p", "--subpath", help="Target subdirectory within repository."
    ),
    namespace: str = typer.Option(
        "public", "--namespace", "-n", help="Namespace to publish imported skills to."
    ),
    format: str | None = typer.Option(
        None, "--format", help="Output format (text | json)."
    ),
) -> None:
    """Import skills directly from a remote Git repository into the registry."""
    out_format = format or (ctx.obj or {}).get("format", "text")
    registry_url = (ctx.obj or {}).get("registry_url") or "http://localhost:8080"
    api_key = (ctx.obj or {}).get("api_key")
    transport = (ctx.obj or {}).get("transport")

    client = SkillRegistryClient(
        base_url=registry_url,
        api_key=api_key,
        transport=transport,
    )

    try:
        with client:
            results = import_from_git(
                specifier=specifier,
                ref=ref,
                subpath=path,
                namespace=namespace,
                client=client,
            )
    except ValueError as e:
        err_console.print(f"Invalid git specifier: {e}")
        raise typer.Exit(code=1) from e
    except (GitCloneError, GitImportError, RuntimeError) as e:
        err_console.print(f"Git import failed: {e}")
        raise typer.Exit(code=1) from e
    except Exception as e:
        err_console.print(f"Error during import: {e}")
        raise typer.Exit(code=1) from e

    if not results:
        err_console.print(f"No skills found in repository: {specifier}")
        raise typer.Exit(code=1)

    if out_format == "json":
        json_data = [
            {
                "name": r.name,
                "slug": r.slug,
                "namespace": r.namespace,
                "version": r.version,
                "files_count": r.files_count,
                "content_hash": r.content_hash,
                "success": r.success,
                "status": r.status,
                "error": r.error,
            }
            for r in results
        ]
        console.print_json(data=json_data)
    else:
        table = Table(title="Git Import Summary")
        table.add_column("NAME", style="cyan")
        table.add_column("NAMESPACE", style="green")
        table.add_column("VERSION", style="magenta")
        table.add_column("FILES", justify="right")
        table.add_column("STATUS")

        for r in results:
            status_style = "green" if r.success else "red"
            status_text = f"[{status_style}]{r.status}[/{status_style}]"
            table.add_row(
                r.name or r.slug,
                r.namespace,
                r.version,
                str(r.files_count),
                status_text,
            )
        console.print(table)

    if any(not r.success for r in results):
        raise typer.Exit(code=1)
