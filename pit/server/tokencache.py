"""GitHub 토큰 검증 결과를 잠깐 기억한다

FastMCP의 GitHub 검증기는 MCP 요청마다 GitHub API를 두 번(/user, /user/repos) 부른다.
세션 하나가 요청을 수십 번 보내므로 호출마다 지연이 붙고 GitHub 호출 한도를 빠르게 쓴다.
성공한 검증만 짧게 기억한다 — 토큰을 폐기해도 최대 TTL 동안은 통과할 수 있다는 대가를 받아들인다.
"""

import hashlib
import time
from collections import OrderedDict
from collections.abc import Callable

from fastmcp.server.auth import AccessToken, TokenVerifier

VERIFY_CACHE_TTL_SECONDS = 300.0
VERIFY_CACHE_MAX_ENTRIES = 1024


class CachedTokenVerifier(TokenVerifier):
    """다른 검증기를 감싸 성공 결과를 TTL 동안 기억한다. 토큰 원문은 담지 않고 해시로 찾는다."""

    def __init__(
        self,
        inner: TokenVerifier,
        clock: Callable[[], float] = time.monotonic,
        ttl_seconds: float = VERIFY_CACHE_TTL_SECONDS,
        max_entries: int = VERIFY_CACHE_MAX_ENTRIES,
    ) -> None:
        super().__init__(required_scopes=inner.required_scopes)
        self._inner = inner
        self._clock = clock
        self._ttl = ttl_seconds
        self._max = max_entries
        self._entries: OrderedDict[str, tuple[float, AccessToken]] = OrderedDict()

    async def verify_token(self, token: str) -> AccessToken | None:
        key = hashlib.sha256(token.encode()).hexdigest()
        now = self._clock()
        hit = self._entries.get(key)
        if hit is not None and hit[0] > now:
            self._entries.move_to_end(key)
            return hit[1]
        verified = await self._inner.verify_token(token)
        if verified is None:
            # 실패는 기억하지 않는다 — 방금 발급된 토큰이 한동안 거부되면 안 된다
            self._entries.pop(key, None)
            return None
        self._entries[key] = (now + self._ttl, verified)
        self._entries.move_to_end(key)
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)
        return verified
