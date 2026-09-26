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
    # We would normally use the config file here, but for CLI we just pass standard uvicorn args.
    # RegistryConfig will be loaded inside create_app
    
    # We let uvicorn handle host/port, falling back to defaults if not provided
    run_kwargs = {
        "factory": True,
        "reload": reload
    }
    if host is not None:
        run_kwargs["host"] = host
    if port is not None:
        run_kwargs["port"] = port
        
    console.print("[green]Starting Open Skill Registry server...[/green]")
    uvicorn.run("open_skill_registry.server.app:create_app", **run_kwargs)
