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
    assert result == {"id": row.id, "status": "recorded", "redacted": 0, "visibility": "private"}
    assert (row.owner_github_id, row.status, row.visibility, row.origin) == (1001, "draft", "private", "mcp")
    assert (row.kind, row.verdict, row.reject_kind) == ("verdict", "reject", "redirect")
    assert row.source == {"client": "claude.ai"}
    assert repository.accounts == {1001: "alice"}


def test_record_decision_project_default_sets_scope_else_private():
    repository = InMemoryRepository()
    repository.project_defaults[(1001, "pit")] = ("team", "team-uuid")
    tools = _tools(repository)

    _run(tools.record_decision(ALICE, _arguments(project="pit")))
    _run(tools.record_decision(ALICE, _arguments(project="other", proposal="다른 프로젝트의 제안", human_quote="다른 프로젝트")))
    _run(tools.record_decision(ALICE, _arguments(proposal="프로젝트 없는 제안", human_quote="프로젝트 없음")))

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
        _run(tools.record_decision(ALICE, _arguments(proposal=f"제안 {n}", human_quote=f"거부 {n}")))

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


def test_search_my_decisions_includes_unverified_but_not_discarded():
    """기록은 곧바로 검색된다. 버린 것만 빠지고, 확인 여부는 결과에 표시된다."""
    repository = InMemoryRepository()
    tools = _tools(repository)
    _run(tools.record_decision(ALICE, _arguments(proposal="캐시 1", human_quote="미확인 캐시")))
    _run(tools.record_decision(ALICE, _arguments(proposal="캐시 2", human_quote="버린 캐시")))
    repository.rows[-1] = repository.rows[-1].model_copy(update={"status": "discarded"})
    _run(tools.record_decision(ALICE, _arguments(proposal="캐시 3", human_quote="확인한 캐시")))
    _confirm(repository)

    found = _run(tools.search_my_decisions(ALICE, "캐시"))

    assert sorted((item["human_quote"], item["verified"]) for item in found) == [("미확인 캐시", False), ("확인한 캐시", True)]


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


def test_supabase_search_always_scopes_to_owner_and_excludes_discarded():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    _run(_supabase(handler).search_recorded(1001, 'x"),owner_github_id.eq.2002,(a', 5))

    params = dict(seen[0].url.params)
    assert params["owner_github_id"] == "eq.1001" and params["status"] == "neq.discarded"
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


# --- 생애주기 (D-0007 1단계) ------------------------------------------------


def test_record_decision_same_proposal_with_different_verdict_is_a_new_record():
    """같은 제안이라도 판정이 바뀌면 접지 않는다 — 그것이 곧 결정의 변화다"""
    repository = InMemoryRepository()
    tools = _tools(repository)
    _run(tools.record_decision(ALICE, _arguments(project="pit", verdict="reject", human_quote="처음엔 거부")))

    result = _run(tools.record_decision(ALICE, _arguments(project="pit", verdict="approve", reject_kind=None, human_quote="다시 보니 승인")))

    assert result["status"] == "recorded" and len(repository.rows) == 2


def test_record_decision_same_proposal_within_days_is_folded_into_repeat():
    repository = InMemoryRepository()
    tools = _tools(repository)
    first = _run(tools.record_decision(ALICE, _arguments(project="pit", human_quote="처음 거부")))

    second = _run(tools.record_decision(ALICE, _arguments(project="pit", proposal="매번  전체를 다시 읽는다", human_quote="또 거부")))

    assert second == {"id": first["id"], "status": "repeated", "redacted": 0}
    assert len(repository.rows) == 1 and repository.rows[0].repeat_count == 2


def test_record_decision_supersedes_must_belong_to_caller():
    repository = InMemoryRepository()
    tools = _tools(repository)
    bobs = _run(tools.record_decision(BOB, _arguments()))["id"]

    with pytest.raises(ToolFailure, match="supersedes"):
        _run(tools.record_decision(ALICE, _arguments(human_quote="뒤집음", supersedes=[bobs])))

    mine = _run(tools.record_decision(ALICE, _arguments(proposal="원래 제안", human_quote="원래 결정")))["id"]
    newer = _run(tools.record_decision(ALICE, _arguments(proposal="다른 제안", human_quote="뒤집음", supersedes=[mine])))
    assert next(r for r in repository.rows if r.id == newer["id"]).supersedes == [mine]


def test_search_ranks_principle_and_verified_first_and_records_the_search():
    repository = InMemoryRepository()
    tools = _tools(repository)
    _run(tools.record_decision(ALICE, _arguments(proposal="캐시 A", human_quote="a")))
    _run(tools.record_decision(ALICE, _arguments(proposal="캐시 B", human_quote="b", tags=["principle"])))
    _run(tools.record_decision(ALICE, _arguments(proposal="캐시 C", human_quote="c")))
    _confirm(repository)

    found = _run(tools.search_my_decisions(ALICE, "캐시", client="claude-code"))

    assert [f["proposal"] for f in found][:2] == ["캐시 B", "캐시 C"]
    assert found[0]["principle"] is True and found[1]["verified"] is True
    assert repository.searches[0][1] == "캐시" and len(repository.searches[0][2]) == 3


def test_get_decision_counts_as_a_citation():
    repository = InMemoryRepository()
    tools = _tools(repository)
    decision_id = _run(tools.record_decision(ALICE, _arguments()))["id"]

    _run(tools.get_decision(ALICE, decision_id))
    _run(tools.get_decision(ALICE, decision_id))

    assert repository.rows[0].cited_count == 2


def test_search_summary_is_bounded():
    repository = InMemoryRepository()
    tools = _tools(repository)
    _run(tools.record_decision(ALICE, _arguments(proposal="캐시 " + "가" * 500, human_quote="나" * 500)))

    (item,) = _run(tools.search_my_decisions(ALICE, "캐시"))

    assert len(item["proposal"]) <= 140 and len(item["human_quote"]) <= 140


# --- 팀 커넥터 · 팀 범위 검색 (D-0008) ------------------------------------------

TEAM_ID = "11111111-1111-1111-1111-111111111111"
ALICE_IN_PILAB = Caller(github_id=1001, github_login="alice", team_slug="pilab")
BOB_IN_PILAB = Caller(github_id=2002, github_login="bob", team_slug="pilab")


def _team_repository() -> InMemoryRepository:
    repository = InMemoryRepository()
    repository.teams = {"pilab": TEAM_ID}
    repository.memberships = {1001: [(TEAM_ID, "pilab")], 2002: [(TEAM_ID, "pilab")]}
    return repository


def test_record_decision_through_team_address_is_team_scoped_draft():
    """팀 저장소의 커넥터로 들어온 기록은 아무것도 고르지 않아도 그 팀의 것이다 — 단 확정 전엔 초안"""
    repository = _team_repository()
    tools = _tools(repository)

    result = _run(tools.record_decision(ALICE_IN_PILAB, _arguments(project="anything")))

    stored = repository.rows[0]
    assert result["visibility"] == "team"
    assert (stored.visibility, stored.team_id, stored.status, stored.source["team"]) == ("team", TEAM_ID, "draft", "pilab")


def test_record_decision_through_team_address_by_non_member_queues_a_join_request_and_keeps_it_private():
    """거부하지 않는다: 가입 요청을 남기고, 기록은 승인 때까지 본인만 보는 private 로 둔다"""
    repository = _team_repository()
    tools = _tools(repository)
    stranger = Caller(github_id=3003, github_login="carol", team_slug="pilab")

    result = _run(tools.record_decision(stranger, _arguments()))
    _run(tools.record_decision(stranger, _arguments(proposal="두 번째")))

    stored = repository.rows[0]
    assert (stored.visibility, stored.team_id, stored.source["team"], stored.source["team_status"]) == ("private", None, "pilab", "pending")
    assert result["visibility"] == "private" and "가입 요청" in str(result["note"])
    assert repository.join_requests == {(TEAM_ID, 3003)}
    assert repository.accounts[3003] == "carol"


def test_record_decision_through_unknown_team_address_is_refused_and_stores_nothing():
    repository = _team_repository()
    tools = _tools(repository)

    with pytest.raises(ToolFailure, match="팀 'ghost'이 없습니다"):
        _run(tools.record_decision(Caller(github_id=1001, github_login="alice", team_slug="ghost"), _arguments()))

    assert repository.rows == [] and repository.join_requests == set()


def test_member_record_through_team_address_carries_no_pending_note():
    repository = _team_repository()
    result = _run(_tools(repository).record_decision(ALICE_IN_PILAB, _arguments()))

    assert "가입 요청" not in str(result.get("note")) and "team_status" not in repository.rows[0].source


def test_team_address_beats_project_default():
    repository = _team_repository()
    repository.project_defaults[(1001, "pit")] = ("private", None)
    tools = _tools(repository)

    _run(tools.record_decision(ALICE_IN_PILAB, _arguments(project="pit")))

    assert (repository.rows[0].visibility, repository.rows[0].team_id) == ("team", TEAM_ID)


def test_team_search_returns_teammates_confirmed_team_decisions_with_author():
    """팀원의 확정된 팀 결정은 `by` 와 함께 나오고, 초안·비공개는 절대 나오지 않는다"""
    repository = _team_repository()
    tools = _tools(repository)
    _run(tools.record_decision(BOB_IN_PILAB, _arguments(proposal="캐시 A", human_quote="밥의 확정 팀 결정")))
    _run(tools.record_decision(BOB_IN_PILAB, _arguments(proposal="캐시 B", human_quote="밥의 초안 팀 결정")))
    _run(tools.record_decision(BOB, _arguments(proposal="캐시 C", human_quote="밥의 확정 비공개 결정")))
    _run(tools.record_decision(ALICE, _arguments(proposal="캐시 D", human_quote="앨리스 자기 초안")))
    repository.rows[0] = repository.rows[0].model_copy(update={"status": "confirmed"})
    repository.rows[2] = repository.rows[2].model_copy(update={"status": "confirmed"})

    found = _run(tools.search_my_decisions(ALICE_IN_PILAB, "캐시"))

    assert sorted((item["human_quote"], item.get("by"), item.get("team")) for item in found) == [
        ("밥의 확정 팀 결정", "bob", "pilab"),
        ("앨리스 자기 초안", None, None),
    ]


def test_search_scope_mine_excludes_team_even_through_team_address():
    repository = _team_repository()
    tools = _tools(repository)
    _run(tools.record_decision(BOB_IN_PILAB, _arguments(human_quote="밥의 팀 결정")))
    _confirm(repository)

    assert _run(tools.search_my_decisions(ALICE_IN_PILAB, "캐시", scope="mine")) == []
    assert len(_run(tools.search_my_decisions(ALICE, "캐시", scope="team"))) == 1
    assert len(_run(tools.search_my_decisions(ALICE, "캐시", scope="team:pilab"))) == 1


@pytest.mark.parametrize("scope", ["team:others", "everything"])
def test_search_unknown_scope_or_foreign_team_is_refused(scope: str):
    tools = _tools(_team_repository())

    with pytest.raises(ToolFailure):
        _run(tools.search_my_decisions(ALICE, "캐시", scope=scope))


def test_get_decision_of_teammate_is_readable_only_when_confirmed_team_scoped():
    repository = _team_repository()
    tools = _tools(repository)
    team_id = _run(tools.record_decision(BOB_IN_PILAB, _arguments(proposal="팀 것")))["id"]
    private_id = _run(tools.record_decision(BOB, _arguments(proposal="비공개 것")))["id"]

    with pytest.raises(ToolFailure, match="그런 결정이 없습니다"):
        _run(tools.get_decision(ALICE, team_id))  # 아직 초안
    repository.rows = [r.model_copy(update={"status": "confirmed"}) for r in repository.rows]
    detail = _run(tools.get_decision(ALICE, team_id))
    assert (detail["by"], detail["team"], detail["proposal"]) == ("bob", "pilab", "팀 것")
    assert next(r for r in repository.rows if r.id == team_id).cited_count == 1
    with pytest.raises(ToolFailure, match="그런 결정이 없습니다"):
        _run(tools.get_decision(ALICE, private_id))


def test_team_principle_ranks_above_own_recent_record():
    repository = _team_repository()
    tools = _tools(repository)
    _run(tools.record_decision(BOB_IN_PILAB, _arguments(proposal="평가는 시간 분할로만", tags=["principle"], human_quote="팀 원칙")))
    _confirm(repository)
    _run(tools.record_decision(ALICE, _arguments(proposal="평가 방법 임시", human_quote="내 최근 것")))

    found = _run(tools.search_my_decisions(ALICE, "평가", scope="team"))

    assert [item["human_quote"] for item in found] == ["팀 원칙", "내 최근 것"]


# --- 팀 커넥터 주소 (HTTP 경로) ---------------------------------------------------


def _scope_seen_by(app_path: str) -> dict:
    from pit.server.routing import TeamConnectorMiddleware

    seen: dict = {}

    async def inner(scope, receive, send):  # noqa: ANN001, ANN202
        seen.update(scope)

    scope = {"type": "http", "path": app_path, "raw_path": app_path.encode(), "state": {}}
    asyncio.run(TeamConnectorMiddleware(inner)(scope, lambda: None, lambda _: None))
    return seen


def test_team_path_is_routed_to_mcp_with_team_in_state():
    seen = _scope_seen_by("/t/pilab/mcp")

    assert (seen["path"], seen["raw_path"], seen["state"]["pithub_team"]) == ("/mcp", b"/mcp", "pilab")


@pytest.mark.parametrize("path", ["/mcp", "/t/PILAB/mcp", "/t/pilab/other", "/t/p/mcp", "/api/v1/me"])
def test_other_paths_pass_through_untouched(path: str):
    seen = _scope_seen_by(path)

    assert seen["path"] == path
    assert "pithub_team" not in seen["state"]


def test_team_address_reaches_the_mcp_endpoint_and_requires_auth():
    """팀 주소도 인증 없이는 401 — 같은 엔드포인트, 같은 문지기"""
    from pit.server.app import HTTP_MIDDLEWARE

    app = build_server(SETTINGS, InMemoryRepository()).http_app(middleware=HTTP_MIDDLEWARE)
    transport = httpx.ASGITransport(app=app)

    async def probe(path: str) -> int:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return (await client.post(path, json={})).status_code

    assert asyncio.run(probe("/t/pilab/mcp")) == asyncio.run(probe("/mcp")) == 401


def test_current_team_slug_reads_path_state_then_query(monkeypatch):
    from types import SimpleNamespace as NS

    monkeypatch.setattr(identity, "get_http_request", lambda: NS(scope={"state": {"pithub_team": "pilab"}}, query_params={}))
    assert identity.current_team_slug() == "pilab"
    monkeypatch.setattr(identity, "get_http_request", lambda: NS(scope={"state": {}}, query_params={"team": "q-team"}))
    assert identity.current_team_slug() == "q-team"
    monkeypatch.setattr(identity, "get_http_request", lambda: NS(scope={}, query_params={}))
    assert identity.current_team_slug() is None


def test_protected_resource_is_the_whole_origin_so_team_addresses_pass_client_checks():
    """MCP 클라이언트는 광고된 resource 가 접속 주소의 접두사일 때만 받아 준다 — /mcp 도 /t/<slug>/mcp 도"""
    from pit.server.app import HTTP_MIDDLEWARE

    app = build_server(SETTINGS, InMemoryRepository()).http_app(middleware=HTTP_MIDDLEWARE)
    transport = httpx.ASGITransport(app=app)

    async def probe() -> tuple[str, dict]:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            challenge = (await client.post("/t/pilab/mcp", json={})).headers["www-authenticate"]
            metadata = (await client.get("/.well-known/oauth-protected-resource")).json()
            return challenge, metadata

    challenge, metadata = asyncio.run(probe())

    assert 'resource_metadata="http://127.0.0.1:8000/.well-known/oauth-protected-resource"' in challenge
    assert metadata["resource"].rstrip("/") == "http://127.0.0.1:8000"


# --- GitHub 토큰 검증 캐시 ------------------------------------------------------


class _CountingVerifier:
    required_scopes = ["read:user"]

    def __init__(self, valid: set[str]) -> None:
        self.valid = valid
        self.calls = 0

    async def verify_token(self, token: str):  # noqa: ANN201
        from fastmcp.server.auth import AccessToken

        self.calls += 1
        return AccessToken(token=token, client_id="1", scopes=["read:user"]) if token in self.valid else None


def test_token_verification_is_cached_within_ttl_and_refreshed_after():
    from pit.server.tokencache import CachedTokenVerifier

    now = [0.0]
    inner = _CountingVerifier({"good"})
    cached = CachedTokenVerifier(inner, clock=lambda: now[0], ttl_seconds=300)

    for _ in range(5):
        assert asyncio.run(cached.verify_token("good")) is not None
    assert inner.calls == 1
    now[0] = 301
    asyncio.run(cached.verify_token("good"))
    assert inner.calls == 2


def test_token_verification_failures_are_not_cached_and_cache_is_bounded():
    from pit.server.tokencache import CachedTokenVerifier

    inner = _CountingVerifier({"t0", "t1", "t2"})
    cached = CachedTokenVerifier(inner, clock=lambda: 0.0, max_entries=2)

    assert asyncio.run(cached.verify_token("bad")) is None
    assert asyncio.run(cached.verify_token("bad")) is None
    assert inner.calls == 2
    for token in ("t0", "t1", "t2"):
        asyncio.run(cached.verify_token(token))
    asyncio.run(cached.verify_token("t0"))  # 가장 오래된 것은 밀려났다
    assert inner.calls == 6


def test_build_server_wraps_github_verifier_with_cache():
    from pit.server.app import _build_auth
    from pit.server.tokencache import CachedTokenVerifier

    assert isinstance(_build_auth(SETTINGS)._token_validator, CachedTokenVerifier)



# --- 회사 제품: 3일 뒤 자동 공유 (D-0010) ------------------------------------------


def test_teammates_team_draft_becomes_searchable_after_grace_marked_unverified():
    """팀 주소로 기록된 초안은 3일 뒤 확인 없이도 팀에 보인다 — verified: false 로"""
    from datetime import timedelta

    repository = _team_repository()
    tools = _tools(repository)
    _run(tools.record_decision(BOB_IN_PILAB, _arguments(proposal="캐시 오래된", human_quote="밥의 오래된 초안")))
    _run(tools.record_decision(BOB_IN_PILAB, _arguments(proposal="캐시 새", human_quote="밥의 새 초안")))
    repository.rows[0] = repository.rows[0].model_copy(update={"created_at": NOW - timedelta(days=4)})

    found = _run(tools.search_my_decisions(ALICE_IN_PILAB, "캐시"))

    assert [(item["human_quote"], item["verified"], item["by"]) for item in found] == [("밥의 오래된 초안", False, "bob")]
    detail = _run(tools.get_decision(ALICE, repository.rows[0].id))
    assert detail["proposal"] == "캐시 오래된"
    with pytest.raises(ToolFailure, match="그런 결정이 없습니다"):
        _run(tools.get_decision(ALICE, repository.rows[1].id))


def test_team_record_result_tells_the_model_about_the_three_day_window():
    result = _run(_tools(_team_repository()).record_decision(ALICE_IN_PILAB, _arguments()))

    assert "3일 뒤" in str(result["note"])


def test_stored_decision_write_excludes_created_at():
    from pit.server.records import WRITE_EXCLUDE

    repository = _team_repository()
    _run(_tools(repository).record_decision(ALICE, _arguments()))

    assert "created_at" not in repository.rows[0].model_dump(mode="json", exclude=WRITE_EXCLUDE)



# --- G0: 건너간 판단 ------------------------------------------------------------


def test_reading_a_teammates_decision_records_a_transfer_but_reading_ones_own_does_not():
    repository = _team_repository()
    tools = _tools(repository)
    bobs = _run(tools.record_decision(BOB_IN_PILAB, _arguments(proposal="밥의 판단")))["id"]
    alices = _run(tools.record_decision(ALICE_IN_PILAB, _arguments(proposal="앨리스 판단")))["id"]
    repository.rows = [r.model_copy(update={"status": "confirmed"}) for r in repository.rows]

    _run(tools.get_decision(ALICE, bobs, client="claude.ai"))
    _run(tools.get_decision(ALICE, alices))

    assert repository.transfers == [(bobs, 2002, 1001, "get", "claude.ai")]


def test_failed_read_of_unshared_decision_records_no_transfer():
    repository = _team_repository()
    tools = _tools(repository)
    bobs = _run(tools.record_decision(BOB_IN_PILAB, _arguments()))["id"]  # 아직 3일 유예 안

    with pytest.raises(ToolFailure):
        _run(tools.get_decision(ALICE, bobs))

    assert getattr(repository, "transfers", []) == []
