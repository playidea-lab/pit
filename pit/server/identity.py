"""도구를 호출한 사람의 신원"""

from dataclasses import dataclass

from fastmcp.server.dependencies import get_access_token


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
