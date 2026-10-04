"""지난달 전체를 사람·날짜별 GitLab 활동 시각으로 정리한 월간 리포트.

시각은 근무 시각이 아니라 GitLab에 남은 흔적(커밋 작성, push, 이슈, MR, 댓글)의
첫~마지막 시각이다. 그 전후의 작업·회의는 보이지 않는다.
"""

import json
import logging
import subprocess
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, tzinfo

from pydantic import BaseModel, ValidationError

from git_watcher.calendar_kr import day_kind, is_workday, month_days
from git_watcher.gitlab import Account, Commit, GitLabClient, split_by_day
from git_watcher.summarize import WORKDAY_HOURS, Summarizer

logger = logging.getLogger(__name__)

# 월간 요약 입력에 넣는 커밋 제목 최대 개수 (사람당)
MAX_TITLES_PER_PERSON = 400
SECONDS_PER_HOUR = 3600
MINUTES_PER_HOUR = 60
# 월간 일별 추정을 동시에 돌리는 claude 호출 수
CLAUDE_PARALLEL = 4

MONTHLY_PROMPT = """당신은 개발을 모르는 대표에게 팀원의 한 달 작업을 보고하는 비서다.
한 사람의 한 달치 GitLab 커밋 제목(날짜·프로젝트별)이 주어진다.

반드시 아래 JSON 하나만 출력하라 (코드블록·설명 없이):
{"headline": "이번 달 한 일을 비개발자도 이해하는 한 문장",
 "items": ["주요 작업 (쉬운 말, 결과 중심)", "..."]}

규칙: items는 최대 5개, 각 항목 앞에 [서비스 이름]. 커밋에 근거가 있는 것만 쓴다.
근무 태도·능력은 평가하지 않는다. 모든 문장은 '~했다' 체."""


class MonthlyNarrative(BaseModel):
    headline: str
    items: list[str]


@dataclass
class DayActivity:
    first: datetime | None = None
    last: datetime | None = None
    commits: int = 0
    additions: int = 0
    deletions: int = 0
    events: int = 0
    # 그날 커밋 내용으로 AI가 추정한 작업 시간 범위 (커밋 없는 날은 None)
    hours_low: float | None = None
    hours_high: float | None = None

    def touch(self, at: datetime) -> None:
        self.first = at if self.first is None or at < self.first else self.first
        self.last = at if self.last is None or at > self.last else self.last

    @property
    def span_hours(self) -> float | None:
        if self.first is None or self.last is None:
            return None
        return (self.last - self.first).total_seconds() / SECONDS_PER_HOUR


@dataclass
class PersonMonth:
    username: str
    name: str
    days: dict[date, DayActivity] = field(default_factory=lambda: defaultdict(DayActivity))
    commits: list[Commit] = field(default_factory=list)
    narrative: MonthlyNarrative | None = None

    def active_workdays(self) -> list[DayActivity]:
        return [a for d, a in sorted(self.days.items()) if is_workday(d) and a.first]

    def offday_count(self) -> int:
        return sum(1 for d, a in self.days.items() if not is_workday(d) and a.first)


def month_window(year: int, month: int, tz: tzinfo) -> tuple[datetime, datetime]:
    days = month_days(year, month)
    start = datetime.combine(days[0], time.min, tz)
    return start, datetime.combine(days[-1] + timedelta(days=1), time.min, tz)


def add_commits(person: PersonMonth, account: Account, tz: tzinfo) -> None:
    for commit in account.commits:
        at = datetime.fromisoformat(commit.authored_at).astimezone(tz)
        day = person.days[at.date()]
        day.touch(at)
        day.commits += 1
        day.additions += commit.additions
        day.deletions += commit.deletions
        person.commits.append(commit)


def add_events(person: PersonMonth, gl: GitLabClient, user_id: int, start: datetime, end: datetime) -> None:
    """push·이슈·MR·댓글 등 모든 이벤트 시각을 활동으로 더한다. 기간 밖은 버린다."""
    after = (start.date() - timedelta(days=1)).isoformat()
    for event in gl.events(user_id, after, end.date().isoformat()):
        at = datetime.fromisoformat(event["created_at"].replace("Z", "+00:00")).astimezone(start.tzinfo)
        if start <= at < end:
            day = person.days[at.date()]
            day.touch(at)
            day.events += 1


def narrate(summarizer: Summarizer, person: PersonMonth) -> MonthlyNarrative | None:
    if not person.commits:
        return None
    lines = [f"{c.authored_at[5:10]} [{c.project.rsplit('/', 1)[-1]}] {c.title}"
             for c in sorted(person.commits, key=lambda c: c.authored_at)][:MAX_TITLES_PER_PERSON]
    try:
        text = summarizer.ask(MONTHLY_PROMPT, "\n".join(lines))
        start, end = text.find("{"), text.rfind("}")
        return MonthlyNarrative.model_validate(json.loads(text[start:end + 1]))
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, ValidationError) as e:
        logger.error("월간 요약 실패 user=%s: %s", person.username, e)
        return None


def estimate_days(summarizer: Summarizer, people: list[PersonMonth], tz: tzinfo) -> None:
    """사람·날짜마다 일일 메일과 같은 기준으로 작업 시간을 추정해 DayActivity에 채운다."""
    jobs: list[tuple[DayActivity, Account]] = []
    for person in people:
        account = Account(key=person.username, display=person.name, commits=person.commits)
        for day, day_account in split_by_day({person.username: account}, tz).items():
            jobs.append((person.days[day], day_account[person.username]))
    with ThreadPoolExecutor(max_workers=CLAUDE_PARALLEL) as pool:
        for act, assessment in zip(
            (a for a, _ in jobs), pool.map(summarizer.assess, (acc for _, acc in jobs)), strict=True
        ):
            act.hours_low, act.hours_high = assessment.hours_low, assessment.hours_high
    logger.info("일별 작업 시간 추정 %d건", len(jobs))


def estimate_total(person: PersonMonth) -> tuple[float, float] | None:
    """한 달 수작업 환산 작업량 합계 (주말·공휴일 포함). 추정이 하나도 없으면 None."""
    days = [a for a in person.days.values() if a.hours_low is not None and a.hours_high is not None]
    if not days:
        return None
    return sum(a.hours_low for a in days), sum(a.hours_high for a in days)


def estimate_cell(person: PersonMonth, workday_total: int) -> str:
    total = estimate_total(person)
    if total is None:
        return "-"
    capacity = workday_total * WORKDAY_HOURS
    low, high = total
    return f"{low:g}~{high:g}시간 ({low / capacity:.0%}~{high / capacity:.0%})"


def summary_cells(person: PersonMonth, workday_total: int) -> dict[str, str | int | float]:
    """월별 요약표 한 줄 (엑셀·메일 공용)."""
    active = person.active_workdays()
    firsts = [a.first for a in active if a.first]
    lasts = [a.last for a in active if a.last]
    spans = [a.span_hours for a in active if a.span_hours is not None]
    return {
        "이름": person.name,
        f"수작업 환산 작업량 (근무일×{WORKDAY_HOURS}시간 대비)": estimate_cell(person, workday_total),
        "활동한 근무일": f"{len(active)} / {workday_total}",
        "휴일 활동일": person.offday_count(),
        "평균 첫 활동": mean_clock(firsts),
        "평균 마지막 활동": mean_clock(lasts),
        "평균 활동 폭(시간)": round(sum(spans) / len(spans), 1) if spans else "-",
        "커밋": len(person.commits),
        "변경 줄": f"+{sum(c.additions for c in person.commits)} / -{sum(c.deletions for c in person.commits)}",
    }


def mean_clock(times: list[datetime]) -> str:
    """시각들의 평균을 HH:MM으로. 자정을 넘기는 활동은 드물다고 보고 단순 평균한다."""
    if not times:
        return "-"
    minutes = sum(t.hour * MINUTES_PER_HOUR + t.minute for t in times) // len(times)
    return f"{minutes // MINUTES_PER_HOUR:02d}:{minutes % MINUTES_PER_HOUR:02d}"


def daily_rows(person: PersonMonth, year: int, month: int) -> list[list[str | int | float]]:
    """일별 시트: 그 달의 모든 날짜 × 사람 한 줄 (활동 없는 날도 포함)."""
    rows = []
    for day in month_days(year, month):
        act = person.days.get(day, DayActivity())
        span = act.span_hours
        rows.append([
            day.isoformat(), "월화수목금토일"[day.weekday()], day_kind(day), person.name,
            f"{act.first:%H:%M}" if act.first else "", f"{act.last:%H:%M}" if act.last else "",
            round(span, 1) if span is not None else "",
            act.hours_low if act.hours_low is not None else "",
            act.hours_high if act.hours_high is not None else "",
            f"{(act.hours_low + act.hours_high) / 2 / WORKDAY_HOURS:.0%}" if act.hours_low is not None else "",
            act.commits, act.additions, act.deletions, act.events,
        ])
    return rows
