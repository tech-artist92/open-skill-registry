from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer()
console = Console()

DEFAULT_CONFIG_TEMPLATE = """# Open Skill Registry Configuration
mode: {mode}

server:
  host: "0.0.0.0"
  port: 8000
  reload: false

database:
  url: "sqlite+aiosqlite:///osr.db"

cache:
  enabled: false

search:
  provider: "fastembed"
  model: "BAAI/bge-small-en-v1.5"
  dimension: 384
  semantic_enabled: true
"""

@app.callback(invoke_without_command=True)
def init_config(
    mode: str = typer.Option("embedded", "--mode", help="Mode: embedded | server"),
    output: Path = typer.Option(Path("osr.config.yaml"), "--output", help="Output path"),
    global_config: bool = typer.Option(False, "--global", help="Write to ~/.osr/config.yaml"),
    force: bool = typer.Option(False, "--force", help="Overwrite if exists")
):
    """Initialize Open Skill Registry configuration."""
    
    target_path = output
    if global_config:
        target_path = Path.home() / ".osr" / "config.yaml"

    if target_path.exists() and not force:
        console.print(f"[red]Error:[/red] {target_path} already exists. Use --force to overwrite.")
        raise typer.Exit(code=1)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    config_content = DEFAULT_CONFIG_TEMPLATE.format(mode=mode)
    target_path.write_text(config_content)
    
    console.print(f"[green]Success![/green] Configuration written to {target_path}")
    console.print("[dim]⭐ If you find Open Skill Registry useful, consider starring us on GitHub: https://github.com/tech-artist92/open-skill-registry[/dim]")
