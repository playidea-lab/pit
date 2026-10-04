from datetime import UTC
from zoneinfo import ZoneInfo

from git_watcher.agent_activity import IDLE_GAP, summarize

KST = ZoneInfo("Asia/Seoul")


def ev(ts: str, name: str = "api_request", **kw: object) -> dict[str, object]:
    return {"ts": ts, "event.name": name, "service.name": "claude-code", "user.email": "a@corp.com", **kw}


def test_active_minutes_splits_on_idle_gap_and_ignores_breaks() -> None:
    # 10:00~10:10 작업, 한 시간 쉬고, 11:10~11:20 작업 → 쉰 시간은 세지 않는다
    events = [ev("2026-10-05T01:00:00+00:00", "user_prompt", prompt_length=80),
              ev("2026-10-05T01:10:00+00:00"),
              ev("2026-10-05T02:10:00+00:00", "user_prompt", prompt_length=20),
              ev("2026-10-05T02:20:00+00:00", "tool_result")]
    (day,) = summarize(events, KST)
    assert len(day.windows()) == 2
    assert day.active_minutes == 24.0  # (10+2) + (10+2)
    assert (day.prompts, day.prompt_chars, day.tool_calls) == (2, 100, 1)
    assert IDLE_GAP.total_seconds() < 3600


def test_summarize_separates_people_repos_and_tools_by_kst_day() -> None:
    events = [ev("2026-10-04T16:30:00+00:00", **{"repo.name": "pi/phenotype"}),  # KST 10/5 01:30
              {"ts": "2026-10-05T01:00:00+00:00", "event.name": "codex.user_prompt", "service.name": "codex_exec",
               "user.account_id": "acct-9", "prompt_length": "12", "repo.name": "pi/phenotype"}]
    days = summarize(events, KST)
    assert [(d.day.isoformat(), d.who, d.repo, sorted(d.tools)) for d in days] == [
        ("2026-10-05", "a@corp.com", "pi/phenotype", ["claude-code"]),
        ("2026-10-05", "acct-9", "pi/phenotype", ["codex"]),
    ]
    assert days[1].prompt_chars == 12
    assert UTC is not None
