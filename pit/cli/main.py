"""pit CLI main entry point"""

import typer

from pit.cli.features import app as features_app
from pit.cli.git import app as git_app
from pit.cli.health import app as health_app
from pit.cli.projects import app as projects_app
from pit.cli.transcripts import app as transcripts_app
from pit.cli.vault import app as vault_app

app = typer.Typer(
    name="pit",
    help="Product / Idea Tracker - 기획/아이디어/결정/체크리스트 관제 시스템",
    no_args_is_help=True,
)

app.add_typer(projects_app, name="projects")
app.add_typer(features_app, name="features")
app.add_typer(health_app, name="health")
app.add_typer(git_app, name="git")
app.add_typer(vault_app, name="vault")
app.add_typer(transcripts_app, name="transcripts")


# Shortcut: pit feature -> pit features show
@app.command("feature")
def feature_show(
    feature_id: str = typer.Argument(..., help="Feature ID"),
    project_id: str = typer.Option(None, "--project", "-p", help="Project ID (선택)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show feature details (shortcut for 'features show')"""
    from pit.cli.features import show

    show(feature_id, project_id, json_output)


@app.command("chat")
def chat():
    """Start interactive chat with pit AI assistant"""
    from pit.cli.chat import chat_main

    chat_main()


@app.command("init")
def init(
    name: str = typer.Option(None, "--name", "-n", help="프로젝트 이름"),
    description: str = typer.Option(None, "--description", "-d", help="프로젝트 설명"),
    owner: str = typer.Option(None, "--owner", "-o", help="프로젝트 소유자"),
):
    """현재 디렉토리에 pit 프로젝트를 초기화합니다."""
    from pit.cli.init import init_project

    init_project(name, description, owner)


if __name__ == "__main__":
    app()
