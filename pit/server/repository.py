"""결정 저장소

도구 로직은 이 규약에만 의존한다. 운영에서는 Supabase(PostgREST)를 service_role로 부르고,
테스트에서는 메모리 구현을 주입한다.
"""

import logging
import re
from typing import Protocol

import httpx

from pit.server.records import StoredDecision

logger = logging.getLogger(__name__)

HTTP_TIMEOUT_SECONDS = 10.0
STATUS_CONFIRMED = "confirmed"
SEARCH_COLUMNS = ("situation", "proposal", "rationale", "human_quote")
# PostgREST의 or=() 문법에서 뜻을 갖는 문자. 검색어에서 빼 버린다 (v1은 단순 부분 일치로 충분하다).
_FILTER_SYNTAX = re.compile(r'[,()"\\*%]')


class RepositoryError(Exception):
    """저장소에 읽거나 쓰지 못함"""


class DecisionRepository(Protocol):
    async def ensure_account(self, github_id: int, github_login: str) -> None: ...

    async def insert_draft(self, decision: StoredDecision) -> bool:
        """초안을 저장한다. 같은 중복 키가 이미 있으면 저장하지 않고 False."""
        ...

    async def search_confirmed(self, owner_github_id: int, query: str, limit: int) -> list[StoredDecision]: ...

    async def get(self, owner_github_id: int, decision_id: str) -> StoredDecision | None: ...


def sanitize_query(query: str) -> str:
    return " ".join(_FILTER_SYNTAX.sub(" ", query).split())


class SupabaseRepository:
    """PostgREST를 service_role 키로 호출한다. 키는 RLS를 지나치므로 소유자 조건을 매번 직접 건다."""

    def __init__(self, base_url: str, service_key: str, client: httpx.AsyncClient | None = None) -> None:
        self._rest = f"{base_url.rstrip('/')}/rest/v1"
        self._headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
        self._client = client or httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS)

    async def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        headers = {**self._headers, **kwargs.pop("headers", {})}
        try:
            response = await self._client.request(method, f"{self._rest}{path}", headers=headers, **kwargs)
            response.raise_for_status()
        except httpx.HTTPError as e:
            # 응답 본문에는 저장하려던 글이 섞일 수 있어 로그에 남기지 않는다
            logger.error("저장소 호출 실패", extra={"method": method, "path": path, "error": type(e).__name__})
            raise RepositoryError(f"저장소 호출 실패: {type(e).__name__}") from e
        return response

    async def ensure_account(self, github_id: int, github_login: str) -> None:
        await self._request(
            "POST",
            "/accounts",
            params={"on_conflict": "github_id"},
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            json={"github_id": github_id, "github_login": github_login},
        )

    async def insert_draft(self, decision: StoredDecision) -> bool:
        response = await self._request(
            "POST",
            "/decisions",
            params={"on_conflict": "owner_github_id,dedupe_key"},
            headers={"Prefer": "resolution=ignore-duplicates,return=representation"},
            json=decision.model_dump(mode="json"),
        )
        return bool(response.json())

    async def search_confirmed(self, owner_github_id: int, query: str, limit: int) -> list[StoredDecision]:
        params = {
            "owner_github_id": f"eq.{owner_github_id}",
            "status": f"eq.{STATUS_CONFIRMED}",
            "order": "decided_at.desc",
            "limit": str(limit),
        }
        cleaned = sanitize_query(query)
        if cleaned:
            params["or"] = "(" + ",".join(f"{column}.ilike.*{cleaned}*" for column in SEARCH_COLUMNS) + ")"
        response = await self._request("GET", "/decisions", params=params)
        return [StoredDecision.model_validate(row) for row in response.json()]

    async def get(self, owner_github_id: int, decision_id: str) -> StoredDecision | None:
        params = {"owner_github_id": f"eq.{owner_github_id}", "id": f"eq.{decision_id}", "limit": "1"}
        rows = (await self._request("GET", "/decisions", params=params)).json()
        return StoredDecision.model_validate(rows[0]) if rows else None
