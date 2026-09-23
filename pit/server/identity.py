"""도구를 호출한 사람의 신원"""

from dataclasses import dataclass
from typing import Protocol

from fastmcp.server.dependencies import get_access_token, get_http_request

from pit.server.routing import TEAM_QUERY_KEY, TEAM_STATE_KEY


class NotAuthenticatedError(Exception):
    """인증된 사용자 정보를 읽을 수 없음"""


@dataclass(frozen=True)
class Caller:
    """도구를 호출한 사람. GitHub의 숫자 id가 pithub 계정과 이어지는 열쇠다.

    team_slug 는 팀 커넥터 주소(`/t/<slug>/mcp`)로 들어온 세션에만 있다.
    """

    github_id: int
    github_login: str
    team_slug: str | None = None


def current_team_slug() -> str | None:
    """이 요청이 팀 커넥터로 들어왔으면 그 팀의 slug (경로 또는 `?team=`)"""
    try:
        request = get_http_request()
    except RuntimeError:
        # HTTP 밖(인메모리 클라이언트)에서는 팀 커넥터가 없다
        return None
    state = request.scope.get("state") or {}
    slug = state.get(TEAM_STATE_KEY) if isinstance(state, dict) else None
    return str(slug or request.query_params.get(TEAM_QUERY_KEY) or "") or None


class AccountDirectory(Protocol):
    async def account_for_user(self, user_id: str) -> tuple[int, str] | None:
        """Supabase 사용자 id → (계정 번호, 로그인 이름). 계정이 없으면 None."""
        ...


def current_caller() -> Caller:
    """GitHub 로그인 토큰(sub = GitHub 숫자 id, login 포함)의 사용자 — PITHUB_AUTH=github

    Raises:
        NotAuthenticatedError: 토큰이 없거나 GitHub 신원이 담겨 있지 않을 때
    """
    token = get_access_token()
    if token is None:
        raise NotAuthenticatedError("인증이 필요합니다.")
    github_id = token.claims.get("sub")
    login = token.claims.get("login")
    if github_id is None or not login or not str(github_id).isdigit():
        raise NotAuthenticatedError("토큰에 GitHub 신원이 없습니다.")
    return Caller(github_id=int(github_id), github_login=str(login), team_slug=current_team_slug())


async def resolve_caller(directory: AccountDirectory | None) -> Caller:
    """토큰의 사용자를 계정으로 — GitHub 토큰이면 그대로, Supabase 토큰(sub = 사용자 UUID)이면 계정 번호를 찾는다.
    Supabase 로그인은 GitHub·이메일을 모두 받는다 (PITHUB_AUTH=supabase)."""
    token = get_access_token()
    if token is None:
        raise NotAuthenticatedError("인증이 필요합니다.")
    subject = str(token.claims.get("sub") or "")
    if subject.isdigit() and token.claims.get("login"):
        return current_caller()
    if not subject or directory is None:
        raise NotAuthenticatedError("토큰에 사용자 신원이 없습니다.")
    found = await directory.account_for_user(subject)
    if found is None:
        raise NotAuthenticatedError("pithub 계정을 찾지 못했습니다. pithub 웹에 한 번 로그인한 뒤 다시 연결하세요.")
    return Caller(github_id=found[0], github_login=found[1], team_slug=current_team_slug())
