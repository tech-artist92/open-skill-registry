from pathlib import Path

import typer

from open_skill_registry.cli.commands import (
    info,
    init,
    install,
    list_cmd,
    login,
    namespace,
    pull,
    push,
    scan,
    search,
    serve,
    tag,
    update,
    verify,
    yank,
)

app = typer.Typer(name="osr", help="Open Skill Registry CLI", no_args_is_help=True)

app.add_typer(init.app, name="init", help="Initialize configuration")
app.add_typer(serve.app, name="serve", help="Start the FastAPI server")
app.add_typer(namespace.app, name="namespace", help="Manage namespaces")

# Add the functions directly as commands
app.command(name="push", help="Push a skill to the registry")(push.push_command)
app.command(name="login", help="Log in to an Open Skill Registry instance")(login.login)
app.command(name="search", help="Search for skills in the registry")(search.search)
app.command(name="info", help="Get detailed information about a skill")(info.info)
app.command(name="pull", help="Pull a skill from the registry to local disk")(pull.pull)
app.command(name="verify", help="Verify cryptographic hashes of a local skill package")(
    verify.verify
)
app.command(name="tag", help="Assign a release tag to a skill version")(tag.tag)
app.command(name="yank", help="Yank a faulty skill version")(yank.yank)
app.command(name="scan", help="Scan a skill package for security vulnerabilities and secrets")(
    scan.scan
)
app.command(name="install", help="Install a skill into workspace or local agent environment")(
    install.install
)
app.command(name="update", help="Update installed skills to their latest versions")(update.update)
app.command(name="list", help="List skills in the remote registry or locally installed skills")(
    list_cmd.list_command
)


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
    format: str = typer.Option("text", "--format", help="Output format (text | json)."),
):
    ctx.ensure_object(dict)
    ctx.obj["config"] = config
    ctx.obj["registry_url"] = registry_url
    ctx.obj["api_key"] = api_key
    ctx.obj["format"] = format

    # Auto-load client config from file if not explicitly passed
    cfg_to_load = config
    if not cfg_to_load:
        for p in [
            Path("osr.config.yaml"),
            Path(".osr/config.yaml"),
            Path.home() / ".osr" / "config.yaml",
        ]:
            if p.exists() and p.is_file():
                cfg_to_load = p
                break
    if cfg_to_load and cfg_to_load.exists():
        try:
            import yaml

            with open(cfg_to_load, encoding="utf-8") as f:
                d = yaml.safe_load(f) or {}
                if isinstance(d, dict) and "client" in d and isinstance(d["client"], dict):
                    c = d["client"]
                    if not ctx.obj.get("registry_url") and c.get("registry_url"):
                        ctx.obj["registry_url"] = c["registry_url"]
                    if not ctx.obj.get("api_key") and c.get("api_key"):
                        ctx.obj["api_key"] = c["api_key"]
                    if not ctx.obj.get("default_namespace") and c.get("default_namespace"):
                        ctx.obj["default_namespace"] = c["default_namespace"]
        except Exception:
            pass


if __name__ == "__main__":
    app()
