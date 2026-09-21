"""pit transcripts CLI — 보관된 세션을 대화 이벤트로 읽기"""

from collections import Counter

import typer
from rich.console import Console
from rich.table import Table

from pit.personal.config import ConfigError, load_config
from pit.personal.home import resolve_pit_home
from pit.transcripts.records import EventKind
from pit.transcripts.view import render_event
from pit.transcripts.view_cache import load_view_events, refresh_all_views
from pit.vault.manifest import load_manifest

app = typer.Typer(help="보관된 세션의 대화 이벤트")
console = Console()

DEFAULT_CONTEXT_EVENTS = 3
SESSION_ID_DISPLAY_CHARS = 8


@app.command("stats")
def stats_cmd() -> None:
    """세션별 이벤트 수와 가린 항목 수 (대화 내용은 출력하지 않는다)"""
    home = resolve_pit_home()
    try:
        config = load_config(home)
    except ConfigError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e

    metas = refresh_all_views(home, config)
    entries = {entry.session_id: entry for entry in load_manifest(home).values() if not entry.agent_name}

    table = Table(title="transcripts")
    for column in ("세션", "H", "A", "Q", "D", "I", "가림", "깨진 줄", "비고"):
        table.add_column(column, justify="right" if column != "비고" else "left")

    totals: Counter[str] = Counter()
    for meta in sorted(metas, key=lambda m: -m.events):
        kinds = Counter(e.kind.value for e in load_view_events(home, entries[meta.session_id]))
        totals.update(kinds)
        table.add_row(
            meta.session_id[:SESSION_ID_DISPLAY_CHARS],
            *(str(kinds[kind.value]) for kind in EventKind),
            str(sum(meta.redactions.values())),
            str(meta.malformed_lines),
            "restricted" if meta.restricted else "",
        )
    console.print(table)
    summary = ", ".join(f"{kind.value}={totals[kind.value]}" for kind in EventKind)
    console.print(f"세션 {len(metas)}개 · {summary}")


@app.command("show")
def show_cmd(
    session_id: str = typer.Argument(..., help="세션 ID (앞부분만 써도 된다)"),
    at: str = typer.Option(..., "--at", help="보고 싶은 이벤트의 uuid"),
    context: int = typer.Option(DEFAULT_CONTEXT_EVENTS, "--context", "-c", help="앞뒤로 보여 줄 이벤트 수"),
) -> None:
    """결정의 출처로 되돌아가 앞뒤 대화를 본다"""
    home = resolve_pit_home()
    matches = [
        entry
        for entry in load_manifest(home).values()
        if not entry.agent_name and entry.session_id.startswith(session_id)
    ]
    if len(matches) != 1:
        console.print(f"[red]세션을 하나로 특정할 수 없습니다 (일치 {len(matches)}개)[/red]")
        raise typer.Exit(1)

    events = load_view_events(home, matches[0])
    position = next((i for i, event in enumerate(events) if event.uuid == at), None)
    if position is None:
        console.print("[red]그 uuid의 이벤트가 없습니다. 'pit transcripts stats'로 캐시를 갱신해 보세요.[/red]")
        raise typer.Exit(1)

    for index in range(max(0, position - context), min(len(events), position + context + 1)):
        event = events[index]
        marker = "→" if index == position else " "
        console.print(f"{marker} [bold]{event.kind.value}[/bold] {event.timestamp or ''}")
        console.print(render_event(event), markup=False)
        console.print()
