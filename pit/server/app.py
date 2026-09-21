"""MCP 서버 조립

인증은 FastMCP의 GitHubProvider에 맡긴다. claude.ai 커스텀 커넥터가 요구하는
OAuth 2.1 · 동적 클라이언트 등록 · PKCE를 이 프로바이더가 중계하고, 사용자는
GitHub 계정으로 로그인한다. 인증 로직을 직접 구현하지 않는다.
"""

from dataclasses import dataclass

from fastmcp import FastMCP
from fastmcp.server.auth.providers.github import GitHubProvider
from fastmcp.server.dependencies import get_access_token

from pit.server.settings import GITHUB_SCOPES, ServerSettings

SERVER_NAME = "pithub"
SERVER_INSTRUCTIONS = """\
pithub는 사용자가 LLM과 일하며 내린 결정을 기록한다.
"""


class NotAuthenticatedError(Exception):
    """인증된 사용자 정보를 읽을 수 없음"""


@dataclass(frozen=True)
class Caller:
    """도구를 호출한 사람. GitHub의 숫자 id가 pithub 계정과 이어지는 열쇠다."""

    github_id: int
    github_login: str


def current_caller() -> Caller:
    """현재 요청의 인증된 사용자를 돌려준다

    Raises:
        NotAuthenticatedError: 토큰이 없거나 GitHub 신원이 담겨 있지 않을 때
    """
    token = get_access_token()
    if token is None:
        raise NotAuthenticatedError("인증이 필요합니다.")
    github_id = token.claims.get("sub")
    login = token.claims.get("login")
    if github_id is None or not login:
        raise NotAuthenticatedError("토큰에 GitHub 신원이 없습니다.")
    return Caller(github_id=int(github_id), github_login=str(login))


def build_server(settings: ServerSettings) -> FastMCP:
    auth = GitHubProvider(
        client_id=settings.github_client_id,
        client_secret=settings.github_client_secret,
        base_url=settings.base_url,
        required_scopes=list(GITHUB_SCOPES),
        jwt_signing_key=settings.jwt_signing_key,
    )
    server = FastMCP(name=SERVER_NAME, instructions=SERVER_INSTRUCTIONS, auth=auth)

    @server.tool
    def whoami() -> dict[str, str | int]:
        """지금 연결된 pithub 계정을 확인한다 (연결 시험용)."""
        caller = current_caller()
        return {"github_id": caller.github_id, "github_login": caller.github_login}

    return server
