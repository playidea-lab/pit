"""서버 설정 — 전부 환경변수에서 읽는다 (주소·포트·비밀을 코드에 두지 않는다)"""

import os
from dataclasses import dataclass
from pathlib import Path

ENV_GITHUB_CLIENT_ID = "PITHUB_GITHUB_CLIENT_ID"
ENV_GITHUB_CLIENT_SECRET = "PITHUB_GITHUB_CLIENT_SECRET"
ENV_BASE_URL = "PITHUB_MCP_BASE_URL"
ENV_JWT_SIGNING_KEY = "PITHUB_JWT_SIGNING_KEY"
ENV_HOST = "PITHUB_MCP_HOST"
ENV_PORT = "PITHUB_MCP_PORT"
ENV_SUPABASE_URL = "PITHUB_SUPABASE_URL"
ENV_SUPABASE_SERVICE_KEY = "PITHUB_SUPABASE_SERVICE_KEY"
ENV_OAUTH_STORAGE_DIR = "PITHUB_OAUTH_STORAGE_DIR"
ENV_OAUTH_STORAGE_KEY = "PITHUB_OAUTH_STORAGE_KEY"

# 개발 기본값 (운영에서는 반드시 환경변수로 지정한다)
DEV_HOST = "127.0.0.1"
DEV_PORT = 8000
# 로그인에는 신원만 필요하다. 저장소 접근 권한은 요구하지 않는다.
GITHUB_SCOPES = ("read:user",)


class SettingsError(Exception):
    """필수 환경변수가 없거나 짝이 맞지 않음"""


@dataclass(frozen=True)
class ServerSettings:
    github_client_id: str
    github_client_secret: str
    base_url: str
    host: str
    port: int
    # 없으면 FastMCP가 client secret에서 키를 파생한다 (개발 전용)
    jwt_signing_key: str | None = None
    # 둘 다 있어야 결정을 저장한다. 없으면 서버는 뜨지만 기록 도구는 "준비 중"을 돌려준다.
    supabase_url: str | None = None
    supabase_service_key: str | None = None
    # OAuth 클라이언트 등록과 토큰을 둘 디렉터리. 없으면 메모리(재시작하면 모두 다시 로그인).
    oauth_storage_dir: Path | None = None
    oauth_storage_key: str | None = None

    @property
    def storage_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)


def load_settings() -> ServerSettings:
    """환경변수에서 설정을 읽는다

    Raises:
        SettingsError: GitHub OAuth 자격 증명이 없거나, 디스크 저장소에 암호화 키가 없을 때
    """
    missing = [name for name in (ENV_GITHUB_CLIENT_ID, ENV_GITHUB_CLIENT_SECRET) if not os.environ.get(name)]
    if missing:
        raise SettingsError(f"환경변수가 필요합니다: {', '.join(missing)}")

    storage_dir = os.environ.get(ENV_OAUTH_STORAGE_DIR)
    storage_key = os.environ.get(ENV_OAUTH_STORAGE_KEY)
    if storage_dir and not storage_key:
        # 디스크에 남는 것은 GitHub 토큰이다. 평문으로 두지 않는다.
        raise SettingsError(f"{ENV_OAUTH_STORAGE_DIR} 를 쓰려면 {ENV_OAUTH_STORAGE_KEY} 도 필요합니다.")

    host = os.environ.get(ENV_HOST, DEV_HOST)
    port = int(os.environ.get(ENV_PORT, DEV_PORT))
    return ServerSettings(
        github_client_id=os.environ[ENV_GITHUB_CLIENT_ID],
        github_client_secret=os.environ[ENV_GITHUB_CLIENT_SECRET],
        base_url=os.environ.get(ENV_BASE_URL, f"http://{host}:{port}"),
        host=host,
        port=port,
        jwt_signing_key=os.environ.get(ENV_JWT_SIGNING_KEY),
        supabase_url=os.environ.get(ENV_SUPABASE_URL),
        supabase_service_key=os.environ.get(ENV_SUPABASE_SERVICE_KEY),
        oauth_storage_dir=Path(storage_dir) if storage_dir else None,
        oauth_storage_key=storage_key,
    )
