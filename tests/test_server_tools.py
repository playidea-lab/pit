"""pithub MCP 도구 테스트 — 가짜 저장소, 네트워크 없음"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

pytest.importorskip("fastmcp", reason="서버 extra가 설치된 환경에서만 실행")

from fastmcp import Client  # noqa: E402
from fastmcp.exceptions import ToolError  # noqa: E402

from pit.server import identity  # noqa: E402
from pit.server.app import STORAGE_NOT_READY, build_server  # noqa: E402
from pit.server.identity import Caller  # noqa: E402
from pit.server.ratelimit import RateLimiter  # noqa: E402
from pit.server.repository import RepositoryError, SupabaseRepository, sanitize_query  # noqa: E402
from pit.server.settings import (  # noqa: E402
    ENV_OAUTH_STORAGE_DIR,
    ServerSettings,
    SettingsError,
    load_settings,
)
from pit.server.tools import DecisionTools, ToolFailure  # noqa: E402
from tests.fakes import FakeClock, InMemoryRepository  # noqa: E402

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
ALICE = Caller(github_id=1001, github_login="alice")
BOB = Caller(github_id=2002, github_login="bob")
SETTINGS = ServerSettings(
    github_client_id="placeholder-id", github_client_secret="placeholder-secret",
    base_url="http://127.0.0.1:8000", host="127.0.0.1", port=8000,
)  # fmt: skip


def _arguments(**overrides: object) -> dict[str, object]:
    base = {
        "situation": "캐시 전략을 정하던 중",
        "proposal": "매번 전체를 다시 읽는다",
        "human_quote": "아니, 바뀐 세션만 다시 읽자",
        "verdict": "reject",
        "reject_kind": "redirect",
    }
    return {**base, **overrides}


def _tools(repository: InMemoryRepository, max_calls: int = 100) -> DecisionTools:
    return DecisionTools(repository, RateLimiter(FakeClock(), max_calls=max_calls), lambda: NOW)


def _run(coroutine):  # noqa: ANN001, ANN202
    return asyncio.run(coroutine)


def test_record_decision_stores_private_draft_for_the_caller():
    repository = InMemoryRepository()

    result = _run(_tools(repository).record_decision(ALICE, _arguments(client="claude.ai")))

    (row,) = repository.rows
    assert result == {"id": row.id, "status": "recorded", "redacted": 0}
    assert (row.owner_github_id, row.status, row.visibility, row.origin) == (1001, "draft", "private", "mcp")
    assert (row.kind, row.verdict, row.reject_kind) == ("verdict", "reject", "redirect")
    assert row.source == {"client": "claude.ai"}
    assert repository.accounts == {1001: "alice"}


def test_record_decision_project_default_sets_scope_else_private():
    repository = InMemoryRepository()
    repository.project_defaults[(1001, "pit")] = ("team", "team-uuid")
    tools = _tools(repository)

    _run(tools.record_decision(ALICE, _arguments(project="pit")))
    _run(tools.record_decision(ALICE, _arguments(project="other", human_quote="다른 프로젝트")))
    _run(tools.record_decision(ALICE, _arguments(human_quote="프로젝트 없음")))

    scopes = [(row.visibility, row.team_id) for row in repository.rows]
    assert scopes == [("team", "team-uuid"), ("private", None), ("private", None)]
    assert all(row.status == "draft" for row in repository.rows)


def test_record_decision_backfill_keeps_given_past_time_and_id_follows_it():
    repository = InMemoryRepository()

    _run(_tools(repository).record_decision(ALICE, _arguments(decided_at="2026-08-25T10:00:00+09:00", client="claude-memory")))

    (row,) = repository.rows
    assert row.decided_at.isoformat() == "2026-08-25T10:00:00+09:00"
    assert row.id.startswith("PD-20260825-") and row.source["client"] == "claude-memory"


@pytest.mark.parametrize("when", ["2027-01-01T00:00:00+00:00", "2020-01-01T00:00:00+00:00"])
def test_record_decision_decided_at_out_of_range_is_rejected(when: str):
    repository = InMemoryRepository()

    with pytest.raises(ToolFailure, match="decided_at"):
        _run(_tools(repository).record_decision(ALICE, _arguments(decided_at=when)))

    assert repository.rows == []


def test_record_decision_with_info_logging_enabled_does_not_crash(caplog):
    """운영은 INFO 로그를 켠다. 로깅 예약어(created 등)를 extra에 쓰면 그때만 터진다."""
    caplog.set_level(logging.DEBUG, logger="pit")
    repository = InMemoryRepository()

    result = _run(_tools(repository).record_decision(ALICE, _arguments()))

    assert result["status"] == "recorded"
    assert any("결정 기록" in record.message for record in caplog.records)


def test_record_decision_secret_in_quote_is_masked_before_storage():
    repository = InMemoryRepository()
    fake_key = "sk-ant-" + "a1B2" * 6

    result = _run(_tools(repository).record_decision(ALICE, _arguments(human_quote=f"키는 {fake_key} 로 바꿔")))

    assert fake_key not in repository.rows[0].model_dump_json()
    assert result["redacted"] == 1 and repository.rows[0].redactions == {"anthropic_key": 1}


def test_record_decision_same_payload_twice_stores_once():
    repository = InMemoryRepository()
    tools = _tools(repository)

    first = _run(tools.record_decision(ALICE, _arguments()))
    second = _run(tools.record_decision(ALICE, _arguments(situation="같은 결정을 다른 말로 다시 보냄")))

    assert len(repository.rows) == 1
    assert (first["status"], second["status"]) == ("recorded", "already_recorded")
    assert first["id"] == second["id"]


def test_record_decision_same_words_from_another_user_is_a_separate_record():
    repository = InMemoryRepository()
    tools = _tools(repository)

    _run(tools.record_decision(ALICE, _arguments()))
    _run(tools.record_decision(BOB, _arguments()))

    assert sorted(row.owner_github_id for row in repository.rows) == [1001, 2002]
    assert repository.rows[0].id != repository.rows[1].id


def test_record_decision_choice_without_verdict_is_stored_as_choice():
    repository = InMemoryRepository()
    arguments = _arguments(verdict=None, reject_kind=None, options=["A안", "B안"], chosen="B안")

    _run(_tools(repository).record_decision(ALICE, arguments))

    assert (repository.rows[0].kind, repository.rows[0].chosen) == ("choice", "B안")


@pytest.mark.parametrize(
    "overrides",
    [
        {"verdict": "maybe"},
        {"verdict": None, "reject_kind": None},
        {"verdict": "approve", "reject_kind": "stop"},
        {"human_quote": ""},
    ],
)
def test_record_decision_invalid_input_returns_tool_failure_and_stores_nothing(overrides: dict):
    repository = InMemoryRepository()

    with pytest.raises(ToolFailure, match="입력이 올바르지 않습니다"):
        _run(_tools(repository).record_decision(ALICE, _arguments(**overrides)))

    assert repository.rows == []


def test_record_decision_over_rate_limit_is_rejected():
    repository = InMemoryRepository()
    tools = _tools(repository, max_calls=2)
    for n in range(2):
        _run(tools.record_decision(ALICE, _arguments(human_quote=f"거부 {n}")))

    with pytest.raises(ToolFailure, match="너무 잦습니다"):
        _run(tools.record_decision(ALICE, _arguments(human_quote="거부 3")))

    assert len(repository.rows) == 2
    assert _run(tools.record_decision(BOB, _arguments()))["status"] == "recorded"


def test_rate_limiter_window_expiry_allows_again():
    clock = FakeClock(step_seconds=40.0)
    limiter = RateLimiter(clock, max_calls=1, window_seconds=60.0)

    assert [limiter.allow(1), limiter.allow(1), limiter.allow(1)] == [True, False, True]


def _confirm(repository: InMemoryRepository) -> None:
    repository.rows[-1] = repository.rows[-1].model_copy(update={"status": "confirmed"})


def test_search_my_decisions_never_returns_other_users_rows():
    repository = InMemoryRepository()
    tools = _tools(repository)
    _run(tools.record_decision(BOB, _arguments(human_quote="밥의 캐시 결정")))
    _confirm(repository)

    assert _run(tools.search_my_decisions(ALICE, "캐시")) == []
    assert len(_run(tools.search_my_decisions(BOB, "캐시"))) == 1


def test_search_my_decisions_excludes_drafts_and_discarded():
    repository = InMemoryRepository()
    tools = _tools(repository)
    _run(tools.record_decision(ALICE, _arguments(human_quote="초안 캐시")))
    _run(tools.record_decision(ALICE, _arguments(human_quote="버린 캐시")))
    repository.rows[-1] = repository.rows[-1].model_copy(update={"status": "discarded"})
    _run(tools.record_decision(ALICE, _arguments(human_quote="확정한 캐시")))
    _confirm(repository)

    found = _run(tools.search_my_decisions(ALICE, "캐시"))

    assert [item["human_quote"] for item in found] == ["확정한 캐시"]


def test_get_decision_of_another_user_is_reported_as_missing():
    repository = InMemoryRepository()
    tools = _tools(repository)
    bobs_id = _run(tools.record_decision(BOB, _arguments()))["id"]

    with pytest.raises(ToolFailure, match="그런 결정이 없습니다"):
        _run(tools.get_decision(ALICE, bobs_id))

    assert _run(tools.get_decision(BOB, bobs_id))["situation"] == "캐시 전략을 정하던 중"


# --- MCP 프로토콜을 거친 계약 테스트 (인메모리 클라이언트) -----------------


def _call(server, name: str, arguments: dict):  # noqa: ANN001, ANN202
    async def run():  # noqa: ANN202
        async with Client(server) as client:
            return await client.call_tool(name, arguments)

    return asyncio.run(run())


def test_tools_without_valid_token_are_rejected():
    server = build_server(SETTINGS, InMemoryRepository())

    with pytest.raises(ToolError, match="인증이 필요합니다"):
        _call(server, "record_decision", _arguments())


def test_record_decision_through_mcp_stores_for_the_token_owner(monkeypatch):
    repository = InMemoryRepository()
    token = SimpleNamespace(claims={"sub": "1001", "login": "alice"})
    monkeypatch.setattr(identity, "get_access_token", lambda: token)

    result = _call(build_server(SETTINGS, repository), "record_decision", _arguments())

    assert result.data["status"] == "recorded"
    assert repository.rows[0].owner_github_id == 1001


def test_record_decision_without_storage_says_nothing_was_saved(monkeypatch):
    monkeypatch.setattr(identity, "get_access_token", lambda: SimpleNamespace(claims={"sub": "1", "login": "a"}))

    with pytest.raises(ToolError, match=STORAGE_NOT_READY):
        _call(build_server(SETTINGS), "record_decision", _arguments())


def test_repository_failure_is_reported_without_leaking_details(monkeypatch):
    repository = InMemoryRepository()
    repository.fail_with = RepositoryError("connection refused to 10.0.0.5")
    monkeypatch.setattr(identity, "get_access_token", lambda: SimpleNamespace(claims={"sub": "1", "login": "a"}))

    with pytest.raises(ToolError) as error:
        _call(build_server(SETTINGS, repository), "record_decision", _arguments())

    assert "저장되지 않았습니다" in str(error.value) and "10.0.0.5" not in str(error.value)


# --- Supabase 저장소: 나가는 요청의 모양 ------------------------------------


def _supabase(handler) -> SupabaseRepository:  # noqa: ANN001
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return SupabaseRepository("https://example.test/", "service-key-placeholder", client)


def test_supabase_search_always_scopes_to_owner_and_confirmed():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    _run(_supabase(handler).search_confirmed(1001, 'x"),owner_github_id.eq.2002,(a', 5))

    params = dict(seen[0].url.params)
    assert params["owner_github_id"] == "eq.1001" and params["status"] == "eq.confirmed"
    assert "2002" in params["or"] and "eq.2002" not in params["or"].replace("owner_github_id.eq.2002", "")
    assert '"' not in params["or"] and params["or"].count("(") == 1


def test_sanitize_query_strips_filter_syntax():
    assert sanitize_query('캐시,(전략)* "x" 100%') == "캐시 전략 x 100"


def test_supabase_insert_reports_duplicate_as_not_created():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "ignore-duplicates" in request.headers["prefer"]
        assert json.loads(request.content)["origin"] == "mcp"
        return httpx.Response(201, json=[])

    repository = InMemoryRepository()
    _run(_tools(repository).record_decision(ALICE, _arguments()))

    assert _run(_supabase(handler).insert_draft(repository.rows[0])) is False


def test_supabase_http_error_becomes_repository_error():
    with pytest.raises(RepositoryError):
        _run(_supabase(lambda request: httpx.Response(500, text="boom")).ensure_account(1, "a"))


# --- 설정 -------------------------------------------------------------------


def test_load_settings_disk_storage_without_encryption_key_raises(monkeypatch, tmp_path):
    """디스크에 남는 것은 GitHub 토큰이다. 암호화 키 없이 켤 수 없다."""
    monkeypatch.setenv("PITHUB_GITHUB_CLIENT_ID", "placeholder-id")
    monkeypatch.setenv("PITHUB_GITHUB_CLIENT_SECRET", "placeholder-secret")
    monkeypatch.setenv(ENV_OAUTH_STORAGE_DIR, str(tmp_path))
    monkeypatch.delenv("PITHUB_OAUTH_STORAGE_KEY", raising=False)

    with pytest.raises(SettingsError, match="PITHUB_OAUTH_STORAGE_KEY"):
        load_settings()
