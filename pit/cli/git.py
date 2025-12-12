"""pit git CLI commands"""

import typer
from rich.console import Console

from pit.core.git_integration import (
    create_feature_branch,
    get_current_branch,
    get_last_commit_info,
    list_branches_for_feature,
    load_pit_config,
)
from pit.loaders import get_feature

app = typer.Typer(help="Git integration commands")
console = Console()


@app.command("checkout")
def checkout(
    feature_id: str = typer.Argument(..., help="Feature ID (e.g., F-0001)"),
):
    """Create and checkout a branch for a feature"""
    config = load_pit_config()
    if not config:
        console.print("[red].pit.yml not found in current or parent directories[/red]")
        raise typer.Exit(1)

    feature = get_feature(config.project_id, feature_id)
    if not feature:
        console.print(f"[red]Feature '{feature_id}' not found in project '{config.project_id}'[/red]")
        raise typer.Exit(1)

    slug = feature.title.lower().replace(" ", "-")[:20]
    slug = "".join(c for c in slug if c.isalnum() or c == "-")

    success, message = create_feature_branch(feature_id, slug)

    if success:
        console.print(f"[green]Created and switched to branch:[/green] {message}")
    else:
        console.print(f"[yellow]{message}[/yellow]")


@app.command("status")
def status(
    feature_id: str = typer.Argument(None, help="Feature ID (optional)"),
):
    """Show git status for current context or feature"""
    config = load_pit_config()

    current = get_current_branch()
    console.print(f"[bold]Current branch:[/bold] {current or 'not in git repo'}")

    if config:
        console.print(f"[bold]Project:[/bold] {config.project_id}")

    commit = get_last_commit_info()
    if commit:
        console.print(f"[bold]Last commit:[/bold] {commit['hash']} - {commit['message']}")

    if feature_id:
        branches = list_branches_for_feature(feature_id)
        if branches:
            console.print(f"\n[bold]Branches for {feature_id}:[/bold]")
            for b in branches:
                marker = " *" if b == current else ""
                console.print(f"  • {b}{marker}")


@app.command("branches")
def branches(
    feature_id: str = typer.Argument(..., help="Feature ID"),
):
    """List all branches for a feature"""
    found = list_branches_for_feature(feature_id)

    if not found:
        console.print(f"[yellow]No branches found for {feature_id}[/yellow]")
        return

    console.print(f"[bold]Branches for {feature_id}:[/bold]")
    for b in found:
        console.print(f"  • {b}")
