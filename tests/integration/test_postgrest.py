"""서버 저장소(SupabaseRepository)를 실제 PostgREST로 — 필터 문법·임베딩·중복 처리를 가짜 저장소로는 잡을 수 없다

실행 (로컬):
    docker run -d --name pithub-test-db -e POSTGRES_PASSWORD=<임의값> -p 55432:5432 postgres:17
    docker run -d --name pithub-test-rest -p 53000:3000 \\
        -e PGRST_DB_URI=postgresql://postgres:<임의값>@host.docker.internal:55432/postgres \\
        -e PGRST_DB_ANON_ROLE=anon -e PGRST_DB_SCHEMAS=public -e PGRST_JWT_SECRET=<32자 이상> \\
        postgrest/postgrest:v12.2.3
    PITHUB_TEST_DATABASE_URL=... PITHUB_TEST_POSTGREST_URL=http://127.0.0.1:53000 \\
        PITHUB_TEST_POSTGREST_JWT_SECRET=<같은 값> uv run pytest -m integration tests/integration/test_postgrest.py

운영의 service_role 키와 같은 역할의 JWT를 만들어 서버와 똑같은 요청을 보낸다.
"""

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
jwt = pytest.importorskip("jwt")
pytest.importorskip("fastmcp", reason="서버 extra가 설치된 환경에서만 실행")

from pit.server.graph import Namespace, normalize_node_name  # noqa: E402
from pit.server.identity import Caller  # noqa: E402
from pit.server.ratelimit import RateLimiter  # noqa: E402
from pit.server.records import StoredDecision  # noqa: E402
from pit.server.repository import SupabaseRepository  # noqa: E402
from pit.server.tools import DecisionTools  # noqa: E402
from pit.server.twin import TwinService  # noqa: E402

pytestmark = pytest.mark.integration

DATABASE_URL_ENV = "PITHUB_TEST_DATABASE_URL"
POSTGREST_URL_ENV = "PITHUB_TEST_POSTGREST_URL"
JWT_SECRET_ENV = "PITHUB_TEST_POSTGREST_JWT_SECRET"
REPO_ROOT = Path(__file__).resolve().parents[2]
STUB_SQL = Path(__file__).with_name("supabase_stub.sql")
MIGRATIONS_DIR = REPO_ROOT / "pithub" / "supabase" / "migrations"
TEAM = "11111111-1111-1111-1111-111111111111"
ALICE, BOB = 1001, 2002
SCHEMA_RELOAD_WAIT_SECONDS = 0.2
SCHEMA_RELOAD_TRIES = 50


def _wait_for_schema(repository: SupabaseRepository) -> None:
    """마이그레이션 직후 PostgREST 스키마 캐시가 새 테이블을 알 때까지 기다린다 (폴링)"""
    async def ready() -> bool:
        try:
            await repository._request("GET", "/transfers", params={"limit": "1"})
            return True
        except Exception:  # noqa: BLE001 — 스키마가 아직 없으면 오류가 정상이다
            return False

    for _ in range(SCHEMA_RELOAD_TRIES):
        if _run(ready()):
            return
        time.sleep(SCHEMA_RELOAD_WAIT_SECONDS)
    pytest.fail("PostgREST가 스키마를 다시 읽지 못했다")


@pytest.fixture(scope="module")
def env() -> dict[str, str]:
    values = {name: os.environ.get(name, "") for name in (DATABASE_URL_ENV, POSTGREST_URL_ENV, JWT_SECRET_ENV)}
    if not all(values.values()):
        pytest.skip("PostgREST 통합 시험 환경변수가 없어 건너뜀")
    with psycopg.connect(values[DATABASE_URL_ENV], autocommit=True) as conn:
        conn.execute(STUB_SQL.read_text(encoding="utf-8"))
        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            conn.execute(migration.read_text(encoding="utf-8"))
        conn.execute("notify pgrst, 'reload schema'")
    return values


@pytest.fixture
def db(env: dict[str, str]):  # noqa: ANN201
    """시험마다 비운 DB — PostgREST가 커밋된 데이터를 봐야 하므로 트랜잭션으로 되돌리지 않고 지운다"""
    with psycopg.connect(env[DATABASE_URL_ENV], autocommit=True) as conn:
        conn.execute("truncate public.accounts, public.teams restart identity cascade; delete from auth.users;")
        conn.execute("insert into public.accounts (github_id, github_login) values (%s, 'alice'), (%s, 'bob')", (ALICE, BOB))
        conn.execute("insert into public.teams (id, slug, name, created_by) values (%s, 'pilab', 'p', %s)", (TEAM, ALICE))
        conn.execute(
            "insert into public.team_members (team_id, github_id, role, accepted_at) values (%s, %s, 'owner', now()), (%s, %s, 'member', now())",
            (TEAM, ALICE, TEAM, BOB),
        )
        yield conn


@pytest.fixture
def repository(env: dict[str, str], db) -> SupabaseRepository:  # noqa: ANN001
    key = jwt.encode({"role": "service_role"}, env[JWT_SECRET_ENV], algorithm="HS256")
    repo = SupabaseRepository(env[POSTGREST_URL_ENV], key)
    repo._rest = env[POSTGREST_URL_ENV]  # PostgREST 단독은 /rest/v1 접두사가 없다
    _wait_for_schema(repo)
    return repo


def _decision(i: int, owner: int, proposal: str, verdict: str = "reject", **extra: object) -> StoredDecision:
    base = {"id": f"PD-{i}", "owner_github_id": owner, "kind": "verdict", "verdict": verdict, "situation": "평가",
            "proposal": proposal, "human_quote": "q", "decided_at": datetime.now(timezone.utc), "dedupe_key": f"k{i}",
            "status": "confirmed", "visibility": "team", "team_id": TEAM}
    return StoredDecision(**{**base, **extra})  # fmt: skip


# httpx 연결 풀은 만든 이벤트 루프에 묶이므로, 모듈 전체가 루프 하나를 쓴다
_LOOP = asyncio.new_event_loop()


def _run(coroutine):  # noqa: ANN001, ANN202
    return _LOOP.run_until_complete(coroutine)


def test_nodes_resolve_per_namespace_with_filter_syntax_and_aliases(repository, db):
    for d in (_decision(1, ALICE, "a"), _decision(2, BOB, "b")):
        _run(repository.insert_draft(d))
    tricky = 'Eval, Split (v2) "x"'
    team = Namespace(team_id=TEAM, owner_github_id=None)
    first = _run(repository.resolve_node(team, "topic", tricky, normalize_node_name(tricky), ALICE))
    again = _run(repository.resolve_node(team, "topic", "eval split v2 x", normalize_node_name("eval split v2 x"), BOB))
    personal = _run(repository.resolve_node(Namespace(None, ALICE), "topic", tricky, normalize_node_name(tricky), ALICE))
    db.execute("update public.nodes set aliases = '{\"평가 분할\"}' where id = %s", (first,))
    aliased = _run(repository.resolve_node(team, "topic", "평가 분할", normalize_node_name("평가 분할"), BOB))

    assert first == again == aliased and personal != first
    _run(repository.attach_nodes("PD-1", [first]))
    _run(repository.attach_nodes("PD-1", [first]))
    _run(repository.attach_nodes("PD-2", [first]))
    _run(repository.add_links("PD-2", [("PD-1", "conflicts_with", "proposed")], BOB))
    _run(repository.add_links("PD-2", [("PD-1", "conflicts_with", "proposed")], BOB))
    assert _run(repository.topics_of(["PD-1", "PD-2", "nope"])) == {"PD-1": [tricky], "PD-2": [tricky]}
    assert _run(repository.node_refs_of(["PD-1"])) == {"PD-1": [("topic", tricky)]}
    assert _run(repository.links_of("PD-1")) == [("PD-2", "PD-1", "conflicts_with", "proposed")]
    assert db.execute("select count(*) from public.decision_nodes").fetchone()[0] == 2


def test_team_search_shows_confirmed_and_old_drafts_only_and_filters_text(repository, db):
    old = datetime.now(timezone.utc) - timedelta(days=4)
    rows = [
        _decision(1, BOB, "캐시 확정"),
        _decision(2, BOB, "캐시 오래된 초안", status="draft"),
        _decision(3, BOB, "캐시 새 초안", status="draft"),
        _decision(4, BOB, "캐시 버림", status="discarded"),
        _decision(5, BOB, "다른 주제"),
    ]
    for row in rows:
        _run(repository.insert_draft(row))
    db.execute("update public.decisions set created_at = %s where id = 'PD-2'", (old,))

    found = _run(repository.search_team([TEAM], "캐시", 10))

    assert sorted(d.id for d in found) == ["PD-1", "PD-2"]


def test_graph_reads_find_nodes_across_team_and_personal_namespaces(repository, db):
    _run(repository.insert_draft(_decision(1, ALICE, "a")))
    _run(repository.insert_draft(_decision(2, BOB, "b", visibility="private", team_id=None)))
    team_node = _run(repository.resolve_node(Namespace(TEAM, None), "topic", "평가 분할", "평가 분할", ALICE))
    bob_node = _run(repository.resolve_node(Namespace(None, BOB), "topic", "평가 분할 개인", "평가 분할 개인", BOB))
    _run(repository.attach_nodes("PD-1", [team_node]))
    _run(repository.attach_nodes("PD-2", [bob_node]))

    assert len(_run(repository.find_nodes([TEAM], ALICE, "평가", 10))) == 1
    assert len(_run(repository.find_nodes([TEAM], BOB, "평가 분할", 10))) == 2
    assert sorted(_run(repository.decision_ids_on_nodes([team_node, bob_node], 10))) == ["PD-1", "PD-2"]
    assert sorted(d.id for d in _run(repository.get_many(["PD-1", "PD-2", "nope"]))) == ["PD-1", "PD-2"]


def test_record_decision_end_to_end_writes_draft_nodes_and_team_scope(repository, db):
    tools = DecisionTools(repository, RateLimiter(time.monotonic), lambda: datetime.now(timezone.utc))
    caller = Caller(github_id=ALICE, github_login="alice")

    result = _run(tools.record_decision(caller, {
        "situation": "평가 방식을 정하는 중", "proposal": "무작위 분할", "human_quote": "아니 시간 분할",
        "verdict": "reject", "project": "pit", "about": [{"name": "평가 분할"}],
    }))  # fmt: skip

    row = db.execute("select visibility, team_id::text, status, created_at is not null from public.decisions").fetchone()
    assert row == ("team", TEAM, "draft", True)
    assert result["topics"] == ["평가 분할", "pit"]
    assert db.execute("select count(*) from public.decision_nodes").fetchone()[0] == 2


def test_twin_answers_or_abstains_and_writes_consult_question_and_transfer(repository, db):
    for i in range(4):
        _run(repository.insert_draft(_decision(i, BOB, "평가를 무작위 분할로 한다")))
    twin = TwinService(repository, lambda: datetime.now(timezone.utc))
    alice = Caller(github_id=ALICE, github_login="alice")

    answered = _run(twin.ask(alice, "bob", "평가를 무작위 분할로 하자", "평가"))
    abstained = _run(twin.ask(alice, "bob", "결제 모듈을 교체한다"))

    assert (answered["prediction"], answered["abstained"], abstained["abstained"]) == ("reject", False, True)
    assert db.execute("select abstained from public.consult_log order by id").fetchall() == [(False,), (True,)]
    assert db.execute("select asker_github_id, twin_github_id, team_id::text from public.twin_questions").fetchall() == [(ALICE, BOB, TEAM)]
    assert db.execute("select via from public.transfers").fetchall() == [("twin",)]
    assert (_run(repository.pending_twin_questions(BOB)), _run(repository.pending_twin_questions(ALICE))) == (1, 0)


def test_account_lookups_membership_consent_and_projects(repository, db):
    user = "7f1c2a4e-0000-4000-8000-000000000001"
    db.execute("insert into auth.users (id) values (%s)", (user,))
    db.execute("insert into public.profiles (id, github_id) values (%s, %s)", (user, BOB))
    db.execute("update public.teams set external_judge_consent_at = now() where id = %s", (TEAM,))

    assert _run(repository.account_for_user(user)) == (BOB, "bob")
    assert _run(repository.account_for_user("7f1c2a4e-0000-4000-8000-00000000ffff")) is None
    assert _run(repository.find_account("bob")) == (BOB, False)
    assert _run(repository.member_teams(ALICE)) == [(TEAM, "pilab")]
    assert _run(repository.consenting_teams([TEAM])) == {TEAM}
    assert _run(repository.find_team("pilab")) == TEAM
    assert _run(repository.logins_of([ALICE, BOB])) == {ALICE: "alice", BOB: "bob"}
