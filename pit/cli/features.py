"""pit features CLI commands"""

import json
from datetime import datetime

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from pit.core.context import get_project_id
from pit.loaders import get_feature, get_next_feature_id, list_features, save_feature
from pit.models.feature import Checklist, Feature

app = typer.Typer(help="Feature management commands")
console = Console()


def get_current_project_id(project_id: str | None = None) -> str:
    """Get project ID from argument or context"""
    if project_id:
        return project_id

    ctx_project = get_project_id()
    if ctx_project:
        return ctx_project

    console.print("[red]프로젝트를 찾을 수 없습니다. 'pit init'으로 초기화하거나 --project 옵션을 사용하세요.[/red]")
    raise typer.Exit(1)


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
    project_id: str = typer.Argument(None, help="Project ID (선택, 없으면 현재 .pit 프로젝트)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all features for a project"""
    # .pit/ 폴더 기반이면 project_id 없이도 동작
    if project_id:
        features = list_features(project_id)
        proj_name = project_id
    else:
        features = list_features()  # 현재 .pit/ 프로젝트
        proj_name = get_project_id() or "current"

    if not features:
        console.print(f"[yellow]No features found for project '{proj_name}'.[/yellow]")
        raise typer.Exit(0)

    if json_output:
        data = [f.model_dump(mode="json", exclude_none=True) for f in features]
        console.print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    table = Table(title=f"Features - {proj_name}")
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
    feature_id: str = typer.Argument(..., help="Feature ID"),
    project_id: str = typer.Option(None, "--project", "-p", help="Project ID (선택)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show feature details"""
    if project_id:
        feature = get_feature(project_id, feature_id)
    else:
        feature = get_feature(feature_id=feature_id)

    if not feature:
        console.print(f"[red]Feature '{feature_id}' not found.[/red]")
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
    title: str = typer.Argument(None, help="Feature title"),
    project_id: str = typer.Option(None, "--project", "-p", help="Project ID (선택)"),
    priority: str = typer.Option("medium", "--priority", help="Priority (low/medium/high/critical)"),
    interactive: bool = typer.Option(True, "--interactive/--no-interactive", "-i", help="Interactive mode"),
):
    """Create a new feature"""
    # 프로젝트 ID 결정
    proj_id = get_current_project_id(project_id)

    if interactive and not title:
        title = typer.prompt("Feature title")

    if not title:
        console.print("[red]Title is required[/red]")
        raise typer.Exit(1)

    feature_id = get_next_feature_id() if not project_id else get_next_feature_id(project_id)

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
        project_id=proj_id,
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
