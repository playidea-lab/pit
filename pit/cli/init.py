"""pit init - 프로젝트 초기화 명령어"""

from datetime import datetime
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.panel import Panel

from pit.core.context import find_pit_root

console = Console()


def init_project(
    name: str = typer.Option(None, "--name", "-n", help="프로젝트 이름"),
    description: str = typer.Option(None, "--description", "-d", help="프로젝트 설명"),
    owner: str = typer.Option(None, "--owner", "-o", help="프로젝트 소유자"),
):
    """현재 디렉토리에 pit 프로젝트를 초기화합니다.

    .pit/ 폴더를 생성하고 config.yaml을 설정합니다.
    """
    cwd = Path.cwd()

    # 이미 pit 프로젝트인지 확인
    existing = find_pit_root(cwd)
    if existing:
        console.print(f"[yellow]이미 pit 프로젝트입니다: {existing.parent}[/yellow]")
        return

    # 프로젝트 ID는 폴더 이름 기반
    project_id = cwd.name

    # 기본값 설정
    if not name:
        name = project_id

    # .pit/ 폴더 생성
    pit_dir = cwd / ".pit"
    pit_dir.mkdir(exist_ok=True)

    # 하위 폴더 생성
    (pit_dir / "features").mkdir(exist_ok=True)
    (pit_dir / "decisions").mkdir(exist_ok=True)
    (pit_dir / "logs").mkdir(exist_ok=True)

    # config.yaml 생성
    config = {
        "id": project_id,
        "name": name,
        "description": description or "",
        "status": "active",
        "owner": owner or "",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }

    config_path = pit_dir / "config.yaml"
    config_path.write_text(yaml.dump(config, allow_unicode=True, sort_keys=False))

    # 결과 출력
    console.print(
        Panel(
            f"[green]✓[/green] pit 프로젝트가 초기화되었습니다!\n\n"
            f"  [bold]ID:[/bold] {project_id}\n"
            f"  [bold]Name:[/bold] {name}\n"
            f"  [bold]Location:[/bold] {pit_dir}\n\n"
            f"다음 명령어로 시작하세요:\n"
            f"  [cyan]pit features create \"첫 번째 기능\"[/cyan]",
            title="🚀 pit init",
            border_style="green",
        )
    )
