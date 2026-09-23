"""판단 그래프의 Supabase(PostgREST) 저장 — SupabaseRepository 가 섞어 쓴다 (G2·G4)

service_role 로 부르므로 RLS가 없다. 누가 무엇을 볼 수 있는지는 호출하는 도구(tools.py)가 거른다.
"""

from typing import TYPE_CHECKING

import httpx

from pit.server.errors import RepositoryError
from pit.server.records import StoredDecision

if TYPE_CHECKING:
    from pit.server.graph import Namespace


def _quoted_in(values: list[str]) -> str:
    return "in.(" + ",".join(f'"{value}"' for value in values) + ")"


class SupabaseGraphMixin:
    async def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response: ...  # SupabaseRepository 가 채운다

    def _namespace_params(self, namespace: "Namespace") -> dict[str, str]:
        if namespace.team_id:
            return {"team_id": f"eq.{namespace.team_id}"}
        return {"team_id": "is.null", "owner_github_id": f"eq.{namespace.owner_github_id}"}

    async def _find_node(self, namespace: "Namespace", kind: str, norm: str) -> str | None:
        params = {
            **self._namespace_params(namespace),
            "kind": f"eq.{kind}",
            "merged_into": "is.null",
            "or": f'(norm_name.eq."{norm}",aliases.cs.{{"{norm}"}})',
            "select": "id",
            "limit": "1",
        }
        rows = (await self._request("GET", "/nodes", params=params)).json()
        return str(rows[0]["id"]) if rows else None

    async def resolve_node(self, namespace: "Namespace", kind: str, name: str, norm: str, created_by: int) -> str:
        found = await self._find_node(namespace, kind, norm)
        if found:
            return found
        try:
            response = await self._request(
                "POST", "/nodes", headers={"Prefer": "return=representation"},
                json={"team_id": namespace.team_id, "owner_github_id": namespace.owner_github_id, "kind": kind,
                      "name": name, "norm_name": norm, "created_by": created_by},
            )  # fmt: skip
        except RepositoryError:
            # 다른 세션이 같은 순간 같은 노드를 만들었으면 유일 인덱스가 막는다 — 그것을 쓴다
            found = await self._find_node(namespace, kind, norm)
            if found:
                return found
            raise
        return str(response.json()[0]["id"])

    async def attach_nodes(self, decision_id: str, node_ids: list[str]) -> None:
        if not node_ids:
            return
        await self._request(
            "POST", "/decision_nodes", params={"on_conflict": "decision_id,node_id,relation"},
            headers={"Prefer": "resolution=ignore-duplicates,return=minimal"},
            json=[{"decision_id": decision_id, "node_id": node_id} for node_id in node_ids],
        )  # fmt: skip

    async def add_links(self, from_decision: str, links: list[tuple[str, str, str]], created_by: int) -> None:
        if not links:
            return
        await self._request(
            "POST", "/decision_links", params={"on_conflict": "from_decision,to_decision,relation"},
            headers={"Prefer": "resolution=ignore-duplicates,return=minimal"},
            json=[{"from_decision": from_decision, "to_decision": to, "relation": relation, "status": status,
                   "created_by": created_by} for to, relation, status in links],
        )  # fmt: skip

    async def topics_of(self, decision_ids: list[str]) -> dict[str, list[str]]:
        if not decision_ids:
            return {}
        ids = ",".join(f'"{decision_id}"' for decision_id in decision_ids)
        params = {"decision_id": f"in.({ids})", "select": "decision_id,nodes(name)"}
        rows = (await self._request("GET", "/decision_nodes", params=params)).json()
        topics: dict[str, list[str]] = {}
        for row in rows:
            node = row.get("nodes") or {}
            if node.get("name"):
                topics.setdefault(str(row["decision_id"]), []).append(str(node["name"]))
        return topics

    async def find_nodes(self, team_ids: list[str], owner_github_id: int, norm_query: str, limit: int) -> list[str]:
        if not norm_query:
            return []
        spaces = [f"and(team_id.is.null,owner_github_id.eq.{owner_github_id})"]
        if team_ids:
            spaces.append("team_id.in.(" + ",".join(team_ids) + ")")
        params = {
            "merged_into": "is.null",
            "and": "(or(" + ",".join(spaces) + f'),or(norm_name.ilike."*{norm_query}*",aliases.cs.{{"{norm_query}"}}))',
            "select": "id",
            "limit": str(limit),
        }
        rows = (await self._request("GET", "/nodes", params=params)).json()
        return [str(row["id"]) for row in rows]

    async def decision_ids_on_nodes(self, node_ids: list[str], limit: int) -> list[str]:
        if not node_ids:
            return []
        params = {"node_id": _quoted_in(node_ids), "select": "decision_id", "order": "created_at.desc", "limit": str(limit)}
        rows = (await self._request("GET", "/decision_nodes", params=params)).json()
        return list(dict.fromkeys(str(row["decision_id"]) for row in rows))

    async def get_many(self, decision_ids: list[str]) -> list[StoredDecision]:
        if not decision_ids:
            return []
        rows = (await self._request("GET", "/decisions", params={"id": _quoted_in(decision_ids)})).json()
        return [StoredDecision.model_validate(row) for row in rows]

    async def links_of(self, decision_id: str) -> list[tuple[str, str, str, str]]:
        params = {
            "or": f'(from_decision.eq."{decision_id}",to_decision.eq."{decision_id}")',
            "select": "from_decision,to_decision,relation,status",
        }
        rows = (await self._request("GET", "/decision_links", params=params)).json()
        return [(str(r["from_decision"]), str(r["to_decision"]), str(r["relation"]), str(r["status"])) for r in rows]

    # --- 트윈 (G6) ---

    async def find_account(self, github_login: str) -> tuple[int, bool] | None:
        params = {"github_login": f"eq.{github_login}", "select": "github_id,deleted_at", "limit": "1"}
        rows = (await self._request("GET", "/accounts", params=params)).json()
        return (int(rows[0]["github_id"]), rows[0].get("deleted_at") is not None) if rows else None

    async def team_decisions_of(self, owner_github_id: int, team_ids: list[str], limit: int) -> list[StoredDecision]:
        if not team_ids:
            return []
        params = {
            "owner_github_id": f"eq.{owner_github_id}", "visibility": "eq.team", "status": "neq.discarded",
            "team_id": "in.(" + ",".join(team_ids) + ")", "order": "decided_at.desc", "limit": str(limit),
        }  # fmt: skip
        rows = (await self._request("GET", "/decisions", params=params)).json()
        return [StoredDecision.model_validate(row) for row in rows]

    async def record_consult(
        self, asker: int, twin: int, question: str, decision_ids: list[str], confidence: float, abstained: bool
    ) -> None:
        await self._request(
            "POST", "/consult_log", headers={"Prefer": "return=minimal"},
            json={"asker_github_id": asker, "twin_github_id": twin, "question": question,
                  "decision_ids": decision_ids, "confidence": confidence, "abstained": abstained},
        )  # fmt: skip

    async def create_twin_question(
        self, asker: int, twin: int, team_id: str | None, situation: str, proposal: str, confidence: float
    ) -> None:
        await self._request(
            "POST", "/twin_questions", headers={"Prefer": "return=minimal"},
            json={"asker_github_id": asker, "twin_github_id": twin, "team_id": team_id, "situation": situation,
                  "proposal": proposal, "confidence": confidence},
        )  # fmt: skip

    async def consenting_teams(self, team_ids: list[str]) -> set[str]:
        if not team_ids:
            return set()
        params = {"id": "in.(" + ",".join(team_ids) + ")", "external_judge_consent_at": "not.is.null", "select": "id"}
        return {str(row["id"]) for row in (await self._request("GET", "/teams", params=params)).json()}
