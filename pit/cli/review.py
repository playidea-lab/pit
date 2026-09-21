"""pit review CLI — 하루 한 번, 결정 후보를 확정·고치기·버리기"""

import time
from datetime import datetime, timezone

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pit.decisions.models import Decision, DecisionKind, Verdict
from pit.decisions.query import review_stats, sample_for_gate1
from pit.decisions.review import (
    EDITABLE_FIELDS,
    REVIEW_DAILY_LIMIT,
    ReviewCommand,
    ReviewInput,
    run_review_session,
)
from pit.decisions.store import load_candidates, load_review_events
from pit.personal.config import ConfigError, load_config
from pit.personal.home import resolve_pit_home
from pit.transcripts.view import render_event
from pit.transcripts.view_cache import load_view_events
from pit.vault.manifest import load_manifest
from pit.vault.sources import resolve_source_root
from pit.vault.sync import sync_all

app = typer.Typer(help="결정 후보 검토", invoke_without_command=True)
console = Console()

GATE1_SAMPLE = "gate1"
SOURCE_CONTEXT_EVENTS = 3
VERDICT_KEYS = {"1": Verdict.APPROVE, "2": Verdict.MODIFY, "3": Verdict.REJECT}
KEY_HELP = "[c] 확정  [1] 승인 [2] 수정 [3] 거부 로 고쳐 확정  [e] 편집  [d] 버림  [o] 원문  [s] 건너뜀  [q] 종료"


def _show(candidate: Decision, position: int, total: int) -> None:
    if candidate.kind is DecisionKind.CHOICE:
        outcome = f"선택지: {' | '.join(candidate.options)}\n[bold]고른 답: {candidate.chosen}[/bold]"
    else:
        verdict = candidate.verdict.value if candidate.verdict else "-"
        outcome = f"[bold]판정: {verdict}[/bold]" + (f" ({candidate.reject_kind.value})" if candidate.reject_kind else "")
    body = (
        f"[dim]상황[/dim]  {candidate.situation}\n\n[dim]제안[/dim]  {candidate.proposal}\n\n{outcome}\n\n"
        f"[dim]내 말[/dim]  {candidate.human_quote or '-'}"
    )
    title = f"{position}/{total} · {candidate.decided_at.astimezone():%m-%d %H:%M} · {candidate.project or '-'}"
    console.print(Panel(body, title=title, subtitle=candidate.extractor.method.value))


def _show_source(candidate: Decision) -> None:
    home = resolve_pit_home()
    key = f"{candidate.source.device}/{candidate.source.session_id}"
    entry = load_manifest(home).get(key)
    events = load_view_events(home, entry) if entry else []
    at = next((i for i, e in enumerate(events) if e.uuid == candidate.source.verdict_uuid), None)
    if at is None:
        console.print("[yellow]원문 위치를 찾지 못했습니다.[/yellow]")
        return
    for event in events[max(0, at - SOURCE_CONTEXT_EVENTS) : at + 1]:
        console.print(f"[bold]{event.kind.value}[/bold]", render_event(event), markup=False)


def _edit(candidate: Decision) -> ReviewInput:
    editable = candidate.model_dump(mode="json", include=set(EDITABLE_FIELDS))
    dumped = yaml.dump(editable, allow_unicode=True, sort_keys=False)
    edited = typer.edit(dumped, extension=".yaml")
    if edited is None:
        return ReviewInput(ReviewCommand.SKIP)
    return ReviewInput(ReviewCommand.EDIT, edits=yaml.safe_load(edited) or {})


def _ask(candidate: Decision, position: int, total: int) -> ReviewInput:
    _show(candidate, position, total)
    while True:
        key = typer.prompt(KEY_HELP, default="c", show_default=False).strip().lower()
        if key == "c":
            return ReviewInput(ReviewCommand.CONFIRM)
        if key in VERDICT_KEYS and candidate.kind is DecisionKind.VERDICT:
            return ReviewInput(ReviewCommand.EDIT, edits={"verdict": VERDICT_KEYS[key]})
        if key == "e":
            return _edit(candidate)
        if key == "d":
            return ReviewInput(ReviewCommand.DISCARD)
        if key == "s":
            return ReviewInput(ReviewCommand.SKIP)
        if key == "q":
            return ReviewInput(ReviewCommand.QUIT)
        if key == "o":
            _show_source(candidate)


@app.callback()
def review_cmd(
    ctx: typer.Context,
    limit: int = typer.Option(REVIEW_DAILY_LIMIT, "--limit", "-n", help="이번에 볼 후보 수"),
    sample: str = typer.Option(None, "--sample", help=f"'{GATE1_SAMPLE}': 추출 품질 판정용 표본을 검토"),
    no_sync: bool = typer.Option(False, "--no-sync", help="시작할 때 보관함 sync를 건너뜀"),
) -> None:
    """후보를 하나씩 보며 확정·고치기·버리기"""
    if ctx.invoked_subcommand is not None:
        return
    home = resolve_pit_home()
    now = datetime.now(timezone.utc)
    try:
        config = load_config(home)
    except ConfigError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e
    if not no_sync:
        # 기록에 드는 노력을 0으로: 검토하러 올 때마다 보관함이 최신이 된다
        sync_all(home, resolve_source_root(), config, config.device, now)

    candidates = load_candidates(home)
    if sample == GATE1_SAMPLE:
        candidates = sample_for_gate1(candidates)
        limit = len(candidates)
    if not candidates:
        console.print("검토할 후보가 없습니다. 'pit extract'로 후보를 만들 수 있습니다.")
        return

    total = min(limit, len(candidates))
    position = iter(range(1, total + 1))
    summary = run_review_session(
        home, candidates, lambda c: _ask(c, next(position), total), time.monotonic, now, limit
    )
    console.print(f"{summary.message.removeprefix('review: ')}, 건너뜀 {summary.skipped}")
    if not summary.committed and (summary.confirmed or summary.edited or summary.discarded):
        console.print("[yellow]결과는 저장됐지만 git commit은 하지 못했습니다.[/yellow]")


@app.command("stats")
def stats_cmd() -> None:
    """검토 이력으로 본 추출 품질 (게이트 1)"""
    stats = review_stats(load_review_events(resolve_pit_home()))
    if stats is None:
        console.print("검토 이력이 없습니다.")
        return
    values = {
        "usable_rate": f"{stats.usable_rate:.1%}",
        "usable_wilson_lower": f"{stats.usable_wilson_lower:.1%}",
        "verdict_flip_rate": f"{stats.verdict_flip_rate:.1%}",
        "median_seconds": f"{stats.median_seconds:.1f}s",
        "p90_seconds": f"{stats.p90_seconds:.1f}s",
    }
    table = Table(title=f"review stats (검토 {stats.reviewed}건)")
    for column in ("항목", "값", "게이트 1"):
        table.add_column(column)
    for name, passed in stats.gate1_checks.items():
        table.add_row(name, values[name], "[green]통과[/green]" if passed else "[red]미달[/red]")
    console.print(table)
