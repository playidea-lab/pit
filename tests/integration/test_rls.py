"""pithub 접근 권한(RLS) 검증 — 실제 Postgres에서 돈다

실행:
    docker run -d --name pithub-test-db -e POSTGRES_PASSWORD=<임의값> -p 55432:5432 postgres:17
    PITHUB_TEST_DATABASE_URL=postgresql://postgres:<임의값>@127.0.0.1:55432/postgres \
        uv run pytest -m integration

Supabase 전체를 띄우지 않고, 같은 이름의 역할과 auth.uid()를 가진 최소 스텁 위에서
마이그레이션을 그대로 적용한다. 검증 대상은 정책의 논리다.
"""

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")

pytestmark = pytest.mark.integration

DATABASE_URL_ENV = "PITHUB_TEST_DATABASE_URL"
REPO_ROOT = Path(__file__).resolve().parents[2]
STUB_SQL = Path(__file__).with_name("supabase_stub.sql")
MIGRATIONS_DIR = REPO_ROOT / "pithub" / "supabase" / "migrations"

ALICE_GITHUB_ID, BOB_GITHUB_ID = 1001, 2002


@pytest.fixture(scope="module")
def database_url() -> str:
    url = os.environ.get(DATABASE_URL_ENV)
    if not url:
        pytest.skip(f"{DATABASE_URL_ENV} 가 없어 건너뜀")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(STUB_SQL.read_text(encoding="utf-8"))
        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            conn.execute(migration.read_text(encoding="utf-8"))
    return url


@pytest.fixture
def db(database_url: str) -> Iterator["psycopg.Connection"]:
    """테스트마다 트랜잭션 하나. 끝나면 되돌린다."""
    with psycopg.connect(database_url) as conn:
        yield conn
        conn.rollback()


@contextmanager
def acting_as(conn: "psycopg.Connection", role: str, user_id: uuid.UUID | None = None) -> Iterator[None]:
    """Supabase가 요청마다 하는 일: 역할을 바꾸고 JWT의 sub를 설정한다

    세이브포인트 안에서 한다. 거부가 예상되는 SQL이 실패해도 세이브포인트까지만 되돌아가므로
    바깥 트랜잭션이 살아 있고, 역할 전환도 함께 되돌려진다.
    거부를 기대할 때는 `with pytest.raises(...), acting_as(...)` 순서로 써서 예외가 이 블록을 지나가게 한다.
    """
    try:
        with conn.transaction():
            conn.execute("select set_config('request.jwt.claim.sub', %s, true)", (str(user_id) if user_id else "",))
            conn.execute(f"set local role {role}")
            yield
    finally:
        conn.execute("reset role")


def sign_in_with_github(conn: "psycopg.Connection", github_id: int, login: str) -> uuid.UUID:
    """웹에 GitHub로 처음 로그인했을 때 인증 서버가 하는 일"""
    user_id = uuid.uuid4()
    conn.execute("insert into auth.users (id) values (%s)", (user_id,))
    conn.execute(
        "insert into auth.identities (user_id, provider, provider_id, identity_data) values (%s, 'github', %s, %s)",
        (user_id, str(github_id), psycopg.types.json.Jsonb({"user_name": login})),
    )
    return user_id


def record_via_mcp(
    conn: "psycopg.Connection",
    github_id: int,
    login: str,
    decision_id: str,
    status: str = "draft",
    visibility: str = "private",
) -> None:
    """MCP 서버(service_role)가 결정을 받는 경로"""
    conn.execute(
        "insert into public.accounts (github_id, github_login) values (%s, %s) on conflict do nothing",
        (github_id, login),
    )
    conn.execute(
        """
        insert into public.decisions
            (id, owner_github_id, status, visibility, origin, kind, verdict, situation, proposal,
             human_quote, decided_at, source, dedupe_key)
        values (%s, %s, %s, %s, 'mcp', 'verdict', 'reject', '상황', '제안', '아니 그거 말고', now(),
                '{"client": "claude.ai", "session": "SECRET-SESSION"}', %s)
        """,
        (decision_id, github_id, status, visibility, decision_id),
    )


def ids(conn: "psycopg.Connection", sql: str) -> list[str]:
    return [row[0] for row in conn.execute(sql).fetchall()]


def test_decisions_other_users_private_rows_are_invisible_and_untouchable(db):
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-alice")
    sign_in_with_github(db, ALICE_GITHUB_ID, "alice")
    bob = sign_in_with_github(db, BOB_GITHUB_ID, "bob")

    with acting_as(db, "authenticated", bob):
        assert ids(db, "select id from public.decisions") == []
        updated = db.execute("update public.decisions set visibility = 'public', status = 'confirmed'").rowcount
        deleted = db.execute("delete from public.decisions").rowcount

    assert (updated, deleted) == (0, 0)
    assert ids(db, "select id from public.decisions") == ["PD-alice"]


def test_decisions_recorded_before_first_web_login_attach_to_the_account(db):
    """claude.ai 커넥터부터 연결한 사람이 나중에 웹에 로그인하면 그동안의 기록이 보인다"""
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-before-login")

    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")

    with acting_as(db, "authenticated", alice):
        assert ids(db, "select id from public.decisions") == ["PD-before-login"]


def test_public_view_shows_only_confirmed_public_rows_without_private_columns(db):
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-draft")
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-confirmed-private", status="confirmed")
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-published", status="confirmed", visibility="public")

    with acting_as(db, "anon"):
        rows = db.execute("select * from public.public_decisions").fetchall()
        columns = {column.name for column in db.execute("select * from public.public_decisions limit 0").description}

    assert [row[0] for row in rows] == ["PD-published"]
    assert columns.isdisjoint({"source", "extractor", "review", "redactions", "dedupe_key", "owner_github_id"})
    assert "SECRET-SESSION" not in str(rows)


def test_anon_cannot_read_tables_directly(db):
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-x", status="confirmed", visibility="public")

    with pytest.raises(psycopg.errors.InsufficientPrivilege), acting_as(db, "anon"):
        db.execute("select * from public.decisions")


def test_authenticated_user_cannot_insert_decisions(db):
    """결정을 만드는 것은 MCP 서버뿐이다. 웹 세션으로는 남의 이름은 물론 자기 이름으로도 못 만든다."""
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")

    with pytest.raises(psycopg.errors.InsufficientPrivilege), acting_as(db, "authenticated", alice):
        db.execute(
            "insert into public.decisions (id, owner_github_id, origin, kind, verdict, decided_at, dedupe_key) "
            "values ('PD-forged', %s, 'mcp', 'verdict', 'approve', now(), 'k')",
            (ALICE_GITHUB_ID,),
        )


def test_owner_can_confirm_publish_and_really_delete(db):
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-mine")
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")

    with acting_as(db, "authenticated", alice):
        db.execute("update public.decisions set status = 'confirmed', visibility = 'public' where id = 'PD-mine'")
    with acting_as(db, "anon"):
        assert ids(db, "select id from public.public_decisions") == ["PD-mine"]

    with acting_as(db, "authenticated", alice):
        db.execute("delete from public.decisions where id = 'PD-mine'")

    assert ids(db, "select id from public.decisions") == []
    with acting_as(db, "anon"):
        assert ids(db, "select id from public.public_decisions") == []


def test_owner_cannot_reassign_a_decision_to_someone_else(db):
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-mine")
    record_via_mcp(db, BOB_GITHUB_ID, "bob", "PD-bob")
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")

    with pytest.raises(psycopg.errors.InsufficientPrivilege), acting_as(db, "authenticated", alice):
        db.execute("update public.decisions set owner_github_id = %s where id = 'PD-mine'", (BOB_GITHUB_ID,))


def test_owner_cannot_rewrite_provenance_of_a_decision(db):
    """출처를 고칠 수 있으면 'MCP가 기록한 것'과 '원문에서 추출한 것'의 대조가 무의미해진다"""
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-mine")
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")

    for assignment in ("origin = 'local_extract'", "source = '{}'::jsonb", "id = 'PD-renamed'", "dedupe_key = 'x'"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege), acting_as(db, "authenticated", alice):
            db.execute(f"update public.decisions set {assignment} where id = 'PD-mine'")

    with acting_as(db, "authenticated", alice):
        changed = db.execute("update public.decisions set verdict = 'modify' where id = 'PD-mine'").rowcount
    assert changed == 1


def test_draft_cannot_be_made_public(db):
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-draft")
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")

    with pytest.raises(psycopg.errors.CheckViolation), acting_as(db, "authenticated", alice):
        db.execute("update public.decisions set visibility = 'public' where id = 'PD-draft'")


def test_same_payload_recorded_twice_is_rejected_by_dedupe_key(db):
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-once")

    with pytest.raises(psycopg.errors.UniqueViolation):
        db.execute(
            "insert into public.decisions (id, owner_github_id, origin, kind, verdict, decided_at, dedupe_key) "
            "values ('PD-twice', %s, 'mcp', 'verdict', 'reject', now(), 'PD-once')",
            (ALICE_GITHUB_ID,),
        )


def test_non_github_identity_creates_no_profile(db):
    user_id = uuid.uuid4()
    db.execute("insert into auth.users (id) values (%s)", (user_id,))
    db.execute(
        "insert into auth.identities (user_id, provider, provider_id) values (%s, 'email', 'someone')", (user_id,)
    )

    assert db.execute("select count(*) from public.profiles").fetchone()[0] == 0


def test_user_metadata_cannot_be_used_to_claim_another_github_id(db):
    """사용자가 고칠 수 있는 raw_user_meta_data 는 신원 연결에 쓰이지 않는다"""
    record_via_mcp(db, BOB_GITHUB_ID, "bob", "PD-bob")
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")
    db.execute(
        "update auth.users set raw_user_meta_data = %s where id = %s",
        (psycopg.types.json.Jsonb({"provider_id": str(BOB_GITHUB_ID), "sub": str(BOB_GITHUB_ID)}), alice),
    )

    with acting_as(db, "authenticated", alice):
        assert ids(db, "select id from public.decisions") == []


def test_api_tokens_are_visible_only_to_their_owner(db):
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")
    bob = sign_in_with_github(db, BOB_GITHUB_ID, "bob")
    with acting_as(db, "authenticated", alice):
        db.execute(
            "insert into public.api_tokens (owner_github_id, name, token_hash) values (%s, 'laptop', 'hash-a')",
            (ALICE_GITHUB_ID,),
        )

    with acting_as(db, "authenticated", bob):
        assert db.execute("select count(*) from public.api_tokens").fetchone()[0] == 0
    with pytest.raises(psycopg.errors.InsufficientPrivilege), acting_as(db, "authenticated", bob):
        db.execute(
            "insert into public.api_tokens (owner_github_id, name, token_hash) values (%s, 'x', 'hash-b')",
            (ALICE_GITHUB_ID,),
        )


def test_delete_my_account_removes_everything_of_the_caller_only(db):
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-alice")
    record_via_mcp(db, BOB_GITHUB_ID, "bob", "PD-bob")
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")

    with acting_as(db, "authenticated", alice):
        db.execute("select public.delete_my_account()")

    assert ids(db, "select id from public.decisions") == ["PD-bob"]
    assert ids(db, "select github_login from public.accounts") == ["bob"]
    assert db.execute("select count(*) from public.profiles").fetchone()[0] == 0


def test_delete_my_account_anonymous_is_refused(db):
    with pytest.raises(psycopg.errors.InsufficientPrivilege), acting_as(db, "anon"):
        db.execute("select public.delete_my_account()")
