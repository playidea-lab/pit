"""pit features CLI commands"""

import json
from datetime import datetime

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from pit.loaders import get_feature, get_next_feature_id, list_features, save_feature
from pit.models.feature import Checklist, Feature

app = typer.Typer(help="Feature management commands")
console = Console()


def status_color(status: str) -> str:
    """Get color for status"""
    colors = {
        "planned": "blue",
        "in_progress": "yellow",
        "ready_for_merge": "cyan",
        "merged": "green",
        "released": "bright_green",
    }
    return colors.get(status, "white")


def priority_color(priority: str) -> str:
    """Get color for priority"""
    colors = {
        "low": "dim",
        "medium": "white",
        "high": "yellow",
        "critical": "red",
    }
    return colors.get(priority, "white")


@app.command("list")
def list_cmd(
    project_id: str = typer.Argument(..., help="Project ID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all features for a project"""
    features = list_features(project_id)

    if not features:
        console.print(f"[yellow]No features found for project '{project_id}'.[/yellow]")
        raise typer.Exit(0)

    if json_output:
        data = [f.model_dump(mode="json", exclude_none=True) for f in features]
        console.print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    table = Table(title=f"Features - {project_id}")
    table.add_column("ID", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Status")
    table.add_column("Priority")
    table.add_column("Progress", justify="right")

    for feature in features:
        done, total = feature.progress
        progress_str = f"{done}/{total}" if total > 0 else "-"

        table.add_row(
            feature.id,
            feature.title[:40] + "..." if len(feature.title) > 40 else feature.title,
            Text(feature.status, style=status_color(feature.status)),
            Text(feature.priority, style=priority_color(feature.priority)),
            progress_str,
        )

    console.print(table)


@app.command("show")
def show(
    project_id: str = typer.Argument(..., help="Project ID"),
    feature_id: str = typer.Argument(..., help="Feature ID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show feature details"""
    feature = get_feature(project_id, feature_id)

    if not feature:
        console.print(f"[red]Feature '{feature_id}' not found in project '{project_id}'.[/red]")
        raise typer.Exit(1)

    if json_output:
        console.print(json.dumps(feature.model_dump(mode="json", exclude_none=True), indent=2, ensure_ascii=False))
        return

    # Header
    status_text = Text(feature.status, style=status_color(feature.status))
    priority_text = Text(feature.priority, style=priority_color(feature.priority))

    console.print()
    console.print(Panel(
        f"[bold cyan]{feature.id}[/bold cyan] - [bold]{feature.title}[/bold]",
        subtitle=f"Status: {status_text} | Priority: {priority_text}",
    ))

    # Description
    if feature.description:
        console.print()
        console.print("[bold]Description:[/bold]")
        console.print(f"  {feature.description.strip()}")

    # Context
    if feature.context:
        console.print()
        console.print("[bold]Context:[/bold]")
        console.print(f"  {feature.context.strip()}")

    # Requirements
    if feature.requirements:
        console.print()
        console.print("[bold]Requirements:[/bold]")
        for req in feature.requirements:
            console.print(f"  • {req}")

    # Acceptance Criteria
    if feature.acceptance_criteria:
        console.print()
        console.print("[bold]Acceptance Criteria:[/bold]")
        for ac in feature.acceptance_criteria:
            console.print(f"  • {ac}")

    # Checklist
    if feature.checklist:
        console.print()
        done, total = feature.progress
        console.print(f"[bold]Checklist:[/bold] ({done}/{total} done)")

        for task in feature.checklist:
            check = "✓" if task.done else "○"
            style = "green" if task.done else "white"
            console.print(f"  [{style}]{check}[/{style}] [{task.type}] {task.label}")

    # Related
    if feature.decisions or feature.logs:
        console.print()
        console.print("[bold]Related:[/bold]")
        if feature.decisions:
            console.print(f"  Decisions: {', '.join(feature.decisions)}")
        if feature.logs:
            console.print(f"  Logs: {', '.join(feature.logs)}")

    console.print()


@app.command("create")
def create(
    project_id: str = typer.Argument(..., help="Project ID"),
    title: str = typer.Option(None, "--title", "-t", help="Feature title"),
    priority: str = typer.Option("medium", "--priority", "-p", help="Priority (low/medium/high/critical)"),
    interactive: bool = typer.Option(True, "--interactive/--no-interactive", "-i", help="Interactive mode"),
):
    """Create a new feature"""
    if interactive and not title:
        title = typer.prompt("Feature title")

    if not title:
        console.print("[red]Title is required[/red]")
        raise typer.Exit(1)

    feature_id = get_next_feature_id(project_id)

    # Interactive task input
    checklist = []
    if interactive:
        console.print("\n[bold]Add tasks (empty line to finish):[/bold]")
        task_num = 1
        while True:
            task_label = typer.prompt(f"  T{task_num}", default="")
            if not task_label:
                break
            checklist.append(Checklist(id=f"T{task_num}", label=task_label, type="code", done=False))
            task_num += 1

    feature = Feature(
        id=feature_id,
        project_id=project_id,
        title=title,
        status="planned",
        priority=priority,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        checklist=checklist,
    )

    filepath = save_feature(feature)
    console.print(f"\n[green]Created:[/green] {feature_id} - {title}")
    console.print(f"[dim]File: {filepath}[/dim]")
