"""pit projects CLI commands"""

import json

import typer
from rich.console import Console
from rich.table import Table

from pit.loaders import list_projects

app = typer.Typer(help="Project management commands")
console = Console()


@app.command("list")
def list_cmd(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all projects"""
    projects = list_projects()

    if not projects:
        console.print("[yellow]No projects found.[/yellow]")
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
