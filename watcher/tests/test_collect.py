from datetime import datetime, timedelta, timezone

from git_watcher import resolve_window
from git_watcher.config import Settings
from git_watcher.gitlab import build_email_index, collect, learn_aliases, split_by_day
from git_watcher.report import Briefing, Day, Row
from git_watcher.summarize import Assessment, parse_assessment

SINCE = datetime(2026, 10, 1, 20, tzinfo=timezone.utc)
UNTIL = SINCE + timedelta(days=1)
USERS = [{"id": 1, "username": "alice", "name": "Alice", "email": "alice@corp.com"},
         {"id": 2, "username": "bob", "name": "Bob", "email": "bob@corp.com"}]


def raw_commit(sha: str, email: str, title: str = "feat: x", authored: str = "2026-10-02T01:00:00Z",
               parents: int = 1) -> dict:
    return {"id": sha, "short_id": sha[:8], "author_email": email, "author_name": email.split("@")[0],
            "title": title, "message": title, "authored_date": authored,
            "parent_ids": ["p"] * parents, "stats": {"additions": 3, "deletions": 1}}


class FakeClient:
    def __init__(self, commits: list[dict], pushes: dict[int, list[dict]] | None = None) -> None:
        self._commits = commits
        self._pushes = pushes or {}
        self._by_sha = {c["id"]: c for c in commits}

    def active_projects(self, since: datetime) -> list[dict]:
        return [{"id": 7, "path_with_namespace": "pi/app"}]

    def commits(self, project: dict, since: datetime, until: datetime) -> list[dict]:
        return self._commits

    def changed_files(self, project_id: int, sha: str) -> list[str]:
        return ["src/a.py"]

    def push_events(self, user_id: int, since: datetime) -> list[dict]:
        return self._pushes.get(user_id, [])

    def commit(self, project_id: int, sha: str) -> dict:
        return self._by_sha[sha]


def test_collect_groups_commits_by_registered_email() -> None:
    client = FakeClient([raw_commit("a1", "alice@corp.com"), raw_commit("b1", "BOB@corp.com", "fix: y")])
    accounts = collect(client, SINCE, UNTIL, build_email_index(USERS))
    assert {k: len(a.commits) for k, a in accounts.items()} == {"alice": 1, "bob": 1}


def test_collect_drops_merge_commits_and_rebased_duplicates() -> None:
    commits = [raw_commit("a1", "alice@corp.com"),
               raw_commit("a2", "alice@corp.com"),  # 같은 작업을 다른 브랜치로 리베이스한 사본
               raw_commit("m1", "alice@corp.com", "Merge branch", parents=2)]
    accounts = collect(FakeClient(commits), SINCE, UNTIL, build_email_index(USERS))
    assert len(accounts["alice"].commits) == 1


def test_collect_keeps_unregistered_email_as_separate_account() -> None:
    accounts = collect(FakeClient([raw_commit("x1", "who@mail.example")]), SINCE, UNTIL, build_email_index(USERS))
    assert list(accounts) == ["email:who@mail.example"]


def test_learn_aliases_maps_personal_email_to_pusher() -> None:
    commits = [raw_commit("c1", "alice.home@mail.example")]
    client = FakeClient(commits, {1: [{"project_id": 7, "push_data": {"commit_to": "c1"}}]})
    assert learn_aliases(client, USERS, SINCE, build_email_index(USERS)) == {"alice.home@mail.example": "alice"}


def test_learn_aliases_does_not_steal_registered_email_when_pushing_others_commit() -> None:
    commits = [raw_commit("c1", "bob@corp.com")]
    client = FakeClient(commits, {1: [{"project_id": 7, "push_data": {"commit_to": "c1"}}]})
    assert learn_aliases(client, USERS, SINCE, build_email_index(USERS)) == {}


def test_resolve_window_caps_long_sleep_at_max_lookback(monkeypatch) -> None:
    monkeypatch.setenv("GITLAB_URL", "http://localhost")
    monkeypatch.setenv("GITLAB_TOKEN", "t")
    settings = Settings(_env_file=None)
    now = UNTIL
    since, until = resolve_window(settings, now, now - timedelta(days=30), None)
    assert (until - since) == timedelta(days=settings.max_lookback_days)
    since, _ = resolve_window(settings, now, None, None)
    assert (now - since) == timedelta(hours=settings.default_lookback_hours)


def test_briefing_lists_idle_people_and_escapes_html() -> None:
    accounts = collect(FakeClient([raw_commit("a1", "alice@corp.com")]), SINCE, UNTIL, build_email_index(USERS))
    assessment = Assessment(hours_low=4, hours_high=6, reason="r", headline="<script>", items=["x"])
    rows = [Row("앨리스", accounts["alice"], assessment), Row("밥")]
    briefing = Briefing(SINCE, UNTIL, [Day(UNTIL.date(), rows)])
    html = briefing.to_html()
    assert "&lt;script&gt;" in html and "<script>" not in html
    assert "밥: 커밋 없음" in briefing.to_text()
    assert briefing.subject.endswith("커밋 1건")


def test_split_by_day_uses_report_timezone_not_utc() -> None:
    from zoneinfo import ZoneInfo
    # UTC 10/01 16:00 = KST 10/02 01:00 → 한국 날짜로는 10/02
    commits = [raw_commit("a1", "alice@corp.com", authored="2026-10-01T16:00:00Z"),
               raw_commit("a2", "alice@corp.com", "fix: z", authored="2026-10-01T10:00:00Z")]
    accounts = collect(FakeClient(commits), SINCE, UNTIL, build_email_index(USERS))
    days = split_by_day(accounts, ZoneInfo("Asia/Seoul"))
    assert {d.isoformat(): len(a["alice"].commits) for d, a in days.items()} == {"2026-10-01": 1, "2026-10-02": 1}


def test_parse_assessment_extracts_json_from_noisy_output() -> None:
    text = '결과입니다\n{"hours_low": 4, "hours_high": 6, "reason": "r", "headline": "h", "items": ["a"]}\n끝'
    assert parse_assessment(text).label == "약 4~6시간 (50%~75%)"


def test_parse_assessment_rejects_inverted_or_absurd_hours() -> None:
    import pytest
    for low, high in [(6, 4), (0, 0), (-1, 2), (10, 30)]:
        with pytest.raises(ValueError):
            parse_assessment(f'{{"hours_low": {low}, "hours_high": {high}, "reason": "r", "headline": "h", "items": []}}')


def test_learn_aliases_uses_majority_pusher_not_first() -> None:
    commits = [raw_commit("c1", "x@mail.example"), raw_commit("c2", "x@mail.example", "fix: 2"),
               raw_commit("c3", "x@mail.example", "fix: 3")]
    push = lambda sha: {"project_id": 7, "push_data": {"commit_to": sha}}  # noqa: E731
    client = FakeClient(commits, {1: [push("c1")], 2: [push("c2"), push("c3")]})
    assert learn_aliases(client, USERS, SINCE, build_email_index(USERS)) == {"x@mail.example": "bob"}


def test_parse_assessment_accepts_zero_lower_bound_for_trivial_day() -> None:
    text = '{"hours_low": 0, "hours_high": 0.5, "reason": "r", "headline": "h", "items": []}'
    assert parse_assessment(text).label == "약 0~0.5시간 (0%~6%)"
