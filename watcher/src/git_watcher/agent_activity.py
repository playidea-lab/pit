"""텔레메트리 요약 이벤트 → 사람·날짜·저장소별 '에이전트와 일한 시간' 요약.

실투입은 이벤트가 이어진 구간의 합이다. 이벤트 사이가 IDLE_GAP 보다 벌어지면 다른 구간으로 본다
(자리를 비웠거나 다른 일을 한 시간은 세지 않는다). 커밋 시각만 보던 것보다 사람 쪽 시간을 직접 잰다.
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, tzinfo
from pathlib import Path

# 이 시간보다 이벤트가 끊기면 쉬었거나 다른 일을 한 것으로 본다
IDLE_GAP = timedelta(minutes=15)
# 구간 하나의 끝에 붙이는 여유 (마지막 이벤트 뒤 결과를 읽는 시간)
TAIL_ALLOWANCE = timedelta(minutes=2)
PROMPT_EVENTS = ("user_prompt", "codex.user_prompt")
TOOL_EVENTS = ("tool_result", "codex.tool_result")
SECONDS_PER_MINUTE = 60
UNKNOWN_REPO = "(저장소 표시 없음)"


@dataclass
class AgentDay:
    """한 사람·하루·저장소의 에이전트 활동 요약."""

    who: str
    day: date
    repo: str
    tools: set[str] = field(default_factory=set)
    times: list[datetime] = field(default_factory=list)
    prompts: int = 0
    prompt_chars: int = 0
    tool_calls: int = 0
    cost_usd: float = 0.0

    def windows(self) -> list[tuple[datetime, datetime]]:
        """IDLE_GAP 기준으로 끊은 작업 구간들."""
        spans: list[tuple[datetime, datetime]] = []
        for t in sorted(self.times):
            if spans and t - spans[-1][1] <= IDLE_GAP:
                spans[-1] = (spans[-1][0], t)
            else:
                spans.append((t, t))
        return spans

    @property
    def active_minutes(self) -> float:
        total = sum(((end - start) + TAIL_ALLOWANCE).total_seconds() for start, end in self.windows())
        return round(total / SECONDS_PER_MINUTE, 1)


def identity(event: dict[str, object]) -> str:
    """도구 계정 식별자. 이메일이 있으면 이메일, 없으면 계정 ID."""
    for key in ("user.email", "user.account_id", "user.account_uuid", "user.id"):
        if event.get(key):
            return str(event[key])
    return "(알 수 없음)"


def tool_of(event: dict[str, object]) -> str:
    name = str(event.get("service.name") or "")
    return "codex" if name.startswith("codex") else ("claude-code" if name == "claude-code" else name or "?")


def _number(v: object) -> float:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def summarize(events: list[dict[str, object]], tz: tzinfo) -> list[AgentDay]:
    days: dict[tuple[str, date, str], AgentDay] = {}
    for e in events:
        raw_ts = e.get("ts") or e.get("event.timestamp")  # 수정 전에 쌓인 Codex 이벤트는 ts가 없다
        if not raw_ts:
            continue
        t = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00")).astimezone(tz)
        who, repo = identity(e), str(e.get("repo.name") or UNKNOWN_REPO)
        d = days.setdefault((who, t.date(), repo), AgentDay(who, t.date(), repo))
        d.tools.add(tool_of(e))
        d.times.append(t)
        name = str(e.get("event.name") or "")
        if name in PROMPT_EVENTS:
            d.prompts += 1
            d.prompt_chars += int(_number(e.get("prompt_length")))
        elif name in TOOL_EVENTS:
            d.tool_calls += 1
        d.cost_usd += _number(e.get("cost_usd"))
    return sorted(days.values(), key=lambda d: (d.day, d.who, d.repo))


def load_events(root: Path, since: date, until: date) -> list[dict[str, object]]:
    """수집기가 남긴 날짜별 JSONL 중 기간에 걸친 파일을 읽는다 (파일 날짜는 UTC 기준)."""
    events: list[dict[str, object]] = []
    # 대화 기록에서 소급한 요약 (파일 이름이 날짜가 아니라 대화 ID다)
    for path in sorted((root / "backfill").glob("*.jsonl")):
        events.extend(json.loads(line) for line in path.read_text().splitlines() if line.strip())
    for path in sorted(root.glob("*.jsonl")):
        file_day = date.fromisoformat(path.stem)
        if since - timedelta(days=1) <= file_day <= until + timedelta(days=1):
            events.extend(json.loads(line) for line in path.read_text().splitlines() if line.strip())
    return events
