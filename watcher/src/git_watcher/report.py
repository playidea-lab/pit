"""브리핑 본문(평문·HTML)을 만들고 메일로 보낸다."""

import html
from dataclasses import dataclass
from datetime import date, datetime

from git_watcher.gitlab import Account
from git_watcher.summarize import WORKDAY_HOURS, Assessment, activity_span

TIME_FORMAT = "%m/%d %H:%M"
NO_COMMITS = "커밋 없음"
# 하루 근무 대비 추정 비율(중간값)별 배지 색 — (하한 비율, 색), 위에서부터 먼저 맞는 것
RATIO_COLORS = ((1.0, "#1b7f3b"), (0.75, "#4caf50"), (0.5, "#8d8d8d"), (0.25, "#e0a100"), (0.0, "#d9534f"))
NONE_COLOR = "#bdbdbd"


@dataclass
class Row:
    name: str
    account: Account | None = None
    assessment: Assessment | None = None

    @property
    def workload(self) -> str:
        return self.assessment.label if self.assessment else NO_COMMITS

    @property
    def ratio(self) -> float | None:
        mid = self.assessment.midpoint if self.assessment else None
        return None if mid is None else mid / WORKDAY_HOURS

    def cells(self) -> list[str]:
        """요약표 한 줄: 이름, 작업량, 커밋, 변경 줄, 커밋 시간대, 한 줄 요약."""
        if not (self.account and self.assessment):
            return [self.name, NO_COMMITS, "0", "-", "-", "-"]
        commits = self.account.commits
        adds = sum(c.additions for c in commits)
        dels = sum(c.deletions for c in commits)
        return [self.name, self.workload, str(len(commits)), f"+{adds} / -{dels}",
                activity_span(self.account), self.assessment.headline]


HEADERS = ["이름", f"수작업 환산 작업량 (AI 없이 했다면, 하루 {WORKDAY_HOURS}시간 대비)", "커밋", "변경 줄", "커밋 시간대", "한 일"]
WEEKDAYS = "월화수목금토일"
FOOTNOTE = ("수작업 환산 작업량은 커밋 결과물을 AI 없이 손으로 만들었다면 걸렸을 시간을 AI가 추정한 값으로, "
            "실제로 일한 시간이 아니라 결과물의 크기입니다. 에이전트를 쓰는 지금은 실제 시간이 이보다 훨씬 짧습니다"
            "(재현 실험에서 5~10배). "
            "회의·리뷰·조사·문서 작업처럼 커밋에 남지 않는 일은 반영되지 않습니다. "
            "커밋 시간대는 그날 첫 커밋~마지막 커밋 시각이며 업무 시작·종료 시각이 아닙니다.")


@dataclass
class Day:
    """하루치 구역. 커밋한 날짜(한국 시간) 기준."""

    date: date
    rows: list[Row]

    @property
    def title(self) -> str:
        return f"{self.date:%m/%d}({WEEKDAYS[self.date.weekday()]})"

    @property
    def active(self) -> list[Row]:
        return [r for r in self.rows if r.assessment]

    def to_text(self) -> str:
        parts = [f"==== {self.title} ===="]
        for row in self.rows:
            name, workload, commits, lines, span, headline = row.cells()
            parts.append(f"- {name}: {workload} (커밋 {commits}, {lines}, {span}) {headline}")
        for row in self.active:
            assert row.assessment is not None
            parts += ["", f"■ {row.name} — 수작업 환산 {row.workload}", f"근거: {row.assessment.reason}"]
            parts += [f"- {item}" for item in row.assessment.items]
        return "\n".join(parts)

    def to_html(self) -> str:
        head = "".join(f"<th style='text-align:left;padding:6px 8px'>{h}</th>" for h in HEADERS)
        body = "".join(_table_row(r) for r in self.rows)
        details = "".join(_detail(r) for r in self.active)
        return (f"<h2 style='margin:28px 0 8px;border-bottom:2px solid #222;padding-bottom:4px'>"
                f"{self.title}</h2>"
                "<table style='border-collapse:collapse;width:100%'>"
                f"<tr style='background:#f2f2f2'>{head}</tr>{body}</table>{details}")


@dataclass
class Briefing:
    since: datetime
    until: datetime
    days: list[Day]

    @property
    def subject(self) -> str:
        total = sum(len(r.account.commits) for d in self.days for r in d.active if r.account)
        if not self.days:
            span = f"{self.until:%m/%d}"
        elif len(self.days) == 1:
            span = self.days[0].title
        else:
            span = f"{self.days[0].title}~{self.days[-1].title}"
        return f"[GitLab 브리핑] {span} — 커밋 {total}건"

    def period(self) -> str:
        return f"{self.since:{TIME_FORMAT}} ~ {self.until:{TIME_FORMAT}}"

    def to_text(self) -> str:
        days = "\n\n".join(d.to_text() for d in self.days) or "이 기간에 커밋이 없습니다."
        return f"기간: {self.period()}\n\n{days}"

    def to_html(self) -> str:
        days = "".join(d.to_html() for d in self.days) or "<p>이 기간에 커밋이 없습니다.</p>"
        return ("<div style='font-family:sans-serif;font-size:14px;color:#222'>"
                f"<p style='color:#666'>기간: {html.escape(self.period())}</p>{days}"
                f"<p style='color:#999;font-size:12px;margin-top:24px'>{FOOTNOTE}</p></div>")


def _detail(row: Row) -> str:
    assert row.assessment is not None
    items = "".join(f"<li>{html.escape(i)}</li>" for i in row.assessment.items)
    return (f"<h3 style='margin:20px 0 4px'>{html.escape(row.name)} {_badge(row)}</h3>"
            f"<div style='color:#666'>근거: {html.escape(row.assessment.reason)}</div>"
            f"<ul style='line-height:1.7;margin-top:6px'>{items}</ul>")


def _badge(row: Row) -> str:
    ratio = row.ratio
    color = NONE_COLOR if ratio is None else next(c for floor, c in RATIO_COLORS if ratio >= floor)
    return (f"<span style='background:{color};color:#fff;border-radius:4px;padding:2px 8px;"
            f"font-size:12px;white-space:nowrap'>{html.escape(row.workload)}</span>")


def _table_row(row: Row) -> str:
    name, workload, *rest = row.cells()
    cell = "padding:6px 8px;border-top:1px solid #e5e5e5;vertical-align:top"
    tds = [f"<td style='{cell};white-space:nowrap'><b>{html.escape(name)}</b></td>",
           f"<td style='{cell}'>{_badge(row)}</td>"]
    tds += [f"<td style='{cell}'>{html.escape(v)}</td>" for v in rest]
    return f"<tr>{''.join(tds)}</tr>"
