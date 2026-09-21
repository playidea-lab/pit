"""pit decisions CLI — 확정된 개인 결정 조회"""

from datetime import datetime

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pit.decisions.models import Decision, DecisionKind, Verdict
from pit.decisions.query import DecisionQuery, filter_decisions
from pit.decisions.store import DECISIONS_DIR, load_decisions, save_decision_record, superseded_by
from pit.personal.gitrepo import commit_paths
from pit.personal.home import resolve_pit_home

app = typer.Typer(help="확정된 개인 결정 (프로젝트를 가로질러 사람 축으로)")
console = Console()

SUMMARY_CHARS = 60


def _outcome(decision: Decision) -> str:
    if decision.kind is DecisionKind.CHOICE:
        return f"→ {decision.chosen}"
    return decision.verdict.value if decision.verdict else "-"


def _print_table(decisions: list[Decision]) -> None:
    replaced = superseded_by(decisions)
    table = Table(title=f"결정 {len(decisions)}건")
    for column in ("ID", "시각", "프로젝트", "판정", "제안"):
        table.add_column(column)
    for decision in decisions:
        mark = " [dim](대체됨)[/dim]" if decision.id in replaced else ""
        table.add_row(
            decision.id,
            f"{decision.decided_at.astimezone():%m-%d %H:%M}",
            (decision.project or "-").rsplit("/", 1)[-1],
            _outcome(decision),
            decision.proposal[:SUMMARY_CHARS] + mark,
        )
    console.print(table)


@app.command("list")
def list_cmd(
    project: str = typer.Option(None, "--project", "-p", help="작업 디렉터리에 포함된 문자열"),
    verdict: Verdict = typer.Option(None, "--verdict", "-v"),
    since: datetime = typer.Option(None, "--since", help="이 시각 이후 (예: 2026-09-01)"),
) -> None:
    """결정 목록"""
    since = since.astimezone() if since else None
    query = DecisionQuery(project_contains=project, verdict=verdict, since=since)
    _print_table(filter_decisions(load_decisions(resolve_pit_home()), query))


@app.command("search")
def search_cmd(text: str = typer.Argument(..., help="상황·제안·근거·내 말·태그에서 찾을 글")) -> None:
    """글로 찾기 — 프로젝트가 달라도 한 줄기로 나온다"""
    _print_table(filter_decisions(load_decisions(resolve_pit_home()), DecisionQuery(text=text)))


@app.command("show")
def show_cmd(decision_id: str = typer.Argument(...)) -> None:
    """결정 하나의 전체 내용과 출처"""
    decisions = load_decisions(resolve_pit_home())
    decision = next((d for d in decisions if d.id == decision_id), None)
    if decision is None:
        console.print(f"[red]그런 결정이 없습니다: {decision_id}[/red]")
        raise typer.Exit(1)

    replaced_by = superseded_by(decisions).get(decision.id, [])
    lines = [
        f"[dim]상황[/dim]  {decision.situation}",
        f"[dim]제안[/dim]  {decision.proposal}",
        f"[bold]{_outcome(decision)}[/bold]",
        f"[dim]근거[/dim]  {decision.rationale or '-'}",
        f"[dim]내 말[/dim]  {decision.human_quote or '-'}",
        f"[dim]이 결정이 뒤집은 것[/dim]  {', '.join(decision.supersedes) or '-'}",
        f"[dim]이 결정을 뒤집은 것[/dim]  {', '.join(replaced_by) or '-'}",
        f"[dim]출처[/dim]  pit transcripts show {decision.source.session_id[:8]} --at {decision.source.verdict_uuid}",
    ]
    console.print(Panel("\n\n".join(lines), title=decision.id))


@app.command("supersede")
def supersede_cmd(
    new_id: str = typer.Argument(..., help="나중의 결정"),
    old_id: str = typer.Argument(..., help="그것이 뒤집은 이전 결정"),
) -> None:
    """나중의 결정이 이전 결정을 대체한다고 표시한다"""
    home = resolve_pit_home()
    by_id = {decision.id: decision for decision in load_decisions(home)}
    if new_id not in by_id or old_id not in by_id:
        console.print("[red]두 결정이 모두 있어야 합니다.[/red]")
        raise typer.Exit(1)
    if by_id[new_id].decided_at < by_id[old_id].decided_at:
        console.print("[red]대체하는 결정이 더 나중의 것이어야 합니다.[/red]")
        raise typer.Exit(1)

    newer = by_id[new_id]
    if old_id not in newer.supersedes:
        newer.supersedes.append(old_id)
        save_decision_record(home, newer)
        commit_paths(home, [home / DECISIONS_DIR], f"supersede: {new_id} replaces {old_id}")
    console.print(f"{new_id} 이(가) {old_id} 을(를) 대체합니다.")
