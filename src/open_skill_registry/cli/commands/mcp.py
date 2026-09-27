"""CLI command for Model Context Protocol (MCP) server (T072)."""

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from open_skill_registry.client.main import SkillRegistryClient
from open_skill_registry.config import RegistryConfig
from open_skill_registry.registry.main import AsyncSkillRegistry
from open_skill_registry.server.mcp import MCPHandler, run_stdio_server


def mcp_command(
    ctx: typer.Context,
    registry_url: Annotated[
        str | None,
        typer.Option("--registry-url", help="Remote registry URL (defaults to local embedded)."),
    ] = None,
    api_key: Annotated[
        str | None, typer.Option("--api-key", help="API key for remote registry.")
    ] = None,
    config: Annotated[
        Path | None, typer.Option("--config", help="Path to configuration file.")
    ] = None,
) -> None:
    """Start a Model Context Protocol (MCP) server over standard I/O (SEP-2640)."""
    reg_url = registry_url or (ctx.obj or {}).get("registry_url")
    key = api_key or (ctx.obj or {}).get("api_key")
    cfg_path = config or (ctx.obj or {}).get("config")

    async def _runner():
        if reg_url:
            client = SkillRegistryClient(base_url=reg_url, api_key=key)
            handler = MCPHandler(registry=client)
        else:
            cfg = RegistryConfig.load(cfg_path) if cfg_path else RegistryConfig.load()
            registry = AsyncSkillRegistry(config=cfg)
            await registry.initialize()
            handler = MCPHandler(registry=registry, config=cfg)

        await run_stdio_server(handler)

    import contextlib

    with contextlib.suppress(KeyboardInterrupt, SystemExit):
        asyncio.run(_runner())
