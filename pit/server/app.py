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
from pit.server.jev import JevJudge
from pit.server.ratelimit import RateLimiter
from pit.server.records import LinkRef, NodeRef
from pit.server.repository import DecisionRepository, RepositoryError, SupabaseRepository
from pit.server.routing import TeamConnectorMiddleware
from pit.server.settings import GITHUB_SCOPES, ServerSettings
from pit.server.tokencache import CachedTokenVerifier
from pit.server.tools import DEFAULT_SEARCH_LIMIT, DecisionTools, ToolFailure
from pit.server.twin import TwinService, TwinUnavailable

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
- `about`: 1-3 short topic names this decision is about (e.g. "evaluation split"), plus the main file or feature
  as kind "artifact" when there is one. Reuse the exact names you saw in search results `topics` so that
  decisions on the same subject connect. Use `links` for "depends_on" / "conflicts_with" another decision id.
- If the result has `possible_conflicts`, tell the user in one line that this seems to contradict those earlier
  decisions (call `get_decision` to say whose and what), so they can decide which stands.
- If the user gave the same verdict on the same proposal again within days, still call: the server folds it.
- `rationale`: only what the user actually said. Do not guess.
- Never include passwords, tokens, keys, customer names or personal data.
- Do not announce the recording or ask permission each time; just continue the work.

Call `search_my_decisions` ONCE when a task starts (with its topic), and again only when the user refers to
an earlier decision or you are about to propose something they might have rejected before. Do not search
before every proposal; do not repeat a search with similar words. Results are short summaries. Call `get_decision` for the full record of the ones you actually rely on —
that call is how pithub learns which records are useful. Results marked `verified: false` were recorded
automatically and not yet confirmed by the user; cite them with that caveat. `principle: true` marks a rule
the user wants followed.

Teams: if this connection came through a team address (`/t/<team>/mcp`), decisions are recorded for that
team. They become visible to the team 3 days later unless the user withdraws them; once visible they are the
company's record. Searches include the team's visible decisions by default. Results with `by` are a teammate's —
say whose they are when you rely on them ("last month <by> rejected the same approach"). Team principles
rank first. You never see a teammate's private records or their team records still inside the 3-day window. Pass `scope` to search only your
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
    provider = OriginScopedGitHubProvider(
        client_id=settings.github_client_id,
        client_secret=settings.github_client_secret,
        base_url=settings.base_url,
        required_scopes=list(GITHUB_SCOPES),
        jwt_signing_key=settings.jwt_signing_key,
        client_storage=client_storage,
    )
    # 요청마다 GitHub API를 두 번 부르지 않도록 검증 결과를 잠깐 기억한다
    provider._token_validator = CachedTokenVerifier(provider._token_validator)
    return provider


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
    async def whoami() -> dict[str, str | int | None]:
        """Show which pithub account this connection is signed in as, and its team status if connected through a team address."""
        caller = _caller()
        result: dict[str, str | int | None] = {"github_id": caller.github_id, "github_login": caller.github_login}
        if caller.team_slug and tools is not None:
            _, status = await _run(tools.team_status(caller, caller.team_slug))
            result.update({"team": caller.team_slug, "team_status": status})
        return result

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
        about: Annotated[list[NodeRef] | None, Field(description='What this decision is about: 1-3 short topic names (kind "topic"), plus the main file/module/feature (kind "artifact") if any. Reuse names shown in search results `topics`.')] = None,
        links: Annotated[list[LinkRef] | None, Field(description='Relations to other decisions you have seen: {"relation": "depends_on"|"conflicts_with", "to": "<decision id>"}.')] = None,
    ) -> dict[str, object]:
        """Record one decision that would matter later: a rejection, a correction, a choice among options, or an approval that sets direction. Skip routine go-aheads."""
        arguments = {
            "situation": situation, "proposal": proposal, "human_quote": human_quote, "verdict": verdict,
            "reject_kind": reject_kind, "rationale": rationale, "options": options or [], "chosen": chosen,
            "project": project, "client": client, "decided_at": decided_at, "tags": tags or [],
            "supersedes": supersedes or [],
            "about": [ref.model_dump() for ref in about or []], "links": [ref.model_dump() for ref in links or []],
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
        client: Annotated[str | None, Field(description="Which app this is: claude.ai, claude-code, codex, ...")] = None,
    ) -> dict[str, object]:
        """Read one decision in full — this user's own, or one visible to their team. Call it for the records you actually rely on."""
        return await _run(ready().get_decision(_caller(), decision_id, client))

    if settings.twin_enabled and repository is not None:
        jev = JevJudge(settings.jev_api_key) if settings.jev_api_key else None
        _register_twin(server, TwinService(repository, lambda: datetime.now(timezone.utc), jev))

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


def _register_twin(server: FastMCP, twin: TwinService) -> None:
    """트윈에게 묻기 (G6) — PITHUB_TWIN_ENABLED 일 때만 도구가 보인다 (D-0009: 본 시험 통과 뒤)"""

    @server.tool
    async def ask_twin(
        login: Annotated[str, Field(description="GitHub login of the teammate whose judgment you want to anticipate.")],
        proposal: Annotated[str, Field(description="The proposal they would be judging, in 1-2 neutral sentences.")],
        situation: Annotated[str, Field(description="What is being worked on, 1 sentence.")] = "",
    ) -> dict[str, object]:
        """Ask how a teammate would likely judge a proposal, from their visible past decisions. Returns a prediction with confidence and evidence, or abstains and asks them. It is a prediction, never their decision."""
        try:
            return await _run(twin.ask(_caller(), login, proposal, situation))
        except TwinUnavailable as e:
            raise ToolError(str(e)) from e
