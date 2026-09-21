"""로컬 pit 이 쓰는 HTTP API (MCP 도구와 같은 프로세스, 다른 인증)

    POST /api/v1/decisions   로컬에서 확정한 결정을 올린다 (origin=local_extract, 기본 비공개)
    GET  /api/v1/decisions   내 결정을 내려받는다 (감사·백필용, since 로 증분)
    GET  /api/v1/me          토큰이 누구 것인지

인증: Authorization: Bearer pit_... (웹 설정에서 발급한 토큰)
"""

import logging
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from pit.decisions.ids import make_decision_id
from pit.server.identity import Caller
from pit.server.records import ORIGIN_MCP, StoredDecision
from pit.server.tokens import hash_token, looks_like_token

logger = logging.getLogger(__name__)

ORIGIN_LOCAL = "local_extract"
MAX_PUSH_BATCH = 200
MAX_PULL_ROWS = 1000
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_TOO_LARGE = 413


class TokenRepository(Protocol):
    async def find_token_owner(self, token_hash: str) -> Caller | None: ...

    async def upsert_local(self, decisions: list[StoredDecision]) -> int:
        """로컬 결정을 넣거나 갱신한다 (같은 id면 갱신). 처리한 건수를 돌려준다."""
        ...

    async def list_mine(self, owner_github_id: int, since: datetime | None, limit: int) -> list[StoredDecision]: ...


class PushPayload(BaseModel):
    decisions: list[StoredDecision] = Field(max_length=MAX_PUSH_BATCH)


async def authenticate(request: Request, tokens: TokenRepository) -> Caller | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not looks_like_token(token):
        return None
    return await tokens.find_token_owner(hash_token(token))


def _owned_by(decision: StoredDecision, caller: Caller) -> StoredDecision:
    return decision.model_copy(
        update={
            "id": make_decision_id(str(caller.github_id), decision.id, decision.decided_at),
            "owner_github_id": caller.github_id,
            "origin": ORIGIN_LOCAL,
            "status": "confirmed",
            "visibility": "private",
            "source": {**decision.source, "local_id": decision.id},
        }
    )


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


class LocalApi:
    def __init__(self, tokens: TokenRepository) -> None:
        self._tokens = tokens

    async def me(self, request: Request) -> JSONResponse:
        caller = await authenticate(request, self._tokens)
        if caller is None:
            return _error(HTTP_UNAUTHORIZED, "유효한 토큰이 필요합니다.")
        return JSONResponse({"github_id": caller.github_id, "github_login": caller.github_login})

    async def push(self, request: Request) -> JSONResponse:
        caller = await authenticate(request, self._tokens)
        if caller is None:
            return _error(HTTP_UNAUTHORIZED, "유효한 토큰이 필요합니다.")
        try:
            payload = PushPayload.model_validate(await request.json())
        except (ValueError, ValidationError) as e:
            return _error(HTTP_BAD_REQUEST, f"본문이 올바르지 않습니다: {type(e).__name__}")

        # 소유자·출처·id는 클라이언트가 정하지 않는다. id를 토큰 주인 기준으로 다시 만들어야
        # 남의 행과 같은 id를 보내 덮어쓰는 일이 구조적으로 불가능하다. 로컬 id는 출처에 남긴다.
        rows = [_owned_by(decision, caller) for decision in payload.decisions]
        count = await self._tokens.upsert_local(rows)
        logger.info("로컬 결정 push", extra={"github_id": caller.github_id, "count": count})
        return JSONResponse({"upserted": count})

    async def pull(self, request: Request) -> JSONResponse:
        caller = await authenticate(request, self._tokens)
        if caller is None:
            return _error(HTTP_UNAUTHORIZED, "유효한 토큰이 필요합니다.")
        since_raw = request.query_params.get("since")
        try:
            since = datetime.fromisoformat(since_raw) if since_raw else None
        except ValueError:
            return _error(HTTP_BAD_REQUEST, "since 는 ISO 8601 형식이어야 합니다.")
        origin = request.query_params.get("origin")
        rows = await self._tokens.list_mine(caller.github_id, since, MAX_PULL_ROWS)
        if origin in (ORIGIN_MCP, ORIGIN_LOCAL):
            rows = [row for row in rows if row.origin == origin]
        return JSONResponse({"decisions": [row.model_dump(mode="json") for row in rows]})
