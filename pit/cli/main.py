"""pit CLI main entry point"""

import typer

from pit.cli.features import app as features_app
from pit.cli.git import app as git_app
from pit.cli.health import app as health_app
from pit.cli.projects import app as projects_app

app = typer.Typer(
    name="pit",
    help="Product / Idea Tracker - 기획/아이디어/결정/체크리스트 관제 시스템",
    no_args_is_help=True,
)

app.add_typer(projects_app, name="projects")
app.add_typer(features_app, name="features")
app.add_typer(health_app, name="health")
app.add_typer(git_app, name="git")


# Shortcut: pit feature -> pit features show
@app.command("feature")
def feature_show(
    project_id: str = typer.Argument(..., help="Project ID"),
    feature_id: str = typer.Argument(..., help="Feature ID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show feature details (shortcut for 'features show')"""
    from pit.cli.features import show

    show(project_id, feature_id, json_output)


if __name__ == "__main__":
    app()
