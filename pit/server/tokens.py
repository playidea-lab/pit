"""로컬 pit 용 API 토큰

웹 설정 화면에서 발급되고 DB에는 해시만 남는다. 서버는 받은 토큰을 해시해 주인을 찾는다.
토큰 형식: pit_<32바이트 urlsafe>. 접두사는 로그·검색에서 토큰을 알아보기 위한 것이다.
"""

import hashlib
import secrets

TOKEN_PREFIX = "pit_"
TOKEN_RANDOM_BYTES = 32


def generate_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(TOKEN_RANDOM_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def looks_like_token(value: str) -> bool:
    return value.startswith(TOKEN_PREFIX) and len(value) > len(TOKEN_PREFIX) + TOKEN_RANDOM_BYTES
