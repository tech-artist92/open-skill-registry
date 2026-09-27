"""Login command for CLI authentication and configuration (T048)."""

from pathlib import Path

import typer
import yaml
from rich.console import Console

console = Console()


def mask_key(key: str) -> str:
    """Mask key preserving prefix and suffix."""
    if len(key) > 12:
        return f"{key[:8]}...{key[-4:]}"
    return "****"


def login(
    ctx: typer.Context,
    registry_url: str | None = typer.Argument(None, help="Registry URL"),
    api_key: str | None = typer.Option(None, "--api-key", help="API key"),
    namespace: str | None = typer.Option(None, "--namespace", help="Default namespace"),
    config: Path | None = typer.Option(None, "--config", help="Configuration file path"),
):
    """Log in to an Open Skill Registry instance and persist credentials."""
    target_config = config or (ctx.obj or {}).get("config")
    if not target_config:
        local_cfg = Path("osr.config.yaml")
        if local_cfg.exists():
            target_config = local_cfg
        else:
            target_config = Path.home() / ".osr" / "config.yaml"
    else:
        target_config = Path(target_config)

    url = registry_url or (ctx.obj or {}).get("registry_url") or "http://localhost:8080"
    key = api_key or (ctx.obj or {}).get("api_key")

    data = {}
    if target_config.exists():
        try:
            with open(target_config, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            data = {}

    if not isinstance(data, dict):
        data = {}

    client_cfg = data.get("client", {})
    if not isinstance(client_cfg, dict):
        client_cfg = {}

    client_cfg["registry_url"] = str(url).rstrip("/")
    if key is not None:
        client_cfg["api_key"] = key
    if namespace is not None:
        client_cfg["default_namespace"] = namespace

    data["client"] = client_cfg

    target_config.parent.mkdir(parents=True, exist_ok=True)
    with open(target_config, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False)

    key_display = mask_key(key) if key else "None"
    ns_display = f", Namespace: {namespace}" if namespace else ""
    console.print(
        f"[green]Successfully logged in to[/green] {url} (API Key: {key_display}{ns_display})"
    )
    console.print(f"[dim]Configuration saved to {target_config}[/dim]")
