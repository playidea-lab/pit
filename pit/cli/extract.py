"""pit extract CLI — 보관된 세션에서 결정 후보 만들기"""

from datetime import datetime, timezone

import typer
from dotenv import load_dotenv
from rich.console import Console

from pit.extract.pipeline import ExtractionLimits, run_extraction
from pit.llm.anthropic_client import AnthropicClient
from pit.llm.client import LLMError, ModelTask, require_model_id
from pit.personal.config import ConfigError, load_config
from pit.personal.home import resolve_pit_home

console = Console()

# 한글 위주 글의 거친 환산 (문자 수 ÷ 이 값 ≈ 토큰 수). 비용 가늠용일 뿐이다.
ROUGH_CHARS_PER_TOKEN = 2


def extract_cmd(
    dry_run: bool = typer.Option(False, "--dry-run", help="LLM을 부르지 않고 호출 수만 센다"),
    max_calls: int = typer.Option(None, "--max-calls", help="이번 실행의 LLM 호출 상한"),
    structured_only: bool = typer.Option(False, "--structured-only", help="구조 신호만 추출 (LLM 없음)"),
) -> None:
    """보관함의 세션에서 결정 후보를 추출한다"""
    load_dotenv()
    home = resolve_pit_home()
    try:
        config = load_config(home)
        client, model_id = None, None
        if not structured_only:
            model_id = require_model_id(config.models, ModelTask.EXTRACT)
            client = None if dry_run else AnthropicClient()
    except (ConfigError, LLMError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e

    limits = ExtractionLimits(max_calls=max_calls, dry_run=dry_run)
    report = run_extraction(home, config, client, model_id, limits, datetime.now(timezone.utc))

    console.print(f"세션 {report.sessions}개")
    console.print(f"후보: 구조 신호 {report.structured}건, LLM {report.llm}건 (이미 아는 것 {report.already_known}건)")
    if not structured_only:
        tokens = report.planned_chars // ROUGH_CHARS_PER_TOKEN
        console.print(f"LLM 호출: 실행 {report.calls} / 필요 {report.planned_calls} (입력 약 {tokens:,} 토큰)")
    if report.errors:
        console.print(f"[yellow]버린 라벨·실패: {dict(report.errors)}[/yellow]")
    if dry_run:
        console.print("[dim]--dry-run: 아무것도 저장하지 않았습니다.[/dim]")
