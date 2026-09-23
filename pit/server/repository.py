"""결정 저장소

도구 로직은 이 규약에만 의존한다. 운영에서는 Supabase(PostgREST)를 service_role로 부르고,
테스트에서는 메모리 구현을 주입한다.
"""

import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol

import httpx

from pit.server.errors import RepositoryError
from pit.server.graph_store import SupabaseGraphMixin
from pit.server.identity import Caller
from pit.server.records import TEAM_SHARE_GRACE, WRITE_EXCLUDE, StoredDecision, normalize_text

if TYPE_CHECKING:
    from pit.server.graph import Namespace

logger = logging.getLogger(__name__)

HTTP_TIMEOUT_SECONDS = 10.0
STATUS_DISCARDED = "discarded"
STATUS_CONFIRMED = "confirmed"
SEARCH_COLUMNS = ("situation", "proposal", "rationale", "human_quote")
# PostgREST의 or=() 문법에서 뜻을 갖는 문자. 검색어에서 빼 버린다 (v1은 단순 부분 일치로 충분하다).
_FILTER_SYNTAX = re.compile(r'[,()"\\*%]')


class DecisionRepository(Protocol):
    async def ensure_account(self, github_id: int, github_login: str) -> None: ...

    async def insert_draft(self, decision: StoredDecision) -> bool:
        """초안을 저장한다. 같은 중복 키가 이미 있으면 저장하지 않고 False."""
        ...

    async def search_recorded(self, owner_github_id: int, query: str, limit: int) -> list[StoredDecision]: ...

    async def get(self, owner_github_id: int, decision_id: str) -> StoredDecision | None: ...

    async def project_default(self, owner_github_id: int, project: str) -> tuple[str, str | None] | None:
        """프로젝트별 기본 공개 범위 (visibility, team_id). 없으면 None → private."""
        ...

    async def find_recent_same_proposal(
        self, owner_github_id: int, project: str | None, proposal_normalized: str, since: datetime
    ) -> StoredDecision | None:
        """같은 프로젝트에서 since 이후 같은 제안이 기록된 적이 있으면 그것"""
        ...

    async def bump_repeat(self, decision_id: str) -> None: ...

    async def owns_all(self, owner_github_id: int, decision_ids: list[str]) -> bool:
        """supersedes 로 가리킨 결정이 전부 호출자 것인가"""
        ...

    async def record_search(self, owner_github_id: int, query: str, returned_ids: list[str], client: str | None) -> None: ...

    async def mark_cited(self, owner_github_id: int, decision_id: str) -> None:
        """get_decision 으로 전체를 가져간 것을 '쓰였다'로 센다"""
        ...

    # --- 팀 (D-0008) ---

    async def member_teams(self, github_id: int) -> list[tuple[str, str]]:
        """수락까지 끝난 팀들의 (team_id, slug)"""
        ...

    async def search_team(self, team_ids: list[str], query: str, limit: int) -> list[StoredDecision]:
        """팀 범위로 확정된 결정만 — 초안·비공개는 팀에 보이지 않는다"""
        ...

    async def get_by_id(self, decision_id: str) -> StoredDecision | None:
        """소유자를 묻지 않고 한 건. 누가 볼 수 있는지는 호출자가 판단한다."""
        ...

    async def logins_of(self, github_ids: list[int]) -> dict[int, str]: ...

    async def record_transfer(self, decision: StoredDecision, reader_github_id: int, via: str, client: str | None) -> None:
        """남의 판단을 가져간 사건을 남긴다 (G0)"""
        ...

    # --- 판단 그래프 (G2) ---

    async def resolve_node(self, namespace: "Namespace", kind: str, name: str, norm: str, created_by: int) -> str:
        """이름 공간에서 같은 종류·같은 비교용 이름(또는 별칭)의 살아 있는 노드를 찾고, 없으면 만든다"""
        ...

    async def attach_nodes(self, decision_id: str, node_ids: list[str]) -> None: ...

    async def add_links(self, from_decision: str, links: list[tuple[str, str, str]], created_by: int) -> None:
        """links: (to_decision, relation, status)"""
        ...

    async def topics_of(self, decision_ids: list[str]) -> dict[str, list[str]]:
        """결정별로 매달린 노드 이름"""
        ...

    async def find_nodes(self, team_ids: list[str], owner_github_id: int, norm_query: str, limit: int) -> list[str]:
        """이름 공간(속한 팀들 + 본인)에서 이름·별칭이 질의를 포함하는 살아 있는 노드 id (G4)"""
        ...

    async def decision_ids_on_nodes(self, node_ids: list[str], limit: int) -> list[str]: ...

    async def get_many(self, decision_ids: list[str]) -> list[StoredDecision]: ...

    async def links_of(self, decision_id: str) -> list[tuple[str, str, str, str]]:
        """(from_decision, to_decision, relation, status) — 이 결정이 어느 쪽이든 걸린 링크"""
        ...

    # --- 트윈 (G6) ---

    async def find_account(self, github_login: str) -> tuple[int, bool] | None:
        """(github_id, 떠났는가). 없으면 None."""
        ...

    async def team_decisions_of(self, owner_github_id: int, team_ids: list[str], limit: int) -> list[StoredDecision]:
        """그 사람이 이 팀들에 남긴 팀 범위 결정 (볼 수 있는지는 호출자가 거른다)"""
        ...

    async def record_consult(
        self, asker: int, twin: int, question: str, decision_ids: list[str], confidence: float, abstained: bool
    ) -> None: ...

    async def create_twin_question(
        self, asker: int, twin: int, team_id: str | None, situation: str, proposal: str, confidence: float
    ) -> None: ...

    async def find_team(self, slug: str) -> str | None:
        """slug 의 팀 id. 없으면 None."""
        ...

    async def request_join(self, team_id: str, github_id: int) -> None:
        """가입 요청 행(본인이 보낸 초대)을 만든다. 이미 있으면 그대로."""
        ...

    # --- 로컬 pit 용 (TokenRepository) ---

    async def find_token_owner(self, token_hash: str) -> Caller | None: ...

    async def upsert_local(self, decisions: list[StoredDecision]) -> int: ...

    async def list_mine(self, owner_github_id: int, since: datetime | None, limit: int) -> list[StoredDecision]: ...


def sanitize_query(query: str) -> str:
    return " ".join(_FILTER_SYNTAX.sub(" ", query).split())


class SupabaseRepository(SupabaseGraphMixin):
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
            # 계정을 지웠던 사람이 다시 오면 되살린다
            json={"github_id": github_id, "github_login": github_login, "deleted_at": None},
        )

    async def insert_draft(self, decision: StoredDecision) -> bool:
        response = await self._request(
            "POST",
            "/decisions",
            params={"on_conflict": "owner_github_id,dedupe_key"},
            headers={"Prefer": "resolution=ignore-duplicates,return=representation"},
            json=decision.model_dump(mode="json", exclude=WRITE_EXCLUDE),
        )
        return bool(response.json())

    async def search_recorded(self, owner_github_id: int, query: str, limit: int) -> list[StoredDecision]:
        params = {
            "owner_github_id": f"eq.{owner_github_id}",
            # 확인 전 기록도 검색된다. 기록은 자동, 확인은 쓰는 순간에 한다.
            "status": f"neq.{STATUS_DISCARDED}",
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

    async def find_token_owner(self, token_hash: str) -> Caller | None:
        params = {
            "token_hash": f"eq.{token_hash}",
            "revoked_at": "is.null",
            "select": "owner_github_id,accounts(github_login)",
            "limit": "1",
        }
        rows = (await self._request("GET", "/api_tokens", params=params)).json()
        if not rows:
            return None
        row = rows[0]
        account = row.get("accounts") or {}
        await self._request(
            "PATCH",
            "/api_tokens",
            params={"token_hash": f"eq.{token_hash}"},
            headers={"Prefer": "return=minimal"},
            json={"last_used_at": datetime.now().astimezone().isoformat()},
        )
        return Caller(github_id=int(row["owner_github_id"]), github_login=str(account.get("github_login", "")))

    async def upsert_local(self, decisions: list[StoredDecision]) -> int:
        if not decisions:
            return 0
        response = await self._request(
            "POST",
            "/decisions",
            params={"on_conflict": "id"},
            headers={"Prefer": "resolution=merge-duplicates,return=representation"},
            json=[decision.model_dump(mode="json", exclude=WRITE_EXCLUDE) for decision in decisions],
        )
        return len(response.json())

    async def list_mine(self, owner_github_id: int, since: datetime | None, limit: int) -> list[StoredDecision]:
        params = {"owner_github_id": f"eq.{owner_github_id}", "order": "decided_at.asc", "limit": str(limit)}
        if since is not None:
            params["decided_at"] = f"gte.{since.isoformat()}"
        response = await self._request("GET", "/decisions", params=params)
        return [StoredDecision.model_validate(row) for row in response.json()]

    async def project_default(self, owner_github_id: int, project: str) -> tuple[str, str | None] | None:
        params = {"github_id": f"eq.{owner_github_id}", "project": f"eq.{project}", "select": "visibility,team_id", "limit": "1"}
        rows = (await self._request("GET", "/project_defaults", params=params)).json()
        if not rows:
            return None
        return str(rows[0]["visibility"]), rows[0].get("team_id")

    async def find_recent_same_proposal(
        self, owner_github_id: int, project: str | None, proposal_normalized: str, since: datetime
    ) -> StoredDecision | None:
        params = {
            "owner_github_id": f"eq.{owner_github_id}",
            "status": f"neq.{STATUS_DISCARDED}",
            "decided_at": f"gte.{since.isoformat()}",
            "order": "decided_at.desc",
            "limit": "50",
        }
        rows = (await self._request("GET", "/decisions", params=params)).json()
        for row in rows:
            decision = StoredDecision.model_validate(row)
            same_project = decision.source.get("project") == project
            if same_project and normalize_text(decision.proposal) == proposal_normalized:
                return decision
        return None

    async def bump_repeat(self, decision_id: str) -> None:
        current = (await self._request("GET", "/decisions", params={"id": f"eq.{decision_id}", "select": "repeat_count"})).json()
        count = int(current[0]["repeat_count"]) + 1 if current else 2
        await self._request(
            "PATCH", "/decisions", params={"id": f"eq.{decision_id}"},
            headers={"Prefer": "return=minimal"}, json={"repeat_count": count},
        )  # fmt: skip

    async def owns_all(self, owner_github_id: int, decision_ids: list[str]) -> bool:
        if not decision_ids:
            return True
        ids = ",".join(f'"{decision_id}"' for decision_id in decision_ids)
        params = {"owner_github_id": f"eq.{owner_github_id}", "id": f"in.({ids})", "select": "id"}
        rows = (await self._request("GET", "/decisions", params=params)).json()
        return len(rows) == len(set(decision_ids))

    async def record_search(self, owner_github_id: int, query: str, returned_ids: list[str], client: str | None) -> None:
        await self._request(
            "POST", "/citations", headers={"Prefer": "return=minimal"},
            json={"owner_github_id": owner_github_id, "query": query, "returned_ids": returned_ids, "client": client},
        )  # fmt: skip

    async def member_teams(self, github_id: int) -> list[tuple[str, str]]:
        params = {"github_id": f"eq.{github_id}", "accepted_at": "not.is.null", "select": "team_id,teams!inner(slug)"}
        rows = (await self._request("GET", "/team_members", params=params)).json()
        return [(str(row["team_id"]), str(row["teams"]["slug"])) for row in rows]

    async def search_team(self, team_ids: list[str], query: str, limit: int) -> list[StoredDecision]:
        if not team_ids:
            return []
        # 팀에 보이는 것: 확인됐거나 유예(3일)가 지난 초안 — DB의 is_team_shared() 와 같은 조건
        shared_before = (datetime.now(timezone.utc) - TEAM_SHARE_GRACE).isoformat().replace("+00:00", "Z")
        conditions = [f"or(status.eq.{STATUS_CONFIRMED},created_at.lte.{shared_before})"]
        cleaned = sanitize_query(query)
        if cleaned:
            conditions.append("or(" + ",".join(f"{column}.ilike.*{cleaned}*" for column in SEARCH_COLUMNS) + ")")
        params = {
            "team_id": "in.(" + ",".join(team_ids) + ")",
            "status": f"neq.{STATUS_DISCARDED}",
            "visibility": "eq.team",
            "and": "(" + ",".join(conditions) + ")",
            "order": "decided_at.desc",
            "limit": str(limit),
        }
        response = await self._request("GET", "/decisions", params=params)
        return [StoredDecision.model_validate(row) for row in response.json()]

    async def get_by_id(self, decision_id: str) -> StoredDecision | None:
        rows = (await self._request("GET", "/decisions", params={"id": f"eq.{decision_id}", "limit": "1"})).json()
        return StoredDecision.model_validate(rows[0]) if rows else None

    async def logins_of(self, github_ids: list[int]) -> dict[int, str]:
        if not github_ids:
            return {}
        ids = ",".join(str(github_id) for github_id in set(github_ids))
        params = {"github_id": f"in.({ids})", "select": "github_id,github_login"}
        rows = (await self._request("GET", "/accounts", params=params)).json()
        return {int(row["github_id"]): str(row["github_login"]) for row in rows}

    async def record_transfer(self, decision: StoredDecision, reader_github_id: int, via: str, client: str | None) -> None:
        await self._request(
            "POST", "/transfers", headers={"Prefer": "return=minimal"},
            json={
                "decision_id": decision.id, "owner_github_id": decision.owner_github_id,
                "reader_github_id": reader_github_id, "team_id": decision.team_id, "via": via, "client": client,
            },
        )  # fmt: skip

    async def find_team(self, slug: str) -> str | None:
        rows = (await self._request("GET", "/teams", params={"slug": f"eq.{slug}", "select": "id", "limit": "1"})).json()
        return str(rows[0]["id"]) if rows else None

    async def request_join(self, team_id: str, github_id: int) -> None:
        await self._request(
            "POST", "/team_members", params={"on_conflict": "team_id,github_id"},
            headers={"Prefer": "resolution=ignore-duplicates,return=minimal"},
            json={"team_id": team_id, "github_id": github_id, "role": "member", "invited_by": github_id},
        )  # fmt: skip

    async def mark_cited(self, owner_github_id: int, decision_id: str) -> None:
        params = {"id": f"eq.{decision_id}", "owner_github_id": f"eq.{owner_github_id}", "select": "cited_count"}
        rows = (await self._request("GET", "/decisions", params=params)).json()
        if not rows:
            return
        await self._request(
            "PATCH", "/decisions", params={"id": f"eq.{decision_id}"}, headers={"Prefer": "return=minimal"},
            json={"cited_count": int(rows[0]["cited_count"]) + 1, "last_cited_at": datetime.now().astimezone().isoformat()},
        )  # fmt: skip
