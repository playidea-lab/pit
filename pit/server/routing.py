"""팀 커넥터 주소

`/t/<slug>/mcp` 는 `/mcp` 와 같은 서버이되 "이 세션은 이 팀의 것"이라는 뜻을 주소에 싣는다.
팀 저장소의 `.mcp.json` 에 이 주소를 넣어 두면 그 저장소에서 일하는 모든 팀원의 세션이
아무것도 고르지 않고 팀 범위로 기록한다. 인증(OAuth)은 `/mcp` 하나로 이루어지므로 경로만
바꿔 태우고, 어느 팀인지는 요청 상태에 남긴다.
"""

import re
from collections.abc import Awaitable, Callable, MutableMapping

Scope = MutableMapping[str, object]
AsgiApp = Callable[[Scope, Callable[[], Awaitable[object]], Callable[[object], Awaitable[None]]], Awaitable[None]]

TEAM_STATE_KEY = "pithub_team"
TEAM_QUERY_KEY = "team"
TEAM_SLUG_PATTERN = r"[a-z0-9][a-z0-9-]{1,38}"
_TEAM_PATH = re.compile(rf"^/t/(?P<slug>{TEAM_SLUG_PATTERN})(?P<rest>/mcp/?)$")


def team_path(slug: str, mcp_path: str = "/mcp") -> str:
    return f"/t/{slug}{mcp_path}"


class TeamConnectorMiddleware:
    """`/t/<slug>/mcp` 를 `/mcp` 로 바꿔 태우고 slug 를 scope["state"] 에 남긴다

    scope 를 새로 만들지 않고 제자리에서 고친다. 바깥 미들웨어가 이미 같은 dict 로
    Request 를 만들어 두었기 때문이다.
    """

    def __init__(self, app: AsgiApp, mcp_path: str = "/mcp") -> None:
        self._app = app
        self._mcp_path = mcp_path

    async def __call__(
        self,
        scope: Scope,
        receive: Callable[[], Awaitable[object]],
        send: Callable[[object], Awaitable[None]],
    ) -> None:
        if scope.get("type") == "http":
            matched = _TEAM_PATH.match(str(scope.get("path", "")))
            if matched:
                scope["path"] = self._mcp_path
                scope["raw_path"] = self._mcp_path.encode()
                state = scope.setdefault("state", {})
                if isinstance(state, dict):
                    state[TEAM_STATE_KEY] = matched.group("slug")
        await self._app(scope, receive, send)
