"""pit health CLI commands"""

import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pit.core.health_check import HealthStatus, check_feature_health, check_project_health
from pit.loaders import get_feature, list_features, list_projects

app = typer.Typer(help="Health check commands")
console = Console()


def status_icon(status: HealthStatus) -> str:
    """Get icon and color for health status"""
    icons = {
        HealthStatus.GREEN: "[green]●[/green]",
        HealthStatus.YELLOW: "[yellow]●[/yellow]",
        HealthStatus.RED: "[red]●[/red]",
    }
    return icons.get(status, "○")


@app.command("project")
def project_health(
    project_id: str = typer.Argument(..., help="Project ID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Check health of a project"""
    features = list_features(project_id)
    result = check_project_health(features)

    if json_output:
        console.print(json.dumps({
            "project_id": project_id,
            "status": result.status.value,
            "score": result.score,
            "reasons": result.reasons,
        }, indent=2, ensure_ascii=False))
        return

    console.print()
    console.print(Panel(
        f"{status_icon(result.status)} [bold]{project_id}[/bold] - Score: {result.score}/100",
        title="Project Health",
    ))

    for reason in result.reasons:
        console.print(f"  • {reason}")

    # Show feature breakdown
    if features:
        console.print()
        table = Table(title="Features")
        table.add_column("Status", width=3)
        table.add_column("ID", style="cyan")
        table.add_column("Title")
        table.add_column("Score", justify="right")
        table.add_column("Issues")

        for feature in features:
            f_result = check_feature_health(feature)
            issues = ", ".join(f_result.reasons[:2]) if f_result.reasons[0] != "All checks passed" else "-"
            table.add_row(
                status_icon(f_result.status),
                feature.id,
                feature.title[:30],
                str(f_result.score),
                issues[:40],
            )

        console.print(table)
    console.print()


@app.command("feature")
def feature_health(
    project_id: str = typer.Argument(..., help="Project ID"),
    feature_id: str = typer.Argument(..., help="Feature ID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Check health of a specific feature"""
    feature = get_feature(project_id, feature_id)

    if not feature:
        console.print(f"[red]Feature '{feature_id}' not found[/red]")
        raise typer.Exit(1)

    result = check_feature_health(feature)

    if json_output:
        console.print(json.dumps({
            "feature_id": feature_id,
            "title": feature.title,
            "status": result.status.value,
            "score": result.score,
            "reasons": result.reasons,
        }, indent=2, ensure_ascii=False))
        return

    console.print()
    console.print(Panel(
        f"{status_icon(result.status)} [bold]{feature_id}[/bold] - {feature.title}\nScore: {result.score}/100",
        title="Feature Health",
    ))

    console.print("[bold]Details:[/bold]")
    for reason in result.reasons:
        console.print(f"  • {reason}")

    # Show checklist status
    if feature.checklist:
        done, total = feature.progress
        console.print(f"\n[bold]Progress:[/bold] {done}/{total} tasks ({feature.progress_percent}%)")

    console.print()


@app.command("all")
def all_health(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Check health of all projects"""
    projects = list_projects()

    if not projects:
        console.print("[yellow]No projects found[/yellow]")
        raise typer.Exit(0)

    if json_output:
        results = []
        for project in projects:
            features = list_features(project.id)
            result = check_project_health(features)
            results.append({
                "project_id": project.id,
                "status": result.status.value,
                "score": result.score,
                "reasons": result.reasons,
            })
        console.print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    console.print()
    table = Table(title="All Projects Health")
    table.add_column("Status", width=3)
    table.add_column("Project", style="cyan")
    table.add_column("Score", justify="right")
    table.add_column("Summary")

    for project in projects:
        features = list_features(project.id)
        result = check_project_health(features)
        summary = ", ".join(result.reasons[:2])
        table.add_row(
            status_icon(result.status),
            project.id,
            str(result.score),
            summary[:50],
        )

    console.print(table)
    console.print()
