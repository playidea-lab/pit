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
        updated = db.execute("update public.decisions set status = 'confirmed'").rowcount
        deleted = db.execute("delete from public.decisions").rowcount

    assert (updated, deleted) == (0, 0)
    assert ids(db, "select id from public.decisions") == ["PD-alice"]


def test_decisions_recorded_before_first_web_login_attach_to_the_account(db):
    """claude.ai 커넥터부터 연결한 사람이 나중에 웹에 로그인하면 그동안의 기록이 보인다"""
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-before-login")

    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")

    with acting_as(db, "authenticated", alice):
        assert ids(db, "select id from public.decisions") == ["PD-before-login"]


def test_public_and_friends_paths_do_not_exist(db):
    """회사 제품(D-0010): 판단이 회사 밖으로 나가는 경로가 스키마에 없다"""
    missing = db.execute(
        "select count(*) from pg_class where relname in ('public_decisions', 'friends_decisions', 'follows')"
    ).fetchone()[0]
    assert missing == 0
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-x")
    for scope in ("public", "friends"):
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute("update public.decisions set visibility = %s where id = 'PD-x'", (scope,))


def test_anon_cannot_read_tables_directly(db):
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-x", status="confirmed")

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


def test_owner_can_confirm_and_really_delete_a_private_decision(db):
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-mine")
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")

    with acting_as(db, "authenticated", alice):
        db.execute("update public.decisions set status = 'confirmed' where id = 'PD-mine'")
        db.execute("delete from public.decisions where id = 'PD-mine'")

    assert ids(db, "select id from public.decisions") == []


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


# --- 범위: team · 자문 기록 -----------------------------------------


def _team(conn, slug: str, owner_github_id: int) -> str:  # noqa: ANN001
    conn.execute(
        "insert into public.accounts (github_id, github_login) values (%s, %s) on conflict do nothing",
        (owner_github_id, f"user{owner_github_id}"),
    )
    row = conn.execute(
        "insert into public.teams (slug, name, created_by) values (%s, %s, %s) returning id", (slug, slug, owner_github_id)
    ).fetchone()
    conn.execute(
        "insert into public.team_members (team_id, github_id, role, accepted_at) values (%s, %s, 'owner', now())",
        (row[0], owner_github_id),
    )
    return str(row[0])


def _join(conn, team: str, github_id: int) -> None:  # noqa: ANN001
    """수락까지 끝난 구성원 (service_role 경로)"""
    conn.execute(
        "insert into public.accounts (github_id, github_login) values (%s, %s) on conflict do nothing",
        (github_id, f"user{github_id}"),
    )
    conn.execute(
        "insert into public.team_members (team_id, github_id, accepted_at) values (%s, %s, now())", (team, github_id)
    )


def _share(conn, decision_id: str, visibility: str, team_id: str | None = None) -> None:  # noqa: ANN001
    conn.execute(
        "update public.decisions set status = 'confirmed', visibility = %s, team_id = %s where id = %s",
        (visibility, team_id, decision_id),
    )


def test_team_scoped_decision_visible_to_members_only(db):
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-team")
    record_via_mcp(db, BOB_GITHUB_ID, "bob", "PD-bob-private")
    carol_id = 3003
    db.execute("insert into public.accounts (github_id, github_login) values (%s, 'carol')", (carol_id,))
    team = _team(db, "pilab", ALICE_GITHUB_ID)
    _join(db, team, BOB_GITHUB_ID)
    _share(db, "PD-team", "team", team)
    bob = sign_in_with_github(db, BOB_GITHUB_ID, "bob")
    carol = sign_in_with_github(db, carol_id, "carol")

    with acting_as(db, "authenticated", bob):
        assert ids(db, "select id from public.decisions") == ["PD-bob-private"]
        assert ids(db, "select id from public.team_decisions") == ["PD-team"]
        # 팀원이 보는 열에 출처·가림 내역은 없다
        columns = {column.name for column in db.execute("select * from public.team_decisions limit 0").description}
        assert not columns & {"source", "redactions", "status", "visibility"}
    with acting_as(db, "authenticated", carol):
        assert ids(db, "select id from public.team_decisions") == []


def test_team_decision_still_visible_after_owner_leaves_but_private_never_was(db):
    """퇴사는 마지막 push다: team 범위로 확정한 것은 팀에 남고, private은 애초에 팀이 본 적 없다"""
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-team")
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-private")
    team = _team(db, "pilab", BOB_GITHUB_ID)
    _join(db, team, ALICE_GITHUB_ID)
    _share(db, "PD-team", "team", team)
    bob = sign_in_with_github(db, BOB_GITHUB_ID, "bob")
    db.execute("delete from public.team_members where team_id = %s and github_id = %s", (team, ALICE_GITHUB_ID))

    with acting_as(db, "authenticated", bob):
        assert ids(db, "select id from public.team_decisions") == ["PD-team"]


def test_draft_with_team_scope_is_not_shown_to_team_until_confirmed(db):
    """범위는 의도다. 확정 전에는 팀도 보지 못한다."""
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-draft")
    team = _team(db, "pilab", BOB_GITHUB_ID)
    _join(db, team, ALICE_GITHUB_ID)
    db.execute("update public.decisions set visibility = 'team', team_id = %s where id = 'PD-draft'", (team,))
    bob = sign_in_with_github(db, BOB_GITHUB_ID, "bob")

    with acting_as(db, "authenticated", bob):
        assert ids(db, "select id from public.team_decisions") == []


def test_consult_log_readable_by_twin_owner_only(db):
    db.execute("insert into public.accounts (github_id, github_login) values (%s, 'alice'), (%s, 'bob')", (ALICE_GITHUB_ID, BOB_GITHUB_ID))
    db.execute(
        "insert into public.consult_log (asker_github_id, twin_github_id, question) values (%s, %s, '이 제안 승인할까?')",
        (BOB_GITHUB_ID, ALICE_GITHUB_ID),
    )
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")
    bob = sign_in_with_github(db, BOB_GITHUB_ID, "bob")

    with acting_as(db, "authenticated", alice):
        assert db.execute("select count(*) from public.consult_log").fetchone()[0] == 1
    with acting_as(db, "authenticated", bob):
        assert db.execute("select count(*) from public.consult_log").fetchone()[0] == 0


def test_project_default_cannot_point_at_a_team_one_is_not_in(db):
    team = _team(db, "others", BOB_GITHUB_ID)
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")

    with pytest.raises(psycopg.errors.InsufficientPrivilege), acting_as(db, "authenticated", alice):
        db.execute(
            "insert into public.project_defaults (github_id, project, visibility, team_id) values (%s, 'pit', 'team', %s)",
            (ALICE_GITHUB_ID, team),
        )


def test_citations_readable_by_owner_only_and_trgm_index_exists(db):
    db.execute("insert into public.accounts (github_id, github_login) values (%s, 'alice'), (%s, 'bob')", (ALICE_GITHUB_ID, BOB_GITHUB_ID))
    db.execute(
        "insert into public.citations (owner_github_id, query, returned_ids) values (%s, '캐시', '{PD-1}')", (ALICE_GITHUB_ID,)
    )
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")
    bob = sign_in_with_github(db, BOB_GITHUB_ID, "bob")

    with acting_as(db, "authenticated", alice):
        assert db.execute("select count(*) from public.citations").fetchone()[0] == 1
    with acting_as(db, "authenticated", bob):
        assert db.execute("select count(*) from public.citations").fetchone()[0] == 0
    assert db.execute("select count(*) from pg_indexes where indexname = 'decisions_proposal_trgm'").fetchone()[0] == 1


# --- 팀 운용: 초대 · 수락 · 탈퇴 (D-0008) -------------------------------------


def test_create_team_makes_caller_an_accepted_owner(db):
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")

    with acting_as(db, "authenticated", alice):
        team = db.execute("select public.create_team('pilab', 'PI Lab')").fetchone()[0]
        row = db.execute("select role, accepted_at is not null from public.team_members where team_id = %s", (team,)).fetchone()
        assert row == ("owner", True)
        assert ids(db, "select slug from public.teams") == ["pilab"]


def test_authenticated_user_cannot_insert_teams_or_members_directly(db):
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")

    with pytest.raises(psycopg.errors.InsufficientPrivilege), acting_as(db, "authenticated", alice):
        db.execute("insert into public.teams (slug, name, created_by) values ('x', 'x', %s)", (ALICE_GITHUB_ID,))
    with pytest.raises(psycopg.errors.InsufficientPrivilege), acting_as(db, "authenticated", alice):
        db.execute("insert into public.team_members (team_id, github_id) values (gen_random_uuid(), %s)", (ALICE_GITHUB_ID,))


def test_invite_is_visible_to_invitee_and_only_they_can_accept(db):
    """초대는 소유자가 보내고, 수락은 본인만. 수락 전에는 팀 결정이 보이지 않는다."""
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-team")
    team = _team(db, "pilab", ALICE_GITHUB_ID)
    _share(db, "PD-team", "team", team)
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")
    bob = sign_in_with_github(db, BOB_GITHUB_ID, "bob")
    carol = sign_in_with_github(db, 3003, "carol")

    with acting_as(db, "authenticated", alice):
        db.execute("select public.invite_to_team(%s, 'bob')", (team,))
    with acting_as(db, "authenticated", bob):
        assert ids(db, "select slug from public.teams") == ["pilab"]
        assert ids(db, "select github_login from public.accounts order by 1") == ["alice", "bob"]
        assert ids(db, "select id from public.team_decisions") == []
    with acting_as(db, "authenticated", carol):
        assert ids(db, "select slug from public.teams") == []
        accepted_by_stranger = db.execute("update public.team_members set accepted_at = now()").rowcount
    assert accepted_by_stranger == 0

    with acting_as(db, "authenticated", bob):
        assert db.execute("update public.team_members set accepted_at = now()").rowcount == 1
        assert ids(db, "select id from public.team_decisions") == ["PD-team"]


def test_only_owner_can_invite_and_unknown_login_is_refused(db):
    team = _team(db, "pilab", ALICE_GITHUB_ID)
    _join(db, team, BOB_GITHUB_ID)
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")
    bob = sign_in_with_github(db, BOB_GITHUB_ID, "bob")

    with pytest.raises(psycopg.errors.InsufficientPrivilege), acting_as(db, "authenticated", bob):
        db.execute("select public.invite_to_team(%s, 'alice')", (team,))
    with pytest.raises(psycopg.errors.NoDataFound), acting_as(db, "authenticated", alice):
        db.execute("select public.invite_to_team(%s, 'nobody')", (team,))


def test_member_can_leave_and_owner_can_remove_but_member_cannot_remove_others(db):
    team = _team(db, "pilab", ALICE_GITHUB_ID)
    _join(db, team, BOB_GITHUB_ID)
    _join(db, team, 3003)
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")
    bob = sign_in_with_github(db, BOB_GITHUB_ID, "bob")

    with acting_as(db, "authenticated", bob):
        assert db.execute("delete from public.team_members where github_id = 3003").rowcount == 0
        assert db.execute("delete from public.team_members where github_id = %s", (BOB_GITHUB_ID,)).rowcount == 1
    with acting_as(db, "authenticated", alice):
        assert db.execute("delete from public.team_members where github_id = 3003").rowcount == 1


def test_team_survives_its_creator_deleting_their_account(db):
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-alice-team")
    team = _team(db, "pilab", ALICE_GITHUB_ID)
    _join(db, team, BOB_GITHUB_ID)
    _share(db, "PD-alice-team", "team", team)
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")
    bob = sign_in_with_github(db, BOB_GITHUB_ID, "bob")

    with acting_as(db, "authenticated", alice):
        db.execute("select public.delete_my_account()")

    assert ids(db, "select slug from public.teams") == ["pilab"]
    with acting_as(db, "authenticated", bob):
        # 팀에 보이게 된 판단은 회사의 기록이다 — 작성자가 계정을 지워도 남고, 떠난 사람으로 표시된다 (D-0010)
        assert db.execute("select id, github_login, departed from public.team_decisions").fetchall() == [
            ("PD-alice-team", "alice", True)
        ]


# --- 가입 요청: 팀 주소로 온 비구성원은 승인 대기열에 (D-0008 보완) -----------------


def _request_join(conn, team: str, github_id: int) -> None:  # noqa: ANN001
    """MCP 서버(service_role)가 팀 주소로 인증한 비구성원을 대기열에 넣는 경로"""
    conn.execute(
        "insert into public.accounts (github_id, github_login) values (%s, %s) on conflict do nothing",
        (github_id, f"user{github_id}"),
    )
    conn.execute(
        "insert into public.team_members (team_id, github_id, invited_by) values (%s, %s, %s) on conflict do nothing",
        (team, github_id, github_id),
    )


def _record_pending(conn, github_id: int, decision_id: str, slug: str) -> None:  # noqa: ANN001
    record_via_mcp(conn, github_id, f"user{github_id}", decision_id)
    conn.execute(
        "update public.decisions set source = %s where id = %s",
        (psycopg.types.json.Jsonb({"client": "claude-code", "team": slug, "team_status": "pending"}), decision_id),
    )


def test_join_request_cannot_be_approved_by_the_requester_but_owner_can(db):
    team = _team(db, "pilab", ALICE_GITHUB_ID)
    _request_join(db, team, BOB_GITHUB_ID)
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")
    bob = sign_in_with_github(db, BOB_GITHUB_ID, "bob")

    with acting_as(db, "authenticated", bob):
        assert db.execute("update public.team_members set accepted_at = now()").rowcount == 0
    with acting_as(db, "authenticated", alice):
        assert db.execute("update public.team_members set accepted_at = now() where github_id = %s", (BOB_GITHUB_ID,)).rowcount == 1


def test_owner_cannot_accept_an_invitation_on_behalf_of_the_invitee(db):
    team = _team(db, "pilab", ALICE_GITHUB_ID)
    db.execute("insert into public.accounts (github_id, github_login) values (%s, 'bob')", (BOB_GITHUB_ID,))
    db.execute(
        "insert into public.team_members (team_id, github_id, invited_by) values (%s, %s, %s)", (team, BOB_GITHUB_ID, ALICE_GITHUB_ID)
    )
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")

    with acting_as(db, "authenticated", alice):
        assert db.execute("update public.team_members set accepted_at = now() where github_id = %s", (BOB_GITHUB_ID,)).rowcount == 0


def test_approval_moves_pending_team_address_records_to_team_scope(db):
    """승인 전에 팀 주소로 기록한 결정은 private 이었다가 승인 순간 팀 범위가 된다 — 다른 private 은 그대로"""
    team = _team(db, "pilab", ALICE_GITHUB_ID)
    _request_join(db, team, BOB_GITHUB_ID)
    _record_pending(db, BOB_GITHUB_ID, "PD-pending", "pilab")
    _record_pending(db, BOB_GITHUB_ID, "PD-other-team", "others")
    record_via_mcp(db, BOB_GITHUB_ID, "bob", "PD-plain-private")
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")

    with acting_as(db, "authenticated", alice):
        db.execute("update public.team_members set accepted_at = now() where github_id = %s", (BOB_GITHUB_ID,))

    rows = db.execute("select id, visibility, team_id::text, source ->> 'team_status' from public.decisions order by id").fetchall()
    assert rows == [
        ("PD-other-team", "private", None, "pending"),
        ("PD-pending", "team", team, None),
        ("PD-plain-private", "private", None, None),
    ]


# --- 회사 제품: 3일 뒤 자동 공유 · 사후 거부 · 소유 이전 (D-0010) ----------------


def _team_draft(conn, owner: int, decision_id: str, team: str, age_days: int = 0) -> None:  # noqa: ANN001
    """팀 주소로 기록된 초안. age_days 만큼 과거에 만들어진 것으로 한다."""
    record_via_mcp(conn, owner, f"user{owner}", decision_id)
    conn.execute(
        "update public.decisions set visibility = 'team', team_id = %s, created_at = now() - make_interval(days => %s) "
        "where id = %s",
        (team, age_days, decision_id),
    )


def test_team_draft_is_shared_automatically_after_three_days_unless_withdrawn_or_discarded(db):
    team = _team(db, "pilab", BOB_GITHUB_ID)
    _join(db, team, ALICE_GITHUB_ID)
    _team_draft(db, ALICE_GITHUB_ID, "PD-fresh", team, age_days=1)
    _team_draft(db, ALICE_GITHUB_ID, "PD-old", team, age_days=4)
    _team_draft(db, ALICE_GITHUB_ID, "PD-withdrawn", team, age_days=1)
    _team_draft(db, ALICE_GITHUB_ID, "PD-discarded", team, age_days=1)
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")
    bob = sign_in_with_github(db, BOB_GITHUB_ID, "bob")

    with acting_as(db, "authenticated", alice):
        db.execute("update public.decisions set visibility = 'private', team_id = null where id = 'PD-withdrawn'")
        db.execute("update public.decisions set status = 'discarded' where id = 'PD-discarded'")
    db.execute("update public.decisions set created_at = now() - interval '5 days'")

    with acting_as(db, "authenticated", bob):
        rows = db.execute("select id, verified from public.team_decisions order by id").fetchall()
    assert rows == [("PD-fresh", False), ("PD-old", False)]


def test_shared_decision_cannot_be_withdrawn_discarded_or_deleted_by_its_author(db):
    team = _team(db, "pilab", BOB_GITHUB_ID)
    _join(db, team, ALICE_GITHUB_ID)
    _team_draft(db, ALICE_GITHUB_ID, "PD-shared", team, age_days=4)
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")

    for change in ("visibility = 'private', team_id = null", "status = 'discarded'"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege), acting_as(db, "authenticated", alice):
            db.execute(f"update public.decisions set {change} where id = 'PD-shared'")
    with acting_as(db, "authenticated", alice):
        assert db.execute("delete from public.decisions where id = 'PD-shared'").rowcount == 0
        # 확인과 글 고치기는 된다
        assert db.execute("update public.decisions set status = 'confirmed', verdict = 'modify' where id = 'PD-shared'").rowcount == 1


def test_delete_my_account_keeps_shared_team_records_and_removes_the_rest(db):
    team = _team(db, "pilab", BOB_GITHUB_ID)
    _join(db, team, ALICE_GITHUB_ID)
    _team_draft(db, ALICE_GITHUB_ID, "PD-shared", team, age_days=4)
    _team_draft(db, ALICE_GITHUB_ID, "PD-still-draft", team, age_days=1)
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-private")
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")

    with acting_as(db, "authenticated", alice):
        db.execute("select public.delete_my_account()")

    assert ids(db, "select id from public.decisions") == ["PD-shared"]
    assert db.execute("select deleted_at is not null from public.accounts where github_id = %s", (ALICE_GITHUB_ID,)).fetchone()[0]
    assert db.execute("select count(*) from public.profiles where github_id = %s", (ALICE_GITHUB_ID,)).fetchone()[0] == 0
    assert db.execute("select count(*) from public.team_members where github_id = %s", (ALICE_GITHUB_ID,)).fetchone()[0] == 0


def test_only_team_owner_can_erase_a_member_persona(db):
    team = _team(db, "pilab", BOB_GITHUB_ID)
    _join(db, team, ALICE_GITHUB_ID)
    _join(db, team, 3003)
    _team_draft(db, ALICE_GITHUB_ID, "PD-alice", team, age_days=4)
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")
    bob = sign_in_with_github(db, BOB_GITHUB_ID, "bob")
    carol = sign_in_with_github(db, 3003, "carol")
    with acting_as(db, "authenticated", alice):
        db.execute("select public.delete_my_account()")

    with pytest.raises(psycopg.errors.InsufficientPrivilege), acting_as(db, "authenticated", carol):
        db.execute("select public.erase_member_persona(%s, %s)", (team, ALICE_GITHUB_ID))
    with acting_as(db, "authenticated", bob):
        erased = db.execute("select public.erase_member_persona(%s, %s)", (team, ALICE_GITHUB_ID)).fetchone()[0]

    assert erased == 1
    assert ids(db, "select id from public.decisions") == []
    assert db.execute("select count(*) from public.accounts where github_id = %s", (ALICE_GITHUB_ID,)).fetchone()[0] == 0



# --- G0: 건너간 판단 ------------------------------------------------------------


def test_transfers_visible_to_owner_and_reader_and_team_sees_only_the_count(db):
    team = _team(db, "pilab", ALICE_GITHUB_ID)
    _join(db, team, BOB_GITHUB_ID)
    _join(db, team, 3003)
    _team_draft(db, ALICE_GITHUB_ID, "PD-a", team, age_days=4)
    db.execute(
        "insert into public.transfers (decision_id, owner_github_id, reader_github_id, team_id, via) values ('PD-a', %s, %s, %s, 'get')",
        (ALICE_GITHUB_ID, BOB_GITHUB_ID, team),
    )
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")
    bob = sign_in_with_github(db, BOB_GITHUB_ID, "bob")
    carol = sign_in_with_github(db, 3003, "carol")
    outsider = sign_in_with_github(db, 4004, "dave")

    for person in (alice, bob):
        with acting_as(db, "authenticated", person):
            assert db.execute("select count(*) from public.transfers").fetchone()[0] == 1
    with acting_as(db, "authenticated", carol):
        assert db.execute("select count(*) from public.transfers").fetchone()[0] == 0
        assert db.execute("select public.team_transfer_count(%s, now() - interval '7 days')", (team,)).fetchone()[0] == 1
    with acting_as(db, "authenticated", outsider):
        assert db.execute("select public.team_transfer_count(%s, now() - interval '7 days')", (team,)).fetchone()[0] == 0
    with pytest.raises(psycopg.errors.InsufficientPrivilege), acting_as(db, "authenticated", bob):
        db.execute(
            "insert into public.transfers (decision_id, owner_github_id, reader_github_id, via) values ('PD-a', %s, %s, 'get')",
            (ALICE_GITHUB_ID, BOB_GITHUB_ID),
        )


# --- G1: 판단 그래프 스키마 --------------------------------------------------------


def _node(conn, name: str, team: str | None = None, owner: int | None = None, kind: str = "topic") -> str:  # noqa: ANN001
    return str(conn.execute(
        "insert into public.nodes (team_id, owner_github_id, kind, name, norm_name) values (%s, %s, %s, %s, lower(%s)) returning id",
        (team, owner, kind, name, name),
    ).fetchone()[0])


def _about(conn, decision_id: str, node_id: str) -> None:  # noqa: ANN001
    conn.execute("insert into public.decision_nodes (decision_id, node_id) values (%s, %s)", (decision_id, node_id))


def test_graph_nodes_and_edges_follow_the_visibility_of_their_decision(db):
    """팀원은 팀에 보인 결정에 매달린 노드·엣지만 본다. 3일 유예 중인 결정의 주제 이름도 새지 않는다."""
    team = _team(db, "pilab", ALICE_GITHUB_ID)
    _join(db, team, BOB_GITHUB_ID)
    _team_draft(db, ALICE_GITHUB_ID, "PD-shared", team, age_days=4)
    _team_draft(db, ALICE_GITHUB_ID, "PD-fresh", team, age_days=1)
    shared_topic = _node(db, "평가 분할", team=team)
    secret_topic = _node(db, "인수 협상", team=team)
    _about(db, "PD-shared", shared_topic)
    _about(db, "PD-fresh", secret_topic)
    db.execute("insert into public.decision_links (from_decision, to_decision, relation) values ('PD-fresh', 'PD-shared', 'depends_on')")
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")
    bob = sign_in_with_github(db, BOB_GITHUB_ID, "bob")
    outsider = sign_in_with_github(db, 3003, "carol")

    with acting_as(db, "authenticated", alice):
        assert sorted(ids(db, "select name from public.nodes")) == ["인수 협상", "평가 분할"]
        assert db.execute("select count(*) from public.decision_links").fetchone()[0] == 1
    with acting_as(db, "authenticated", bob):
        assert ids(db, "select name from public.nodes") == ["평가 분할"]
        assert ids(db, "select decision_id from public.decision_nodes") == ["PD-shared"]
        assert db.execute("select count(*) from public.decision_links").fetchone()[0] == 0
    with acting_as(db, "authenticated", outsider):
        assert db.execute("select count(*) from public.nodes").fetchone()[0] == 0


def test_web_users_cannot_write_graph_rows(db):
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-a")
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")

    with pytest.raises(psycopg.errors.InsufficientPrivilege), acting_as(db, "authenticated", alice):
        db.execute("insert into public.nodes (owner_github_id, kind, name, norm_name) values (%s, 'topic', 'x', 'x')", (ALICE_GITHUB_ID,))


def test_supersedes_array_is_mirrored_into_links_and_nodes_are_unique_per_namespace(db):
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-old")
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-new")
    db.execute("update public.decisions set supersedes = '{PD-old,PD-missing}' where id = 'PD-new'")
    assert db.execute("select from_decision, to_decision from public.decision_links").fetchall() == [("PD-new", "PD-old")]
    db.execute("update public.decisions set supersedes = '{}' where id = 'PD-new'")
    assert db.execute("select count(*) from public.decision_links").fetchone()[0] == 0

    _node(db, "평가 분할", owner=ALICE_GITHUB_ID)
    with pytest.raises(psycopg.errors.UniqueViolation), db.transaction():
        _node(db, "평가 분할", owner=ALICE_GITHUB_ID)
    # 이름 공간이 다르면 같은 이름도 따로 존재한다
    db.execute("insert into public.accounts (github_id, github_login) values (%s, 'bob') on conflict do nothing", (BOB_GITHUB_ID,))
    _node(db, "평가 분할", owner=BOB_GITHUB_ID)
    assert db.execute("select count(*) from public.nodes").fetchone()[0] == 2


# --- G5: 충돌 후보 처리 ------------------------------------------------------------


def _conflict(conn, a: str, b: str) -> int:  # noqa: ANN001
    return int(conn.execute(
        "insert into public.decision_links (from_decision, to_decision, relation, status) values (%s, %s, 'conflicts_with', 'proposed') returning id",
        (a, b),
    ).fetchone()[0])


def test_conflict_can_be_resolved_only_by_an_owner_of_either_end(db):
    team = _team(db, "pilab", ALICE_GITHUB_ID)
    _join(db, team, BOB_GITHUB_ID)
    _team_draft(db, ALICE_GITHUB_ID, "PD-a", team, age_days=4)
    _team_draft(db, BOB_GITHUB_ID, "PD-b", team, age_days=4)
    confirm_me, dismiss_me = _conflict(db, "PD-b", "PD-a"), _conflict(db, "PD-a", "PD-b")
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")
    carol = sign_in_with_github(db, 3003, "carol")

    with pytest.raises(psycopg.errors.InsufficientPrivilege), acting_as(db, "authenticated", carol):
        db.execute("select public.resolve_conflict(%s, 'confirm')", (confirm_me,))
    with acting_as(db, "authenticated", alice):
        db.execute("select public.resolve_conflict(%s, 'confirm')", (confirm_me,))
        db.execute("select public.resolve_conflict(%s, 'dismiss')", (dismiss_me,))

    assert db.execute("select id, status from public.decision_links").fetchall() == [(confirm_me, "confirmed")]


def test_supersede_turns_the_conflict_into_an_overturn_by_the_newer_decisions_author(db):
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-old")
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-new")
    db.execute("update public.decisions set decided_at = now() - interval '10 days' where id = 'PD-old'")
    link = _conflict(db, "PD-old", "PD-new")
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")

    with acting_as(db, "authenticated", alice):
        db.execute("select public.resolve_conflict(%s, 'supersede')", (link,))

    assert db.execute("select supersedes from public.decisions where id = 'PD-new'").fetchone()[0] == ["PD-old"]
    assert db.execute("select from_decision, to_decision, relation from public.decision_links").fetchall() == [
        ("PD-new", "PD-old", "supersedes")
    ]


def test_supersede_is_refused_to_the_author_of_the_older_decision(db):
    team = _team(db, "pilab", ALICE_GITHUB_ID)
    _join(db, team, BOB_GITHUB_ID)
    _team_draft(db, ALICE_GITHUB_ID, "PD-old", team, age_days=10)
    _team_draft(db, BOB_GITHUB_ID, "PD-new", team, age_days=4)
    db.execute("update public.decisions set decided_at = now() - interval '10 days' where id = 'PD-old'")
    link = _conflict(db, "PD-old", "PD-new")
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")

    with pytest.raises(psycopg.errors.InsufficientPrivilege), acting_as(db, "authenticated", alice):
        db.execute("select public.resolve_conflict(%s, 'supersede')", (link,))


# --- G3: 이름 맞추기 --------------------------------------------------------------


def test_similar_team_nodes_are_merge_candidates_and_merging_moves_edges_and_keeps_an_alias(db):
    team = _team(db, "pilab", ALICE_GITHUB_ID)
    _join(db, team, BOB_GITHUB_ID)
    for decision_id in ("PD-1", "PD-2", "PD-3"):
        _team_draft(db, ALICE_GITHUB_ID, decision_id, team, age_days=4)
    big = _node(db, "평가 데이터 분할", team=team)
    small = _node(db, "평가 데이터 분할법", team=team)
    other = _node(db, "로그인 화면", team=team)
    for decision_id, node in (("PD-1", big), ("PD-2", big), ("PD-3", small), ("PD-3", other)):
        _about(db, decision_id, node)
    bob = sign_in_with_github(db, BOB_GITHUB_ID, "bob")
    outsider = sign_in_with_github(db, 3003, "carol")

    with acting_as(db, "authenticated", outsider):
        assert db.execute("select count(*) from public.node_merge_candidates()").fetchone()[0] == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction():
            db.execute("select public.merge_nodes(%s, %s)", (big, small))
    with acting_as(db, "authenticated", bob):
        rows = db.execute("select keep_name, drop_name from public.node_merge_candidates()").fetchall()
        assert rows == [("평가 데이터 분할", "평가 데이터 분할법")]
        db.execute("select public.merge_nodes(%s, %s)", (big, small))
        assert db.execute("select count(*) from public.node_merge_candidates()").fetchone()[0] == 0

    assert sorted(ids(db, f"select decision_id from public.decision_nodes where node_id = '{big}'")) == ["PD-1", "PD-2", "PD-3"]
    assert db.execute("select aliases from public.nodes where id = %s", (big,)).fetchone()[0] == ["평가 데이터 분할법"]
    assert db.execute("select merged_into::text, merged_by from public.nodes where id = %s", (small,)).fetchone() == (big, BOB_GITHUB_ID)


def test_dismissed_pair_is_not_asked_again_and_other_namespaces_never_pair(db):
    team = _team(db, "pilab", ALICE_GITHUB_ID)
    record_via_mcp(db, ALICE_GITHUB_ID, "alice", "PD-p")
    _team_draft(db, ALICE_GITHUB_ID, "PD-t", team, age_days=4)
    personal = _node(db, "캐시 전략", owner=ALICE_GITHUB_ID)
    team_a = _node(db, "캐시 전략", team=team)
    team_b = _node(db, "캐시 전략들", team=team)
    _about(db, "PD-p", personal)
    _about(db, "PD-t", team_a)
    _about(db, "PD-t", team_b)
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")

    with acting_as(db, "authenticated", alice):
        pairs = db.execute("select keep_id::text, drop_id::text from public.node_merge_candidates()").fetchall()
        assert len(pairs) == 1 and personal not in pairs[0]
        db.execute("select public.dismiss_node_merge(%s, %s)", (team_b, team_a))
        assert db.execute("select count(*) from public.node_merge_candidates()").fetchone()[0] == 0
        with pytest.raises(psycopg.errors.InvalidParameterValue), db.transaction():
            db.execute("select public.merge_nodes(%s, %s)", (team_a, personal))


# --- G6: 트윈 질문 ---------------------------------------------------------------


def test_twin_question_is_seen_by_asker_and_owner_and_answered_only_by_the_owner(db):
    team = _team(db, "pilab", ALICE_GITHUB_ID)
    _join(db, team, BOB_GITHUB_ID)
    question = db.execute(
        "insert into public.twin_questions (asker_github_id, twin_github_id, team_id, proposal) "
        "values (%s, %s, %s, '평가를 무작위 분할로') returning id",
        (ALICE_GITHUB_ID, BOB_GITHUB_ID, team),
    ).fetchone()[0]
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")
    bob = sign_in_with_github(db, BOB_GITHUB_ID, "bob")
    carol = sign_in_with_github(db, 3003, "carol")

    with acting_as(db, "authenticated", carol):
        assert db.execute("select count(*) from public.twin_questions").fetchone()[0] == 0
    with pytest.raises(psycopg.errors.InsufficientPrivilege), acting_as(db, "authenticated", alice):
        db.execute("select public.answer_twin_question(%s, 'reject', '아니')", (question,))
    with acting_as(db, "authenticated", bob):
        decision_id = db.execute("select public.answer_twin_question(%s, 'reject', '아니, 시간 분할')", (question,)).fetchone()[0]
    with pytest.raises(psycopg.errors.InvalidParameterValue), acting_as(db, "authenticated", bob):
        db.execute("select public.answer_twin_question(%s, 'approve', '다시')", (question,))

    row = db.execute("select owner_github_id, status, visibility, team_id::text, verdict from public.decisions where id = %s", (decision_id,)).fetchone()
    assert row == (BOB_GITHUB_ID, "confirmed", "team", team, "reject")
    with acting_as(db, "authenticated", alice):
        assert ids(db, "select id from public.team_decisions") == [decision_id]
        assert db.execute("select answer_decision_id from public.twin_questions").fetchone()[0] == decision_id


def test_only_team_owner_can_consent_to_the_external_judge(db):
    team = _team(db, "pilab", ALICE_GITHUB_ID)
    _join(db, team, BOB_GITHUB_ID)
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")
    bob = sign_in_with_github(db, BOB_GITHUB_ID, "bob")

    with pytest.raises(psycopg.errors.InsufficientPrivilege), acting_as(db, "authenticated", bob):
        db.execute("select public.set_team_judge_consent(%s, true)", (team,))
    with acting_as(db, "authenticated", alice):
        db.execute("select public.set_team_judge_consent(%s, true)", (team,))
    assert db.execute("select external_judge_consent_by from public.teams").fetchone()[0] == ALICE_GITHUB_ID
    with acting_as(db, "authenticated", alice):
        db.execute("select public.set_team_judge_consent(%s, false)", (team,))
    assert db.execute("select external_judge_consent_at from public.teams").fetchone()[0] is None


def test_only_the_twin_owner_can_rate_a_twin_answer(db):
    db.execute("insert into public.accounts (github_id, github_login) values (%s, 'alice'), (%s, 'bob')", (ALICE_GITHUB_ID, BOB_GITHUB_ID))
    consult = db.execute(
        "insert into public.consult_log (asker_github_id, twin_github_id, question, prediction, judge, shadow_prediction) "
        "values (%s, %s, 'q', 'reject', 'knn', 'approve') returning id",
        (ALICE_GITHUB_ID, BOB_GITHUB_ID),
    ).fetchone()[0]
    alice = sign_in_with_github(db, ALICE_GITHUB_ID, "alice")
    bob = sign_in_with_github(db, BOB_GITHUB_ID, "bob")

    with pytest.raises(psycopg.errors.InsufficientPrivilege), acting_as(db, "authenticated", alice):
        db.execute("select public.rate_twin_answer(%s, 'reject')", (consult,))
    with acting_as(db, "authenticated", bob):
        db.execute("select public.rate_twin_answer(%s, 'reject')", (consult,))
    assert db.execute("select owner_verdict, rated_at is not null from public.consult_log").fetchone() == ("reject", True)
