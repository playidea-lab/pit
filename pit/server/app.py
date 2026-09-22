"""MCP 서버 조립

인증은 FastMCP의 GitHubProvider에 맡긴다. claude.ai 커스텀 커넥터가 요구하는
OAuth 2.1 · 동적 클라이언트 등록 · PKCE를 이 프로바이더가 중계하고, 사용자는
GitHub 계정으로 로그인한다. 인증 로직을 직접 구현하지 않는다.
"""

import time
from collections.abc import Awaitable
from datetime import datetime, timezone
from typing import Annotated, TypeVar

from cryptography.fernet import Fernet
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.providers.github import GitHubProvider
from key_value.aio.stores.disk import DiskStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
from pydantic import AnyHttpUrl, Field
from starlette.middleware import Middleware

from pit.server.api import LocalApi
from pit.server.identity import Caller, NotAuthenticatedError, current_caller
from pit.server.ratelimit import RateLimiter
from pit.server.repository import DecisionRepository, RepositoryError, SupabaseRepository
from pit.server.routing import TeamConnectorMiddleware
from pit.server.settings import GITHUB_SCOPES, ServerSettings
from pit.server.tools import DEFAULT_SEARCH_LIMIT, DecisionTools, ToolFailure

SERVER_NAME = "pithub"
ResultT = TypeVar("ResultT")
# `/t/<slug>/mcp` 팀 커넥터 주소를 `/mcp` 로 태운다 (run 과 http_app 양쪽에 같은 목록)
HTTP_MIDDLEWARE = [Middleware(TeamConnectorMiddleware)]

# 세 클라이언트(claude.ai · Claude Code · Codex)의 모델이 읽는 글이다.
SERVER_INSTRUCTIONS = """\
pithub keeps a personal record of the decisions this user makes while working with an AI assistant.
Record decisions that would matter to someone asking later "why did you do it this way?" — not every step.

Record (call `record_decision` once, right after the user reacts):
- the user REJECTS or CORRECTS something you proposed ("no, not that", "do X instead", "drop it"). These matter most.
- the user CHOOSES between alternatives you laid out (set `options` and `chosen`).
- the user APPROVES a proposal that sets direction: architecture, scope, a rule to follow from now on,
  a trade-off accepted, something deliberately not done. Use `tags: ["principle"]` when it is a rule going forward.

Do NOT record:
- routine go-aheads on incremental steps ("ok", "continue", "next") with nothing at stake
- the user starting a task, asking a factual question, or giving information
- your own decisions that the user did not react to
- anything you are unsure about — a missed record is cheaper than a wrong one

How to fill it:
- `human_quote`: the user's own words, verbatim. Never paraphrase.
- `situation` / `proposal`: neutral, 1-2 sentences. They must NOT contain the verdict or words like
  "rejected", "dropped", "approved", "adopted" — write what was on the table, not what happened to it.
- If this decision overturns an earlier one, search first and pass its id in `supersedes`.
- If the user gave the same verdict on the same proposal again within days, still call: the server folds it.
- `rationale`: only what the user actually said. Do not guess.
- Never include passwords, tokens, keys, customer names or personal data.
- Do not announce the recording or ask permission each time; just continue the work.

Before proposing an approach on a topic the user may have decided before, call `search_my_decisions`.
Results are short summaries. Call `get_decision` for the full record of the ones you actually rely on —
that call is how pithub learns which records are useful. Results marked `verified: false` were recorded
automatically and not yet confirmed by the user; cite them with that caveat. `principle: true` marks a rule
the user wants followed.

Teams: if this connection came through a team address (`/t/<team>/mcp`), decisions are recorded for that
team and searches include the team's confirmed decisions by default. Results with `by` are a teammate's —
say whose they are when you rely on them ("last month <by> rejected the same approach"). Team principles
rank first. You never see a teammate's unconfirmed or private records. Pass `scope` to search only your
own (`mine`) or a specific team (`team:<slug>`).
"""

STORAGE_NOT_READY = "pithub 저장소가 아직 준비되지 않았습니다. 기록은 저장되지 않았습니다."


def _caller() -> Caller:
    try:
        return current_caller()
    except NotAuthenticatedError as e:
        raise ToolError(str(e)) from e


class OriginScopedGitHubProvider(GitHubProvider):
    """보호 리소스를 `/mcp` 하나가 아니라 서버 origin 전체로 광고한다

    MCP 클라이언트(Claude Code 등)는 메타데이터의 resource 가 접속 주소의 접두사일 때만 받아 준다.
    팀 주소 `/t/<slug>/mcp` 도 같은 서버이므로 resource 는 origin 이어야 한다.
    토큰의 audience 검증은 FastMCP 내부에서 따로 하므로 기존 로그인은 그대로 유효하다.
    """

    def _get_resource_url(self, path: str | None = None) -> AnyHttpUrl | None:
        return self.base_url


def _build_auth(settings: ServerSettings) -> GitHubProvider:
    client_storage = None
    if settings.oauth_storage_dir and settings.oauth_storage_key:
        # 재배포해도 세 클라이언트가 다시 로그인하지 않도록 디스크(Fly 볼륨)에 둔다.
        # 담기는 것이 GitHub 토큰이라 반드시 암호화한다.
        client_storage = FernetEncryptionWrapper(
            key_value=DiskStore(directory=str(settings.oauth_storage_dir)),
            fernet=Fernet(settings.oauth_storage_key.encode()),
        )
    return OriginScopedGitHubProvider(
        client_id=settings.github_client_id,
        client_secret=settings.github_client_secret,
        base_url=settings.base_url,
        required_scopes=list(GITHUB_SCOPES),
        jwt_signing_key=settings.jwt_signing_key,
        client_storage=client_storage,
    )


def _build_repository(settings: ServerSettings) -> DecisionRepository | None:
    if not (settings.supabase_url and settings.supabase_service_key):
        return None
    return SupabaseRepository(settings.supabase_url, settings.supabase_service_key)


def build_server(settings: ServerSettings, repository: DecisionRepository | None = None) -> FastMCP:
    """서버를 조립한다. repository를 주면 그것을 쓰고(테스트), 없으면 설정에서 만든다."""
    repository = repository or _build_repository(settings)
    tools = (
        DecisionTools(repository, RateLimiter(time.monotonic), lambda: datetime.now(timezone.utc))
        if repository is not None
        else None
    )
    server = FastMCP(name=SERVER_NAME, instructions=SERVER_INSTRUCTIONS, auth=_build_auth(settings))

    def ready() -> DecisionTools:
        if tools is None:
            raise ToolError(STORAGE_NOT_READY)
        return tools

    @server.tool
    def whoami() -> dict[str, str | int]:
        """Show which pithub account this connection is signed in as."""
        caller = _caller()
        return {"github_id": caller.github_id, "github_login": caller.github_login}

    @server.tool
    async def record_decision(
        situation: Annotated[str, Field(description="What was being worked on, in 1-2 neutral sentences.")],
        proposal: Annotated[str, Field(description="What you (the assistant) proposed, in 1-2 neutral sentences.")],
        human_quote: Annotated[str, Field(description="The user's reaction, copied verbatim from their message.")],
        verdict: Annotated[str | None, Field(description="approve | modify | reject")] = None,
        reject_kind: Annotated[str | None, Field(description="Only for reject: stop | redirect")] = None,
        rationale: Annotated[str, Field(description="The user's stated reason, if they gave one. Do not guess.")] = "",
        options: Annotated[list[str] | None, Field(description="Options you offered, if the user chose among them.")] = None,
        chosen: Annotated[str | None, Field(description="The option the user picked.")] = None,
        project: Annotated[str | None, Field(description="Project or topic name, if obvious.")] = None,
        client: Annotated[str | None, Field(description="Which app this is: claude.ai, claude-code, codex, ...")] = None,
        decided_at: Annotated[str | None, Field(description="ISO 8601 time, ONLY when backfilling a past decision from notes or documents. Omit for decisions made now.")] = None,
        tags: Annotated[list[str] | None, Field(description='Short topic tags. Use "principle" for a rule the user wants followed from now on.')] = None,
        supersedes: Annotated[list[str] | None, Field(description="Ids of the user's earlier decisions that this one overturns (find them with search_my_decisions first).")] = None,
    ) -> dict[str, object]:
        """Record one decision that would matter later: a rejection, a correction, a choice among options, or an approval that sets direction. Skip routine go-aheads."""
        arguments = {
            "situation": situation, "proposal": proposal, "human_quote": human_quote, "verdict": verdict,
            "reject_kind": reject_kind, "rationale": rationale, "options": options or [], "chosen": chosen,
            "project": project, "client": client, "decided_at": decided_at, "tags": tags or [],
            "supersedes": supersedes or [],
        }  # fmt: skip
        return await _run(ready().record_decision(_caller(), arguments))

    @server.tool
    async def search_my_decisions(
        query: Annotated[str, Field(description="Words to look for in this user's confirmed past decisions.")],
        limit: Annotated[int, Field(description="Maximum results.")] = DEFAULT_SEARCH_LIMIT,
        client: Annotated[str | None, Field(description="Which app this is: claude.ai, claude-code, codex, ...")] = None,
        scope: Annotated[str | None, Field(description="mine | team | team:<slug>. Default: team when connected through a team address, else mine.")] = None,
    ) -> list[dict[str, object]]:
        """Find how this user (and, through a team address, their team) decided similar things before. Returns short summaries; call get_decision for the full record of the ones you actually use."""
        return await _run(ready().search_my_decisions(_caller(), query, limit, client, scope))

    @server.tool
    async def get_decision(
        decision_id: Annotated[str, Field(description="An id returned by search_my_decisions or record_decision.")],
    ) -> dict[str, object]:
        """Read one decision in full — this user's own, or a teammate's confirmed team decision."""
        return await _run(ready().get_decision(_caller(), decision_id))

    if repository is not None:
        api = LocalApi(repository)
        server.custom_route("/api/v1/me", methods=["GET"])(api.me)
        server.custom_route("/api/v1/decisions", methods=["POST"])(api.push)
        server.custom_route("/api/v1/decisions", methods=["GET"])(api.pull)

    return server


async def _run(operation: Awaitable[ResultT]) -> ResultT:
    """도구의 실패를 MCP 클라이언트가 이해하는 오류로 옮긴다"""
    try:
        return await operation
    except ToolFailure as e:
        raise ToolError(str(e)) from e
    except RepositoryError as e:
        raise ToolError("pithub 저장소에 닿지 못했습니다. 기록은 저장되지 않았습니다.") from e
