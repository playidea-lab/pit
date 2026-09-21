"""pithub MCP 서버 테스트 (네트워크 없이)"""

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("fastmcp", reason="서버 extra가 설치된 환경에서만 실행")

from pit.server import app as server_app  # noqa: E402
from pit.server import identity  # noqa: E402
from pit.server.settings import GITHUB_SCOPES, SettingsError, load_settings  # noqa: E402

ENV = {
    "PITHUB_GITHUB_CLIENT_ID": "placeholder-id",
    "PITHUB_GITHUB_CLIENT_SECRET": "placeholder-secret",
}


def _set_env(monkeypatch: pytest.MonkeyPatch, **extra: str) -> None:
    for name in ("PITHUB_MCP_BASE_URL", "PITHUB_MCP_HOST", "PITHUB_MCP_PORT", "PITHUB_JWT_SIGNING_KEY"):
        monkeypatch.delenv(name, raising=False)
    for name, value in {**ENV, **extra}.items():
        monkeypatch.setenv(name, value)


def test_load_settings_missing_github_credentials_raises_settings_error(monkeypatch):
    for name in ENV:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(SettingsError, match="PITHUB_GITHUB_CLIENT_ID"):
        load_settings()


def test_load_settings_base_url_defaults_to_host_and_port(monkeypatch):
    _set_env(monkeypatch, PITHUB_MCP_PORT="9001")

    settings = load_settings()

    assert settings.base_url == "http://127.0.0.1:9001"
    assert settings.jwt_signing_key is None


def test_load_settings_explicit_base_url_wins(monkeypatch):
    _set_env(monkeypatch, PITHUB_MCP_BASE_URL="https://mcp.example.test")

    assert load_settings().base_url == "https://mcp.example.test"


def test_github_scopes_request_identity_only():
    """로그인에 저장소 권한을 요구하지 않는다 (기존 pithub는 repo 쓰기 권한까지 요구했다)"""
    assert GITHUB_SCOPES == ("read:user",)


def test_current_caller_without_token_raises_not_authenticated(monkeypatch):
    monkeypatch.setattr(identity, "get_access_token", lambda: None)

    with pytest.raises(identity.NotAuthenticatedError):
        identity.current_caller()


def test_current_caller_token_without_github_identity_raises(monkeypatch):
    monkeypatch.setattr(identity, "get_access_token", lambda: SimpleNamespace(claims={"login": "cm"}))

    with pytest.raises(identity.NotAuthenticatedError):
        identity.current_caller()


def test_current_caller_reads_numeric_github_id_and_login(monkeypatch):
    token = SimpleNamespace(claims={"sub": "12345", "login": "cm"})
    monkeypatch.setattr(identity, "get_access_token", lambda: token)

    assert identity.current_caller() == identity.Caller(github_id=12345, github_login="cm")


def test_build_server_exposes_whoami_tool(monkeypatch):
    _set_env(monkeypatch)

    server = server_app.build_server(load_settings())
    tools = asyncio.run(server.get_tools())

    assert set(tools) == {"whoami", "record_decision", "search_my_decisions", "get_decision"}
