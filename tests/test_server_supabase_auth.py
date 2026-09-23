"""Supabase 로그인(OAuth 2.1 서버) 방식 — GitHub·이메일 모두 받는다"""

import asyncio
from types import SimpleNamespace

import httpx
import pytest

pytest.importorskip("fastmcp", reason="서버 extra가 설치된 환경에서만 실행")

from pit.server import identity  # noqa: E402
from pit.server.app import HTTP_MIDDLEWARE, build_server  # noqa: E402
from pit.server.identity import NotAuthenticatedError, resolve_caller  # noqa: E402
from pit.server.settings import ServerSettings  # noqa: E402
from tests.fakes import InMemoryRepository  # noqa: E402

USER = "7f1c2a4e-0000-4000-8000-000000000001"
PROJECT = "https://project.supabase.test"


class Directory:
    def __init__(self, users: dict[str, tuple[int, str]]) -> None:
        self.users = users

    async def account_for_user(self, user_id: str):  # noqa: ANN201
        return self.users.get(user_id)


def _token(monkeypatch: pytest.MonkeyPatch, claims: dict) -> None:
    monkeypatch.setattr(identity, "get_access_token", lambda: SimpleNamespace(claims=claims))
    monkeypatch.setattr(identity, "current_team_slug", lambda: None)


def test_supabase_token_resolves_to_the_email_account(monkeypatch):
    _token(monkeypatch, {"sub": USER, "email": "bob@corp.example"})

    caller = asyncio.run(resolve_caller(Directory({USER: (-3, "bob")})))

    assert (caller.github_id, caller.github_login) == (-3, "bob")


def test_supabase_token_without_account_asks_to_sign_in_on_the_web(monkeypatch):
    _token(monkeypatch, {"sub": USER})

    with pytest.raises(NotAuthenticatedError, match="웹에 한 번 로그인"):
        asyncio.run(resolve_caller(Directory({})))


def test_github_token_still_resolves_without_a_lookup(monkeypatch):
    _token(monkeypatch, {"sub": "1001", "login": "alice"})

    assert asyncio.run(resolve_caller(None)).github_id == 1001


def test_supabase_mode_points_clients_at_supabase_as_the_authorization_server():
    settings = ServerSettings(
        github_client_id="i", github_client_secret="s", base_url="http://127.0.0.1:8000", host="127.0.0.1", port=8000,
        supabase_url=PROJECT, supabase_service_key="k", auth_mode="supabase",
    )  # fmt: skip
    app = build_server(settings, InMemoryRepository()).http_app(middleware=HTTP_MIDDLEWARE)

    async def metadata() -> dict:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.post("/t/pilab/mcp", json={})).status_code == 401
            return (await client.get("/.well-known/oauth-protected-resource")).json()

    body = asyncio.run(metadata())
    assert body["authorization_servers"] == [f"{PROJECT}/auth/v1"]
    assert body["resource"].rstrip("/") == "http://127.0.0.1:8000"


def test_unknown_auth_mode_is_refused(monkeypatch):
    from pit.server.settings import SettingsError, load_settings

    monkeypatch.setenv("PITHUB_GITHUB_CLIENT_ID", "i")
    monkeypatch.setenv("PITHUB_GITHUB_CLIENT_SECRET", "s")
    monkeypatch.setenv("PITHUB_AUTH", "password")
    with pytest.raises(SettingsError):
        load_settings()
