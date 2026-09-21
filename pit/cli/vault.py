"""pit vault CLI — 세션 원문을 개인 보관함에 보존"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from pit.personal.config import ConfigError, load_config
from pit.personal.home import PersonalHomeError, ensure_home, resolve_pit_home
from pit.vault.manifest import load_manifest
from pit.vault.policy import end_pause, load_pauses, start_pause
from pit.vault.snapshot import snapshot_control_inputs
from pit.vault.sources import resolve_claude_home, resolve_source_root
from pit.vault.sync import SyncReport, SyncStatus, sync_all

app = typer.Typer(help="세션 원문 보관함 (개인 소유, 로컬)")
console = Console()

BYTES_PER_MB = 1024 * 1024


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _run_sync(home: Path, source_root: Path, device: str | None) -> SyncReport:
    try:
        config = load_config(home)
        return sync_all(home, source_root, config, device or config.device, _now())
    except (ConfigError, PersonalHomeError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e


def _print_report(report: SyncReport) -> None:
    table = Table(title="vault sync")
    table.add_column("상태")
    table.add_column("파일 수", justify="right")
    for status in SyncStatus:
        if report.count(status):
            table.add_row(status.value, str(report.count(status)))
    console.print(table)
    console.print(f"추가된 용량: {report.bytes_added / BYTES_PER_MB:.1f} MB")


@app.command("sync")
def sync_cmd(
    quiet: bool = typer.Option(False, "--quiet", "-q", help="결과를 출력하지 않음 (훅용)"),
) -> None:
    """Claude Code 세션을 보관함에 반영하고 통제군 입력을 스냅샷한다"""
    home = resolve_pit_home()
    report = _run_sync(home, resolve_source_root(), device=None)

    config = load_config(home)
    snapshot_control_inputs(resolve_claude_home(), home, config.control_input_globs, _now())

    if not quiet:
        _print_report(report)
    if report.count(SyncStatus.FAILED):
        raise typer.Exit(1)


@app.command("import")
def import_cmd(
    source_dir: Path = typer.Argument(..., help="다른 기기에서 가져온 projects 폴더"),
    device: str = typer.Option(..., "--device", "-d", help="그 기기의 이름"),
) -> None:
    """다른 기기의 세션 폴더를 이 보관함에 합친다"""
    if not source_dir.is_dir():
        console.print(f"[red]폴더가 없습니다: {source_dir}[/red]")
        raise typer.Exit(1)
    _print_report(_run_sync(resolve_pit_home(), source_dir, device=device))


@app.command("status")
def status_cmd(
    as_json: bool = typer.Option(False, "--json", help="JSON으로 출력"),
) -> None:
    """보관함 현황 (내용은 출력하지 않는다)"""
    home = resolve_pit_home()
    entries = list(load_manifest(home).values())
    paused = any(pause.end is None for pause in load_pauses(home)) if home.exists() else False
    summary = {
        "home": str(home),
        "files": len(entries),
        "main_sessions": sum(1 for entry in entries if entry.agent_name is None),
        "vault_bytes": sum(entry.vault_bytes for entry in entries),
        "devices": sorted({entry.device for entry in entries}),
        "last_synced_at": max((entry.synced_at for entry in entries), default=None),
        "paused": paused,
    }

    if as_json:
        console.print_json(json.dumps(summary, default=str, ensure_ascii=False))
        return

    console.print(f"보관함: {summary['home']}")
    console.print(f"파일 {summary['files']}개 (메인 세션 {summary['main_sessions']}개)")
    console.print(f"용량 {summary['vault_bytes'] / BYTES_PER_MB:.1f} MB")
    console.print(f"기기: {', '.join(summary['devices']) or '-'}")
    last = summary["last_synced_at"]
    console.print(f"마지막 sync: {last.astimezone():%Y-%m-%d %H:%M} (현지 시각)" if last else "마지막 sync: -")
    console.print("[yellow]기록 일시정지 중[/yellow]" if paused else "기록 중")


@app.command("pause")
def pause_cmd() -> None:
    """지금부터의 기록을 보관함에 넣지 않는다"""
    home = resolve_pit_home()
    ensure_home(home)
    if start_pause(home, _now()):
        console.print("기록을 일시정지했습니다. 'pit vault resume'으로 다시 시작합니다.")
    else:
        console.print("[yellow]이미 일시정지 중입니다.[/yellow]")


@app.command("resume")
def resume_cmd() -> None:
    """일시정지를 끝낸다 (정지 구간의 기록은 계속 제외된다)"""
    home = resolve_pit_home()
    if home.exists() and end_pause(home, _now()):
        console.print("기록을 다시 시작했습니다.")
    else:
        console.print("[yellow]일시정지 중이 아닙니다.[/yellow]")


@app.command("hook-snippet")
def hook_snippet_cmd(
    pit_repo: Optional[Path] = typer.Option(None, "--repo", help="pit 저장소 경로"),
) -> None:
    """세션 종료 시 자동 sync하는 Claude Code 훅 설정 조각을 출력한다

    설정 파일을 직접 고치지는 않는다. 출력을 ~/.claude/settings.json 에 합치면 된다.
    """
    repo = (pit_repo or Path(__file__).resolve().parents[2]).resolve()
    command = f"uv run --directory {repo} pit vault sync --quiet"
    snippet = {"hooks": {"SessionEnd": [{"hooks": [{"type": "command", "command": command}]}]}}
    console.print_json(json.dumps(snippet))
