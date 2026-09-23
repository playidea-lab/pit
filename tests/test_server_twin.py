"""트윈에게 묻기 (G6) — 가짜 저장소"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("fastmcp", reason="서버 extra가 설치된 환경에서만 실행")

from pit.server.identity import Caller  # noqa: E402
from pit.server.records import StoredDecision  # noqa: E402
from pit.server.twin import TwinService, TwinUnavailable  # noqa: E402
from tests.fakes import InMemoryRepository  # noqa: E402

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
TEAM = "11111111-1111-1111-1111-111111111111"
ALICE = Caller(github_id=1001, github_login="alice")


def _decision(i: int, proposal: str, verdict: str, owner: int = 2002, **extra: object) -> StoredDecision:
    fields = {"id": f"PD-{i}", "owner_github_id": owner, "kind": "verdict", "verdict": verdict, "situation": "평가",
              "proposal": proposal, "human_quote": "q", "decided_at": NOW - timedelta(days=30 - i), "dedupe_key": f"k{i}",
              "status": "confirmed", "visibility": "team", "team_id": TEAM, "created_at": NOW - timedelta(days=30)}
    return StoredDecision(**{**fields, **extra})  # fmt: skip


def _repository(rows: list[StoredDecision]) -> InMemoryRepository:
    repository = InMemoryRepository()
    repository.accounts = {1001: "alice", 2002: "bob"}
    repository.memberships = {1001: [(TEAM, "pilab")], 2002: [(TEAM, "pilab")]}
    repository.rows = rows
    return repository


def _ask(repository: InMemoryRepository, proposal: str, login: str = "bob") -> dict:
    return asyncio.run(TwinService(repository, lambda: NOW).ask(ALICE, login, proposal, "평가"))


def test_twin_predicts_from_similar_visible_judgments_with_evidence_and_records_a_transfer():
    rows = [_decision(i, "평가를 무작위 분할로 한다", "reject") for i in range(4)]
    rows += [_decision(10 + i, "설계 문서를 먼저 쓴다", "approve") for i in range(4)]
    repository = _repository(rows)

    answer = _ask(repository, "평가를 무작위 분할로 하자")

    assert (answer["prediction"], answer["abstained"]) == ("reject", False)
    assert answer["confidence"] >= 0.6 and answer["evidence"][0]["proposal"] == "평가를 무작위 분할로 한다"
    assert repository.transfers[0][2:4] == (1001, "twin")
    assert repository.consults[0][4] is False and not getattr(repository, "twin_questions", [])


def test_twin_abstains_and_asks_the_person_when_history_does_not_decide():
    repository = _repository([_decision(1, "캐시를 쓴다", "reject"), _decision(2, "캐시를 쓴다 둘", "approve")])

    answer = _ask(repository, "로그인 화면을 바꾼다")

    assert (answer["prediction"], answer["abstained"]) == (None, True)
    assert repository.twin_questions == [(1001, 2002, TEAM, "로그인 화면을 바꾼다")]


def test_twin_never_uses_private_or_withdrawn_or_other_team_records():
    rows = [
        _decision(1, "평가를 무작위 분할로", "reject", visibility="private", team_id=None),
        _decision(2, "평가를 무작위 분할로", "reject", status="draft", created_at=NOW - timedelta(days=1)),
        _decision(3, "평가를 무작위 분할로", "reject", team_id="22222222-2222-2222-2222-222222222222"),
    ]
    answer = _ask(_repository(rows), "평가를 무작위 분할로")

    assert answer["evidence"] == [] and answer["abstained"] is True


def test_departed_twin_answers_from_the_team_graph_but_never_asks():
    rows = [_decision(i, "평가를 무작위 분할로 한다", "reject") for i in range(4)]
    repository = _repository(rows)
    repository.departed = {2002}

    assert _ask(repository, "평가를 무작위 분할로")["departed"] is True
    abstained = _ask(repository, "완전히 다른 결제 문제")
    assert abstained["abstained"] is True and not getattr(repository, "twin_questions", [])


def test_twin_refuses_unknown_login_and_oneself():
    repository = _repository([])
    with pytest.raises(TwinUnavailable):
        _ask(repository, "x", login="nobody")
    with pytest.raises(TwinUnavailable):
        _ask(repository, "x", login="alice")


def test_ask_twin_tool_is_hidden_unless_enabled():
    from pit.server.app import build_server
    from pit.server.settings import ServerSettings

    base = {"github_client_id": "i", "github_client_secret": "s", "base_url": "http://127.0.0.1:8000", "host": "127.0.0.1", "port": 8000}

    def names(enabled: bool) -> set[str]:
        server = build_server(ServerSettings(**base, twin_enabled=enabled), InMemoryRepository())
        return set(asyncio.run(server.get_tools()))

    assert "ask_twin" not in names(False)
    assert "ask_twin" in names(True)
