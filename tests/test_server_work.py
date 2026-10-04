"""작업 보고 도구 (report_start / report_commit) — 합성 데이터만 쓴다."""

import asyncio
from datetime import datetime, timezone

import pytest

pytest.importorskip("fastmcp", reason="서버 extra가 설치된 환경에서만 실행")

from fastmcp import Client  # noqa: E402

from pit.server.app import build_server  # noqa: E402
from pit.server.identity import Caller  # noqa: E402
from pit.server.ratelimit import RateLimiter  # noqa: E402
from pit.server.settings import ServerSettings  # noqa: E402
from pit.server.work import WorkToolFailure, WorkTools  # noqa: E402
from tests.fakes import FakeClock, InMemoryRepository  # noqa: E402

NOW = datetime(2026, 10, 4, 3, 0, tzinfo=timezone.utc)
ALICE = Caller(github_id=1001, github_login="alice")
BOB = Caller(github_id=2002, github_login="bob")
SHA = "a1b2c3d4e5f6"
SETTINGS = ServerSettings(
    github_client_id="placeholder-id", github_client_secret="placeholder-secret",
    base_url="http://127.0.0.1:8000", host="127.0.0.1", port=8000,
)  # fmt: skip


def make_tools(repository: InMemoryRepository | None = None) -> tuple[WorkTools, InMemoryRepository]:
    repository = repository or InMemoryRepository()
    return WorkTools(repository, RateLimiter(FakeClock()), lambda: NOW), repository


def run(coro):  # noqa: ANN001, ANN201
    return asyncio.run(coro)


def test_report_start_then_commit_links_and_keeps_expected_size() -> None:
    tools, repo = make_tools()
    start = run(tools.report_start(ALICE, {"task": "설문 soft delete", "task_kind": "feature",
                                           "expected_manual_hours": 4, "expected_agent_minutes": 10}))
    done = run(tools.report_commit(ALICE, {"task": "설문 soft delete", "task_kind": "feature", "commit_sha": SHA,
                                           "start_id": start["id"], "atomic": True, "message_ok": True}))
    assert done["flags"] == []
    started, committed = repo.work_reports
    assert (started.kind, started.expected_manual_hours) == ("start", 4)
    assert (committed.kind, committed.start_id, committed.commit_sha) == ("commit", start["id"], SHA)


def test_report_commit_rejects_someone_elses_start_id() -> None:
    tools, _ = make_tools()
    start = run(tools.report_start(ALICE, {"task": "t", "task_kind": "fix"}))
    with pytest.raises(WorkToolFailure, match="start_id"):
        run(tools.report_commit(BOB, {"task": "t", "task_kind": "fix", "commit_sha": SHA,
                                      "start_id": start["id"], "atomic": True, "message_ok": True}))


def test_report_commit_flags_non_atomic_and_rejects_bad_sha() -> None:
    tools, _ = make_tools()
    result = run(tools.report_commit(ALICE, {"task": "t", "task_kind": "fix", "commit_sha": SHA,
                                             "atomic": False, "atomic_note": "두 기능이 섞임", "message_ok": True}))
    assert result["flags"]
    with pytest.raises(WorkToolFailure, match="commit_sha"):
        run(tools.report_commit(ALICE, {"task": "t", "task_kind": "fix", "commit_sha": "not-a-sha!",
                                        "atomic": True, "message_ok": True}))


def test_report_redacts_secrets_in_free_text() -> None:
    tools, repo = make_tools()
    run(tools.report_start(ALICE, {"task": "키 교체", "task_kind": "ops",
                                   "intent": "AWS 키 AKIAIOSFODNN7EXAMPLE 를 새 키로 바꿈"}))
    (stored,) = repo.work_reports
    assert "AKIAIOSFODNN7EXAMPLE" not in stored.intent and stored.redactions.get("intent") == 1


def test_report_rejects_unknown_implements_ids() -> None:
    tools, _ = make_tools()
    with pytest.raises(WorkToolFailure, match="implements"):
        run(tools.report_start(ALICE, {"task": "t", "task_kind": "feature", "implements": ["D-nope"]}))


def test_report_goes_to_the_single_team_so_its_owner_can_read_it() -> None:
    repo = InMemoryRepository()
    repo.memberships[ALICE.github_id] = [("team-uuid-1", "pilab")]
    tools, _ = make_tools(repo)
    run(tools.report_start(ALICE, {"task": "t", "task_kind": "feature"}))
    assert repo.work_reports[0].team_id == "team-uuid-1"


def test_mcp_lists_report_tools() -> None:
    server = build_server(SETTINGS, InMemoryRepository())

    async def names() -> set[str]:
        async with Client(server) as client:
            return {tool.name for tool in await client.list_tools()}

    assert {"report_start", "report_commit"} <= run(names())
