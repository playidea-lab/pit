"""pit login | push | pull | audit — pithub 서버와의 연동"""

import json
from datetime import datetime, timezone
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from pit.audit.mcp_audit import McpRecord, audit
from pit.decisions.store import load_decisions
from pit.personal.home import ensure_home, resolve_pit_home
from pit.personal.remote import (
    RemoteClient,
    RemoteConfig,
    RemoteError,
    load_pulled,
    load_remote,
    resolve_url,
    save_pulled,
    save_remote,
)

console = Console()
audit_app = typer.Typer(help="MCP 기록을 원문 추출과 대조한다")

PREVIEW_ROWS = 5


def _client(home) -> RemoteClient:  # noqa: ANN001
    saved = load_remote(home)
    if saved is None:
        console.print("[red]먼저 'pit login' 을 실행하세요.[/red]")
        raise typer.Exit(1)
    return RemoteClient(saved.url, saved.token)


def _fail(e: RemoteError) -> None:
    console.print(f"[red]{e}[/red]")
    raise typer.Exit(1) from e


def login_cmd(
    url: Optional[str] = typer.Option(None, "--url", help="pithub 주소 (환경변수 PITHUB_URL 대신)"),
) -> None:
    """pithub 설정 화면에서 발급한 토큰을 저장한다"""
    home = resolve_pit_home()
    ensure_home(home)
    saved = load_remote(home)
    try:
        resolved = resolve_url(url, saved)
    except RemoteError as e:
        _fail(e)
    token = typer.prompt("토큰 (pit_ 로 시작, 입력은 보이지 않습니다)", hide_input=True).strip()

    try:
        me = RemoteClient(resolved, token).whoami()
    except RemoteError as e:
        _fail(e)
    save_remote(home, RemoteConfig(url=resolved, token=token, github_login=str(me.get("github_login"))))
    console.print(f"{resolved} 에 [bold]{me.get('github_login')}[/bold] 로 연결됐습니다.")


def push_cmd(
    yes: bool = typer.Option(False, "--yes", "-y", help="확인 없이 올린다"),
) -> None:
    """로컬에서 확정한 결정을 pithub에 올린다 (비공개로 들어간다)"""
    home = resolve_pit_home()
    client = _client(home)
    decisions = [d for d in load_decisions(home) if d.review is not None]
    if not decisions:
        console.print("올릴 결정이 없습니다.")
        return

    table = Table(title=f"올릴 결정 {len(decisions)}건 (앞 {PREVIEW_ROWS}건)")
    for column in ("ID", "판정", "제안"):
        table.add_column(column)
    for d in decisions[:PREVIEW_ROWS]:
        table.add_row(d.id, d.verdict.value if d.verdict else f"→ {d.chosen}", d.proposal[:60])
    console.print(table)
    console.print("[dim]원문·출처 세션 내용은 올라가지 않습니다. 서버에서는 본인만 볼 수 있습니다.[/dim]")
    if not yes and not typer.confirm("올릴까요?", default=False):
        raise typer.Exit(0)

    try:
        count = client.push(decisions)
    except RemoteError as e:
        _fail(e)
    console.print(f"{count}건 반영됐습니다.")


def pull_cmd(
    since: Optional[datetime] = typer.Option(None, "--since", help="이 시각 이후만 (ISO 8601)"),
) -> None:
    """pithub의 내 결정을 내려받아 $PIT_HOME/remote/ 에 둔다"""
    home = resolve_pit_home()
    client = _client(home)
    try:
        rows = client.pull(since=since)
    except RemoteError as e:
        _fail(e)
    path = save_pulled(home, rows)
    console.print(f"{len(rows)}건을 {path} 에 저장했습니다.")


@audit_app.command("mcp")
def audit_mcp_cmd(
    since: Optional[datetime] = typer.Option(None, "--since", help="이 시각 이후만"),
    as_json: bool = typer.Option(False, "--json", help="구조화된 리포트로 출력"),
) -> None:
    """MCP가 기록한 결정 vs 원문에서 추출해 확정한 결정 — 재현율·판정 일치율 (먼저 'pit pull')"""
    home = resolve_pit_home()
    pulled = [row for row in load_pulled(home) if row.get("origin") == "mcp"]
    if not pulled:
        console.print("[yellow]내려받은 MCP 기록이 없습니다. 'pit pull' 을 먼저 실행하세요.[/yellow]")
        raise typer.Exit(1)
    records = [
        McpRecord(id=str(r["id"]), verdict=r.get("verdict"), human_quote=str(r.get("human_quote", "")),
                  decided_at=datetime.fromisoformat(str(r["decided_at"])))
        for r in pulled
    ]  # fmt: skip
    if since is not None and since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)

    report = audit(load_decisions(home), records, since)
    if as_json:
        console.print_json(json.dumps(report.as_dict(), ensure_ascii=False))
        return

    table = Table(title="MCP 기록 감사")
    for column in ("항목", "값", "기준"):
        table.add_column(column)
    checks = report.gate_checks
    rows = [
        ("로컬 확정 결정", str(report.local_total), ""),
        ("MCP 기록", str(report.mcp_total), ""),
        ("짝이 된 결정", str(report.matched), ""),
        ("재현율", _pct(report.recall), _verdict(checks["recall"])),
        ("거부 재현율", _pct(report.reject_recall), _verdict(checks["reject_recall"])),
        ("판정 일치율", _pct(report.verdict_agreement), _verdict(checks["verdict_agreement"])),
    ]
    for row in rows:
        table.add_row(*row)
    console.print(table)


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.1%}"


def _verdict(passed: bool | None) -> str:
    if passed is None:
        return "[dim]판정 불가[/dim]"
    return "[green]통과[/green]" if passed else "[red]미달[/red]"
