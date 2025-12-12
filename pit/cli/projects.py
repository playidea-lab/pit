"""pit projects CLI commands"""

import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pit.core.context import find_pit_root, get_project_context
from pit.loaders import list_projects

app = typer.Typer(help="Project management commands")
console = Console()


@app.command("list")
def list_cmd(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all projects (현재 .pit/ 프로젝트)"""
    projects = list_projects()

    if not projects:
        console.print("[yellow]No projects found. Use 'pit init' to initialize.[/yellow]")
        raise typer.Exit(0)

    if json_output:
        data = [p.model_dump(mode="json", exclude_none=True) for p in projects]
        console.print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    table = Table(title="Projects")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Status", style="green")
    table.add_column("Owner", style="yellow")

    for project in projects:
        table.add_row(
            project.id,
            project.name,
            project.status,
            project.owner or "-",
        )

    console.print(table)


@app.command("info")
def info(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """현재 프로젝트 정보 표시"""
    pit_root = find_pit_root()
    if not pit_root:
        console.print("[red]pit 프로젝트를 찾을 수 없습니다. 'pit init'으로 초기화하세요.[/red]")
        raise typer.Exit(1)

    context = get_project_context()
    if not context:
        console.print("[red]프로젝트 설정을 읽을 수 없습니다.[/red]")
        raise typer.Exit(1)

    if json_output:
        console.print(json.dumps(context, indent=2, ensure_ascii=False, default=str))
        return

    console.print(Panel(
        f"[bold cyan]{context.get('id', 'unknown')}[/bold cyan] - {context.get('name', 'Unnamed')}\n\n"
        f"[bold]Description:[/bold] {context.get('description', '-')}\n"
        f"[bold]Status:[/bold] {context.get('status', '-')}\n"
        f"[bold]Owner:[/bold] {context.get('owner', '-')}\n"
        f"[bold]Location:[/bold] {pit_root.parent}",
        title="Current Project",
        border_style="cyan",
    ))
