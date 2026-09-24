"""판단 그래프 쓰기 (G2, docs/GRAPH_ENGINEERING.md)

결정 하나가 기록될 때 그 결정이 매달리는 노드(주제·프로젝트·산출물)를 찾거나 만들고,
다른 결정과의 관계를 잇는다. 노드는 결정 없이 생기지 않는다 — 그래프는 판단에 매달린다(D-0009 §5).
"""

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from pit.server.conflicts import conflict_candidates
from pit.server.records import SUMMARY_CHARS, LinkRef, NodeRef, StoredDecision, is_team_shared
from pit.server.repository import DecisionRepository
from pit.transcripts.redact import RedactionRules, redact

VISIBILITY_TEAM = "team"
KIND_PROJECT = "project"
# 비교용 이름에서 뺄 문자 — PostgREST 필터 문법과 부딪히는 것들. DB의 norm_name 과 같은 규칙이어야 한다.
_NAME_SYNTAX = re.compile(r'[,(){}"\\*%]')
# 모델이 판정을 확인하지 않고 주장한 충돌은 후보로만 둔다 — 사람이 정리함에서 확인한다
# cites = 남의 판단이 이 결정의 근거가 됨 (세션 AI가 실제로 기댄 것만 보낸다 — 확인된 엣지)
LINK_STATUS = {"depends_on": "confirmed", "conflicts_with": "proposed", "cites": "confirmed"}
# 충돌을 찾을 때 훑는 이웃 결정 수와, 한 번에 올리는 후보 수
CONFLICT_SCAN_LIMIT = 60
MAX_CONFLICTS = 3


def normalize_node_name(name: str) -> str:
    """같은 주제를 같은 이름으로 — 유니코드 정규화 · 소문자 · 공백 하나 · 필터 문법 문자 제거"""
    folded = unicodedata.normalize("NFKC", name).lower()
    return " ".join(_NAME_SYNTAX.sub(" ", folded).split())


@dataclass(frozen=True)
class Namespace:
    """노드 이름 공간: 팀 결정이면 팀이 공유하고, 아니면 그 사람 것이다"""

    team_id: str | None
    owner_github_id: int | None

    @classmethod
    def of(cls, decision: StoredDecision) -> "Namespace":
        if decision.visibility == VISIBILITY_TEAM and decision.team_id:
            return cls(team_id=decision.team_id, owner_github_id=None)
        return cls(team_id=None, owner_github_id=decision.owner_github_id)


@dataclass
class GraphWriter:
    repository: DecisionRepository
    # 호출자가 이 결정을 읽을 수 있는가 — 링크와 충돌 후보가 권한 밖을 가리키지 못하게
    readable: Callable[[StoredDecision], bool]

    async def _can_link_to(self, decision_id: str) -> bool:
        target = await self.repository.get_by_id(decision_id)
        return target is not None and self.readable(target)

    async def attach(
        self, decision: StoredDecision, about: list[NodeRef], project: str | None, links: list[LinkRef]
    ) -> dict[str, object]:
        """노드를 찾거나 만들어 매달고, 링크를 잇는다. MCP 기록과 로컬 push 가 같은 규약으로 부른다.
        결과는 도구 응답에 싣는 짧은 요약."""
        rules = RedactionRules()
        refs = [(ref.kind, redact(ref.name, rules).text) for ref in about]
        if project:
            refs.append((KIND_PROJECT, redact(project, rules).text))
        namespace = Namespace.of(decision)
        node_ids: list[str] = []
        topics: list[str] = []
        for kind, name in dict.fromkeys(refs):
            norm = normalize_node_name(name)
            if not norm:
                continue
            node_id = await self.repository.resolve_node(namespace, kind, name.strip(), norm, decision.owner_github_id)
            if node_id not in node_ids:
                node_ids.append(node_id)
                topics.append(name.strip())
        await self.repository.attach_nodes(decision.id, node_ids)

        linked, skipped = [], []
        for link in links:
            if link.to != decision.id and await self._can_link_to(link.to):
                linked.append((link.to, link.relation, LINK_STATUS[link.relation]))
            else:
                skipped.append(link.to)
        await self.repository.add_links(decision.id, linked, decision.owner_github_id)
        conflicts = await self._propose_conflicts(decision, node_ids, {to for to, _, _ in linked})
        # 빈 값은 싣지 않는다 — 도구 응답은 세션 컨텍스트에 남는다
        summary: dict[str, object] = {}
        if topics:
            summary["topics"] = topics
        if linked:
            summary["links"] = len(linked)
        if skipped:
            summary["links_skipped"] = skipped
        if conflicts:
            summary["possible_conflicts"] = conflicts
        return summary

    async def _propose_conflicts(self, decision: StoredDecision, node_ids: list[str], already: set[str]) -> list[str]:
        """같은 노드의 결정 중 반대로 판정된 것을 충돌 후보로 올린다 (G5) — 볼 수 있는 것만"""
        if not node_ids:
            return []
        neighbor_ids = await self.repository.decision_ids_on_nodes(node_ids, CONFLICT_SCAN_LIMIT)
        neighbors = [d for d in await self.repository.get_many(neighbor_ids) if self.readable(d)]
        found = [c for c in conflict_candidates(decision, neighbors) if c not in already][:MAX_CONFLICTS]
        await self.repository.add_links(
            decision.id, [(other, "conflicts_with", "proposed") for other in found], decision.owner_github_id
        )
        return found


@dataclass
class GraphReader:
    """그래프로 넓혀 읽는다 (G4). readable 은 호출자가 이 결정을 볼 수 있는가 — 저장소는 service_role 이라 여기서 거른다."""

    repository: DecisionRepository
    readable: Callable[[StoredDecision], bool]

    async def topic_hits(self, team_ids: list[str], owner_github_id: int, query: str, limit: int) -> list[StoredDecision]:
        """질의가 노드 이름에 걸리면, 그 노드에 매달린 결정들 — 본문에 그 단어가 없어도 같은 주제면 나온다"""
        node_ids = await self.repository.find_nodes(team_ids, owner_github_id, normalize_node_name(query), limit)
        decision_ids = await self.repository.decision_ids_on_nodes(node_ids, limit * 3)
        return [d for d in await self.repository.get_many(decision_ids) if self.readable(d)][:limit]

    async def related(self, decision_id: str) -> list[dict[str, object]]:
        """이 결정과 링크로 이어진 결정들 (볼 수 있는 것만) — 방향·관계·짧은 제안"""
        links = await self.repository.links_of(decision_id)
        other = {(to if frm == decision_id else frm): (rel, status, "out" if frm == decision_id else "in")
                 for frm, to, rel, status in links}  # fmt: skip
        found = {d.id: d for d in await self.repository.get_many(list(other)) if self.readable(d)}
        return [
            {"id": other_id, "relation": rel, "direction": direction, "status": status,
             "proposal": found[other_id].proposal[:SUMMARY_CHARS]}
            for other_id, (rel, status, direction) in other.items() if other_id in found
        ]  # fmt: skip


def readable_for(github_id: int, teams: dict[str, str], now: datetime) -> Callable[[StoredDecision], bool]:
    """이 사람이 볼 수 있는 결정인가 — 본인 것(버린 것 제외), 또는 속한 팀에 보인 것. DB의 can_see_decision 과 같은 규칙."""

    def readable(decision: StoredDecision) -> bool:
        if decision.owner_github_id == github_id:
            return decision.status != "discarded"
        return decision.team_id in teams and is_team_shared(decision, now)

    return readable
