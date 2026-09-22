"""사용자별 호출 빈도 제한

쓰기 도구가 공개 주소에 열려 있다. 잘못 짜인 지침이나 폭주하는 에이전트가
받은함을 쓰레기로 채우지 못하게 막는다. 머신 한 대를 전제로 한 메모리 구현이다.
"""

from collections import deque
from collections.abc import Callable

# 폭주 방지용이지 백필을 막는 값이 아니다. 메모 백필 한 세션이 100건을 넘길 수 있다.
RATE_LIMIT_MAX_CALLS = 300
RATE_LIMIT_WINDOW_SECONDS = 3600.0


class RateLimiter:
    def __init__(
        self,
        clock: Callable[[], float],
        max_calls: int = RATE_LIMIT_MAX_CALLS,
        window_seconds: float = RATE_LIMIT_WINDOW_SECONDS,
    ) -> None:
        self._clock = clock
        self._max_calls = max_calls
        self._window = window_seconds
        self._calls: dict[int, deque[float]] = {}

    def allow(self, github_id: int) -> bool:
        """이번 호출을 허용하면 True (허용한 호출만 집계한다)"""
        now = self._clock()
        calls = self._calls.setdefault(github_id, deque())
        while calls and now - calls[0] >= self._window:
            calls.popleft()
        if len(calls) >= self._max_calls:
            return False
        calls.append(now)
        return True
