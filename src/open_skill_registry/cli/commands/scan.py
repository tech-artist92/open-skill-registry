"""Security scanner CLI command (T063)."""

import json
from pathlib import Path

import typer
from rich.console import Console

from open_skill_registry.registry.security.scanner import scan_path

console = Console()


def scan(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="Path to directory, zip file, or skill package to scan"),
):
    """Scan a skill package for security vulnerabilities, secrets, and prompt injections."""
    target_path = Path(path)
    if not target_path.exists():
        console.print(f"[red]Error: Path not found: {path}[/red]")
        raise typer.Exit(code=1)

    try:
        result = scan_path(target_path)
    except Exception as e:
        console.print(f"[red]Scan failed: {e}[/red]")
        raise typer.Exit(code=1) from e

    format_opt = (ctx.obj or {}).get("format", "text") if ctx else "text"
    if format_opt == "json":
        typer.echo(json.dumps(result.to_dict(), indent=2))
        if not result.passed:
            raise typer.Exit(code=1)
        return

    # Print detailed findings
    if result.findings:
        console.print(f"\nFindings ({len(result.findings)}):")
        for finding in result.findings:
            loc = (
                f"{finding.file_path}:{finding.line_number}"
                if finding.line_number
                else finding.file_path
            )
            sev = finding.severity.value
            console.print(f"  [{sev}] {finding.rule_id} at {loc}: {finding.message}")
        console.print("")
    else:
        console.print("[green]No security issues found.[/green]")

    # Print summary
    if result.passed:
        console.print(f"[green][PASS][/green] Safety score: {result.safety_score}")
        console.print(f"Scanned {result.scanned_files_count} file(s).")
    else:
        console.print(f"[red][FAIL][/red] Safety score: {result.safety_score}")
        console.print(f"Scanned {result.scanned_files_count} file(s).")
        raise typer.Exit(code=1)
