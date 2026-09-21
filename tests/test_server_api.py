"""로컬 pit 용 HTTP API 테스트 — 가짜 저장소, 인메모리 ASGI"""

from datetime import datetime, timezone

import httpx
import pytest

pytest.importorskip("fastmcp", reason="서버 extra가 설치된 환경에서만 실행")

from pit.server.app import build_server  # noqa: E402
from pit.server.records import StoredDecision  # noqa: E402
from pit.server.settings import ServerSettings  # noqa: E402
from pit.server.tokens import generate_token, hash_token, looks_like_token  # noqa: E402
from tests.fakes import InMemoryRepository  # noqa: E402

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
SETTINGS = ServerSettings(
    github_client_id="placeholder-id", github_client_secret="placeholder-secret",
    base_url="http://127.0.0.1:8000", host="127.0.0.1", port=8000,
)  # fmt: skip


def _local_decision(local_id: str, owner: int = 9999) -> dict:
    return StoredDecision(
        id=local_id, owner_github_id=owner, kind="verdict", verdict="reject", situation="s", proposal="p",
        human_quote="q", decided_at=NOW, dedupe_key=local_id, status="draft", visibility="public",
    ).model_dump(mode="json")  # fmt: skip


@pytest.fixture
def api():
    repository = InMemoryRepository()
    token = generate_token()
    repository.tokens[hash_token(token)] = (1001, "alice")
    server = build_server(SETTINGS, repository)
    transport = httpx.ASGITransport(app=server.http_app())
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    return client, repository, token


def _run(coroutine):  # noqa: ANN001, ANN202
    import asyncio

    return asyncio.run(coroutine)


def test_token_format_is_recognizable_and_hash_is_stable():
    token = generate_token()
    assert looks_like_token(token) and not looks_like_token("sk-ant-" + "x" * 40)
    assert hash_token(token) == hash_token(token) and hash_token(token) != token


def test_me_without_token_is_unauthorized(api):
    client, _, _ = api

    response = _run(client.get("/api/v1/me"))

    assert response.status_code == 401


def test_me_with_unknown_token_is_unauthorized(api):
    client, _, _ = api

    response = _run(client.get("/api/v1/me", headers={"Authorization": f"Bearer {generate_token()}"}))

    assert response.status_code == 401


def test_me_with_valid_token_returns_owner(api):
    client, _, token = api

    response = _run(client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}))

    assert response.json() == {"github_id": 1001, "github_login": "alice"}


def test_push_rewrites_owner_origin_and_id_from_token(api):
    """클라이언트가 보낸 소유자·id·공개 여부는 무시되고 토큰 주인 것이 된다"""
    client, repository, token = api
    body = {"decisions": [_local_decision("PD-20260901-local001", owner=2002)]}

    response = _run(client.post("/api/v1/decisions", json=body, headers={"Authorization": f"Bearer {token}"}))

    (row,) = repository.rows
    assert response.json() == {"upserted": 1}
    assert (row.owner_github_id, row.origin, row.status, row.visibility) == (1001, "local_extract", "confirmed", "private")
    assert row.id != "PD-20260901-local001" and row.source["local_id"] == "PD-20260901-local001"


def test_push_cannot_overwrite_another_users_row_with_same_id(api):
    client, repository, token = api
    bobs = StoredDecision.model_validate(_local_decision("PD-shared", owner=2002))
    repository.rows.append(bobs)

    _run(client.post("/api/v1/decisions", json={"decisions": [_local_decision("PD-shared")]},
                     headers={"Authorization": f"Bearer {token}"}))  # fmt: skip

    assert any(r.id == "PD-shared" and r.owner_github_id == 2002 for r in repository.rows)
    assert len(repository.rows) == 2


def test_push_same_local_id_twice_updates_not_duplicates(api):
    client, repository, token = api
    headers = {"Authorization": f"Bearer {token}"}
    body = {"decisions": [_local_decision("PD-x")]}

    _run(client.post("/api/v1/decisions", json=body, headers=headers))
    _run(client.post("/api/v1/decisions", json=body, headers=headers))

    assert len(repository.rows) == 1


def test_push_invalid_body_is_bad_request(api):
    client, _, token = api

    response = _run(client.post("/api/v1/decisions", json={"decisions": [{"id": "x"}]},
                                headers={"Authorization": f"Bearer {token}"}))  # fmt: skip

    assert response.status_code == 400


def test_pull_returns_only_the_token_owners_rows_with_since_filter(api):
    client, repository, token = api
    repository.rows.append(StoredDecision.model_validate({**_local_decision("PD-old", owner=1001), "decided_at": "2026-09-01T00:00:00+00:00"}))
    repository.rows.append(StoredDecision.model_validate(_local_decision("PD-new", owner=1001)))
    repository.rows.append(StoredDecision.model_validate(_local_decision("PD-bob", owner=2002)))
    headers = {"Authorization": f"Bearer {token}"}

    everything = _run(client.get("/api/v1/decisions", headers=headers)).json()["decisions"]
    recent = _run(client.get("/api/v1/decisions", params={"since": "2026-09-15T00:00:00+00:00"}, headers=headers)).json()["decisions"]

    assert sorted(d["id"] for d in everything) == ["PD-new", "PD-old"]
    assert [d["id"] for d in recent] == ["PD-new"]


def test_pull_bad_since_is_bad_request(api):
    client, _, token = api

    response = _run(client.get("/api/v1/decisions", params={"since": "yesterday"}, headers={"Authorization": f"Bearer {token}"}))

    assert response.status_code == 400
