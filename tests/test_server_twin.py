"""트윈에게 묻기 (G6) — 가짜 저장소"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("fastmcp", reason="서버 extra가 설치된 환경에서만 실행")

from pit.server.identity import Caller  # noqa: E402
from pit.server.ratelimit import RateLimiter  # noqa: E402
from pit.server.records import StoredDecision  # noqa: E402
from pit.server.tools import DecisionTools  # noqa: E402
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



# --- JEV 판정기 (선택, 팀 동의) ----------------------------------------------------


def _jev(status: int = 200, choice: str = "approve", confidence: float = 0.93):  # noqa: ANN202
    import httpx

    from pit.server.jev import JevJudge

    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen.append(json.loads(request.content))
        body = {"answers": {"verdict": {"type": "choice", "choice": choice, "confidence": confidence,
                                         "probabilities": {choice: confidence}}}}  # fmt: skip
        return httpx.Response(status, json=body)

    return JevJudge("test-key", httpx.AsyncClient(transport=httpx.MockTransport(handler))), seen


def test_knn_answers_and_jev_only_shadows_for_consenting_teams_without_names():
    """답은 kNN, JEV는 그림자 예측만 기록한다 — 이름은 보내지 않는다 (2026-09-24 결정)"""
    rows = [_decision(i, "평가를 무작위 분할로 한다", "reject") for i in range(3)]
    repository = _repository(rows)
    repository.consent = {TEAM}
    jev, seen = _jev(choice="approve", confidence=0.93)
    service = TwinService(repository, lambda: NOW, jev)

    answer = asyncio.run(service.ask(ALICE, "bob", "평가를 무작위 분할로", "평가"))
    asyncio.run(service.shadow_now(1, rows, "평가", "평가를 무작위 분할로"))

    assert (answer["judge"], answer["prediction"]) == ("knn", "reject")
    assert repository.consult_rows[0] == {"prediction": "reject", "judge": "knn", "shadow_judge": "jev", "shadow_prediction": "approve"}
    assert "bob" not in str(seen[-1]) and "alice" not in str(seen[-1])


def test_without_consent_jev_shadow_is_never_called():
    rows = [_decision(i, "평가를 무작위 분할로 한다", "reject") for i in range(3)]
    repository = _repository(rows)
    jev, seen = _jev()
    service = TwinService(repository, lambda: NOW, jev)

    asyncio.run(service.ask(ALICE, "bob", "평가를 무작위 분할로", "평가"))
    asyncio.run(service.shadow_now(1, rows, "평가", "평가를 무작위 분할로"))

    assert seen == [] and "shadow_judge" not in repository.consult_rows[0]


def test_jev_shadow_failure_leaves_the_answer_alone():
    rows = [_decision(i, "평가를 무작위 분할로 한다", "reject") for i in range(3)]
    repository = _repository(rows)
    repository.consent = {TEAM}
    jev, _ = _jev(status=529)
    service = TwinService(repository, lambda: NOW, jev)

    answer = asyncio.run(service.ask(ALICE, "bob", "평가를 무작위 분할로", "평가"))
    asyncio.run(service.shadow_now(1, rows, "평가", "평가를 무작위 분할로"))

    assert answer["prediction"] == "reject" and "shadow_judge" not in repository.consult_rows[0]


def test_jev_response_with_unknown_choice_is_rejected():
    from pit.server.jev import JevError, parse_response

    with pytest.raises(JevError):
        parse_response({"answers": {"verdict": {"choice": "maybe", "confidence": 1.0}}})



def test_asking_the_twin_too_often_is_refused():
    from pit.server.ratelimit import RateLimiter
    from tests.fakes import FakeClock

    repository = _repository([_decision(1, "캐시를 쓴다", "reject")])
    service = TwinService(repository, lambda: NOW, None, RateLimiter(FakeClock(), max_calls=2))

    asyncio.run(service.ask(ALICE, "bob", "캐시"))
    asyncio.run(service.ask(ALICE, "bob", "캐시"))
    with pytest.raises(TwinUnavailable, match="너무 자주"):
        asyncio.run(service.ask(ALICE, "bob", "캐시"))


def test_server_instructions_tell_the_model_when_to_ask_a_twin():
    from pit.server.app import SERVER_INSTRUCTIONS

    assert "ask_twin" in SERVER_INSTRUCTIONS and "never their" in SERVER_INSTRUCTIONS



# --- 그래프 B: 트윈의 근거는 그래프가 먼저 --------------------------------------------


def _attach(repository: InMemoryRepository, decision_id: str, kind: str, name: str) -> None:
    from pit.server.graph import normalize_node_name

    repository.nodes = getattr(repository, "nodes", {})
    key = (TEAM, None, kind, normalize_node_name(name))
    repository.nodes.setdefault(key, (f"N{len(repository.nodes) + 1}", name))
    repository.decision_nodes = getattr(repository, "decision_nodes", set()) | {(decision_id, repository.nodes[key][0])}


def test_twin_takes_evidence_from_the_topic_even_when_the_words_differ():
    """질문이 주제를 가리키면, 글자가 달라도 그 주제에 매달린 판단이 근거다 — 글자만 비슷한 다른 판단은 아니다"""
    rows = [
        _decision(1, "데이터를 시간 순으로 나눈다", "approve"),
        _decision(2, "섞어서 나누는 방식은 쓰지 않는다", "approve"),
        _decision(3, "평가 대시보드 색을 바꾼다", "reject"),
        _decision(4, "평가 대시보드 글꼴을 바꾼다", "reject"),
    ]
    repository = _repository(rows)
    for decision_id in ("PD-1", "PD-2"):
        _attach(repository, decision_id, "topic", "평가 분할")
    _attach(repository, "PD-3", "topic", "대시보드")

    answer = asyncio.run(TwinService(repository, lambda: NOW).ask(ALICE, "bob", "평가 분할을 시간 순으로", "평가", ["평가 분할"]))

    assert (answer["basis"], answer["topics"]) == ("graph", ["평가 분할"])
    assert {e["id"] for e in answer["evidence"]} == {"PD-1", "PD-2"}


def test_topic_named_in_the_question_is_found_without_about_and_topics_beat_projects():
    rows = [_decision(1, "캐시를 쓴다", "reject"), _decision(2, "캐시를 안 쓴다", "approve")]
    repository = _repository(rows)
    _attach(repository, "PD-1", "project", "borch")
    _attach(repository, "PD-2", "project", "borch")
    _attach(repository, "PD-1", "topic", "캐시 전략")

    answer = asyncio.run(TwinService(repository, lambda: NOW).ask(ALICE, "bob", "borch 의 캐시 전략을 바꾸자"))

    assert answer["topics"] == ["캐시 전략"] and [e["id"] for e in answer["evidence"]] == ["PD-1"]


def test_linked_decision_joins_the_evidence_and_no_graph_falls_back_to_text():
    rows = [_decision(1, "시계열 예측으로 간다", "approve"), _decision(2, "평가는 시간 분할", "approve"), _decision(3, "무관한 결정", "reject")]
    repository = _repository(rows)
    _attach(repository, "PD-2", "topic", "평가 분할")
    repository.links = {("PD-2", "PD-1", "depends_on", "confirmed")}

    linked = asyncio.run(TwinService(repository, lambda: NOW).ask(ALICE, "bob", "평가 분할 바꾸자"))
    plain = asyncio.run(TwinService(repository, lambda: NOW).ask(ALICE, "bob", "전혀 다른 이야기"))

    assert {e["id"] for e in linked["evidence"]} == {"PD-1", "PD-2"} and linked["basis"] == "graph"
    assert plain["basis"] == "text" and "topics" not in plain


def test_twin_questions_notice_tells_owner_only_when_a_question_waits():
    repository = _repository([_decision(1, "캐시를 쓴다", "reject"), _decision(2, "캐시를 쓴다 둘", "approve")])
    tools = DecisionTools(repository, RateLimiter(lambda: 0.0), lambda: NOW)
    bob = Caller(github_id=2002, github_login="bob", team_slug="pilab")
    before = asyncio.run(tools.twin_questions_notice(bob))

    _ask(repository, "로그인 화면을 바꾼다")

    assert before == {} and asyncio.run(tools.twin_questions_notice(bob)) == {"twin_questions_waiting": 1}
    assert asyncio.run(tools.twin_questions_notice(ALICE)) == {}
