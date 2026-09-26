import typer
import uvicorn
from typing import Optional
from pathlib import Path
from rich.console import Console
from open_skill_registry.config import RegistryConfig

app = typer.Typer()
console = Console()

@app.callback(invoke_without_command=True)
def serve(
    config: Optional[Path] = typer.Option(None, "--config", help="Path to config file"),
    host: Optional[str] = typer.Option(None, "--host", help="Bind socket to this host."),
    port: Optional[int] = typer.Option(None, "--port", help="Bind socket to this port."),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload.")
):
    """Start the FastAPI server."""
    # Load config to get default host/port
    try:
        registry_config = RegistryConfig.load(config)
        default_host = registry_config.server.host if registry_config.server else "127.0.0.1"
        default_port = registry_config.server.port if registry_config.server else 8000
    except Exception:
        default_host = "127.0.0.1"
        default_port = 8000

    final_host = host if host is not None else default_host
    final_port = port if port is not None else default_port

    run_kwargs = {
        "factory": True,
        "reload": reload,
        "host": final_host,
        "port": final_port
    }
        
    console.print(f"[green]Starting Open Skill Registry server on {final_host}:{final_port}...[/green]")
    uvicorn.run("open_skill_registry.server.app:create_app", **run_kwargs)
