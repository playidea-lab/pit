"""pit twin eval — 오프라인 트윈 시험 (G7)"""

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from pit.personal.home import resolve_pit_home
from pit.personal.remote import load_pulled
from pit.twin.offline import evaluate, knn_judge, knn_other_projects_judge, load_items, prior_judge

console = Console()
app = typer.Typer(help="트윈 시험")

JUDGES = {"prior": prior_judge, "knn": knn_judge, "knn_other_projects": knn_other_projects_judge}


@app.command("eval")
def eval_cmd(
    include_leaky: bool = typer.Option(False, "--include-leaky", help="설명에 판정이 샌 결정도 넣는다"),
    as_json: bool = typer.Option(False, "--json", help="구조화된 리포트만 출력"),
    output: Optional[Path] = typer.Option(None, "--output", help="리포트를 파일로 저장"),
) -> None:
    """pit pull 로 받은 내 결정으로, 기록이 다음 판정을 맞히는지 시간 순 분할로 잰다 (비용 0)"""
    rows = load_pulled(resolve_pit_home())
    items, dropped = load_items(rows, include_leaky=include_leaky)
    if len(items) < 10:
        console.print(f"[red]판정형 결정이 {len(items)}건뿐입니다. 'pit pull' 을 먼저 실행하세요.[/red]")
        raise typer.Exit(1)
    report = {"dropped": dropped, **evaluate(items, JUDGES)}
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
