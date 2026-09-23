"""pit twin eval — 오프라인 트윈 시험 (G7)"""

import json
import os
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.table import Table

from pit.personal.home import resolve_pit_home
from pit.personal.remote import load_pulled
from pit.server.jev import JevError
from pit.twin.offline import (
    evaluate,
    knn_judge,
    knn_other_projects_judge,
    load_items,
    make_jev_judge,
    prior_judge,
)

console = Console()
app = typer.Typer(help="트윈 시험")

JUDGES = {"prior": prior_judge, "knn": knn_judge, "knn_other_projects": knn_other_projects_judge}


JEV_KEY_ENV = "PITHUB_JEV_API_KEY"
JEV_KEY_FILE = "jev.key"
JEV_TIMEOUT_SECONDS = 20.0


def _jev_key(home: Path) -> str | None:
    """환경변수, 없으면 PIT_HOME/jev.key (0600). 키는 출력하지 않는다."""
    key = os.environ.get(JEV_KEY_ENV, "").strip()
    path = home / JEV_KEY_FILE
    if not key and path.exists():
        key = path.read_text(encoding="utf-8").strip()
    return key or None


def _post(url: str, headers: dict[str, str], body: dict[str, object]) -> dict[str, object]:
    """실패는 JevError 로 — 판정기가 그 건을 기준선으로 물러나 확신도 0으로 센다"""
    try:
        with httpx.Client(timeout=JEV_TIMEOUT_SECONDS) as client:
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        console.print(f"[yellow]JEV 호출 실패: {type(e).__name__}[/yellow]")
        raise JevError(type(e).__name__) from e


@app.command("eval")
def eval_cmd(
    include_leaky: bool = typer.Option(False, "--include-leaky", help="설명에 판정이 샌 결정도 넣는다"),
    jev: bool = typer.Option(False, "--jev", help="JEV 판정기도 돌린다 (시험 건수만큼 API 호출 — 비용 발생)"),
    as_json: bool = typer.Option(False, "--json", help="구조화된 리포트만 출력"),
    output: Optional[Path] = typer.Option(None, "--output", help="리포트를 파일로 저장"),
) -> None:
    """pit pull 로 받은 내 결정으로, 기록이 다음 판정을 맞히는지 시간 순 분할로 잰다 (비용 0)"""
    rows = load_pulled(resolve_pit_home())
    items, dropped = load_items(rows, include_leaky=include_leaky)
    if len(items) < 10:
        console.print(f"[red]판정형 결정이 {len(items)}건뿐입니다. 'pit pull' 을 먼저 실행하세요.[/red]")
        raise typer.Exit(1)
    judges = dict(JUDGES)
    if jev:
        key = _jev_key(resolve_pit_home())
        if key is None:
            console.print(f"[red]{JEV_KEY_ENV} 또는 PIT_HOME/{JEV_KEY_FILE} 이 필요합니다.[/red]")
            raise typer.Exit(1)
        judges["jev"] = make_jev_judge(key, _post)
    report = {"dropped": dropped, **evaluate(items, judges)}
    if output is not None:
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if as_json:
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
        return
    _print(report)


def _print(report: dict[str, object]) -> None:
    console.print(
        f"훈련 {report['n_train']} · 시험 {report['n_test']} (분할 {report['split_at']}) · "
        f"시험 판정 {report['test_labels']} · 제외 {report['dropped']}"
    )
    table = Table("판정기", "정확도", "균형 정확도", "확신≥0.6 범위/정확도", "확신≥0.8 범위/정확도")
    for name, judge in report["judges"].items():  # type: ignore[union-attr]
        cov = judge["coverage"]
        table.add_row(
            name, f"{judge['accuracy']:.3f}", f"{judge['balanced_accuracy']:.3f}",
            f"{cov['0.6']['coverage']:.2f} / {cov['0.6']['accuracy']:.3f}",
            f"{cov['0.8']['coverage']:.2f} / {cov['0.8']['accuracy']:.3f}",
        )  # fmt: skip
    console.print(table)
    for name, ci in report["vs_prior"].items():  # type: ignore[union-attr]
        console.print(f"{name} − prior 균형 정확도 95% 구간: [{ci['ci_low']:+.3f}, {ci['ci_high']:+.3f}]")
