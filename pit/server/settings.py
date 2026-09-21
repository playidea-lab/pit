"""서버 설정 — 전부 환경변수에서 읽는다 (주소·포트·비밀을 코드에 두지 않는다)"""

import os
from dataclasses import dataclass

ENV_GITHUB_CLIENT_ID = "PITHUB_GITHUB_CLIENT_ID"
ENV_GITHUB_CLIENT_SECRET = "PITHUB_GITHUB_CLIENT_SECRET"
ENV_BASE_URL = "PITHUB_MCP_BASE_URL"
ENV_JWT_SIGNING_KEY = "PITHUB_JWT_SIGNING_KEY"
ENV_HOST = "PITHUB_MCP_HOST"
ENV_PORT = "PITHUB_MCP_PORT"

# 개발 기본값 (운영에서는 반드시 환경변수로 지정한다)
DEV_HOST = "127.0.0.1"
DEV_PORT = 8000
# 로그인에는 신원만 필요하다. 저장소 접근 권한은 요구하지 않는다.
GITHUB_SCOPES = ("read:user",)


class SettingsError(Exception):
    """필수 환경변수가 없음"""


@dataclass(frozen=True)
class ServerSettings:
    github_client_id: str
    github_client_secret: str
    base_url: str
    host: str
    port: int
    # 없으면 FastMCP가 client secret에서 키를 파생한다 (개발 전용)
    jwt_signing_key: str | None


def load_settings() -> ServerSettings:
    """환경변수에서 설정을 읽는다

    Raises:
        SettingsError: GitHub OAuth 자격 증명이 없을 때
    """
    missing = [name for name in (ENV_GITHUB_CLIENT_ID, ENV_GITHUB_CLIENT_SECRET) if not os.environ.get(name)]
    if missing:
        raise SettingsError(f"환경변수가 필요합니다: {', '.join(missing)}")

    host = os.environ.get(ENV_HOST, DEV_HOST)
    port = int(os.environ.get(ENV_PORT, DEV_PORT))
    return ServerSettings(
        github_client_id=os.environ[ENV_GITHUB_CLIENT_ID],
        github_client_secret=os.environ[ENV_GITHUB_CLIENT_SECRET],
        base_url=os.environ.get(ENV_BASE_URL, f"http://{host}:{port}"),
        host=host,
        port=port,
        jwt_signing_key=os.environ.get(ENV_JWT_SIGNING_KEY),
    )
