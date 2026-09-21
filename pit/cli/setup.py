"""pit setup — 개발자용 로컬 pit 을 처음 준비한다

비개발자에게 로컬 pit은 필요 없다. 커넥터 추가와 GitHub 로그인이면 끝난다.
이 명령은 원문 보존과 감사를 원하는 사람이 한 번 실행한다.
"""

import os
import plistlib
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console

from pit.personal.config import load_config
from pit.personal.home import ensure_home, resolve_pit_home
from pit.personal.remote import PITHUB_URL_ENV
from pit.vault.sources import resolve_source_root
from pit.vault.sync import SyncStatus, sync_all

console = Console()

LAUNCHD_LABEL = "co.pilab.pit.vault-sync"
SYNC_HOUR = 21
MCP_PATH = "/mcp"


def _mcp_url() -> str | None:
    base = os.environ.get(PITHUB_URL_ENV)
    return f"{base.rstrip('/')}{MCP_PATH}" if base else None


def setup_cmd(
    daily: bool = typer.Option(False, "--daily", help=f"매일 {SYNC_HOUR}시에 보관함을 sync하는 launchd 작업을 등록"),
    pit_repo: Path = typer.Option(None, "--repo", help="pit 저장소 경로 (uv tool 설치면 불필요)"),
) -> None:
    """개인 보관함을 만들고 첫 sync를 한 뒤, 도구에 커넥터를 추가하는 명령을 안내한다"""
    home = resolve_pit_home()
    ensure_home(home)
    config = load_config(home)
    console.print(f"보관함: {home}")

    report = sync_all(home, resolve_source_root(), config, config.device, datetime.now(timezone.utc))
    console.print(f"첫 sync: 새 파일 {report.count(SyncStatus.NEW)}개, {report.bytes_added / (1024 * 1024):.1f} MB")

    if daily:
        _install_launchd(pit_repo)

    mcp = _mcp_url()
    console.print("\n[bold]다음 단계[/bold]")
    if mcp:
        console.print(f"  Claude Code: claude mcp add --transport http pithub {mcp}")
        console.print(f"  Codex:       codex mcp add pithub --url {mcp} && codex mcp login pithub")
        console.print(f"  claude.ai:   설정 → 커넥터 → 커스텀 커넥터 추가 → {mcp}")
    else:
        console.print(f"  {PITHUB_URL_ENV} 를 설정하면 커넥터 추가 명령을 여기에 보여 줍니다.")
    console.print("  pithub 설정 화면에서 토큰을 발급한 뒤: pit login")


def _install_launchd(pit_repo: Path | None) -> None:
    """launchd 사용자 에이전트 파일을 쓴다. 로드는 사용자가 한다(설정 파일을 몰래 바꾸지 않는다)."""
    if pit_repo:
        program = ["uv", "run", "--directory", str(pit_repo.resolve()), "pit", "vault", "sync", "--quiet"]
    else:
        program = ["pit", "vault", "sync", "--quiet"]
    plist = {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": program,
        "StartCalendarInterval": {"Hour": SYNC_HOUR, "Minute": 0},
        "EnvironmentVariables": {"PATH": os.environ.get("PATH", "")},
    }
    path = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(plistlib.dumps(plist))
    console.print(f"launchd 파일을 썼습니다: {path}")
    console.print(f"  켜려면: launchctl load {path}")
