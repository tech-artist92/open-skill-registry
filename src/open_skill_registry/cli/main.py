from pathlib import Path

import typer

from open_skill_registry.cli.commands import init, serve

app = typer.Typer(name="osr", help="Open Skill Registry CLI", no_args_is_help=True)

app.add_typer(init.app, name="init", help="Initialize configuration")
app.add_typer(serve.app, name="serve", help="Start the FastAPI server")

def version_callback(value: bool):
    if value:
        try:
            import importlib.metadata
            version = importlib.metadata.version("open-skill-registry")
        except Exception:
            version = "unknown"
        typer.echo(f"Open Skill Registry version: {version}")
        raise typer.Exit()

@app.callback()
def main(
    ctx: typer.Context,
    version: bool | None = typer.Option(
        None, "--version", callback=version_callback, is_eager=True, help="Print version and exit."
    ),
    config: Path | None = typer.Option(None, "--config", help="Path to configuration file."),
    registry_url: str | None = typer.Option(None, "--registry-url", help="Registry URL to use."),
    api_key: str | None = typer.Option(None, "--api-key", help="API key for authentication."),
    format: str = typer.Option("text", "--format", help="Output format (text | json).")
):
    ctx.ensure_object(dict)
    ctx.obj["config"] = config
    ctx.obj["registry_url"] = registry_url
    ctx.obj["api_key"] = api_key
    ctx.obj["format"] = format
