"""판단 그래프 쓰기 (G2, docs/GRAPH_ENGINEERING.md)

결정 하나가 기록될 때 그 결정이 매달리는 노드(주제·프로젝트·산출물)를 찾거나 만들고,
다른 결정과의 관계를 잇는다. 노드는 결정 없이 생기지 않는다 — 그래프는 판단에 매달린다(D-0009 §5).
"""

import re
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pit.server.records import RecordDecisionInput, StoredDecision
from pit.server.repository import DecisionRepository
from pit.transcripts.redact import RedactionRules, redact

VISIBILITY_TEAM = "team"
KIND_PROJECT = "project"
# 비교용 이름에서 뺄 문자 — PostgREST 필터 문법과 부딪히는 것들. DB의 norm_name 과 같은 규칙이어야 한다.
_NAME_SYNTAX = re.compile(r'[,(){}"\\*%]')
# 모델이 판정을 확인하지 않고 주장한 충돌은 후보로만 둔다 — 사람이 정리함에서 확인한다
LINK_STATUS = {"depends_on": "confirmed", "conflicts_with": "proposed"}


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
    # 호출자가 이 결정을 읽을 수 있는가 — 남의 결정에 링크를 걸 때 권한 밖을 가리키지 못하게
    can_link_to: Callable[[str], Awaitable[bool]]

    async def attach(self, decision: StoredDecision, payload: RecordDecisionInput) -> dict[str, object]:
        """노드를 찾거나 만들어 매달고, 링크를 잇는다. 결과는 도구 응답에 싣는 짧은 요약."""
        rules = RedactionRules()
        refs = [(ref.kind, redact(ref.name, rules).text) for ref in payload.about]
        if payload.project:
            refs.append((KIND_PROJECT, redact(payload.project, rules).text))
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
        for link in payload.links:
            if link.to != decision.id and await self.can_link_to(link.to):
                linked.append((link.to, link.relation, LINK_STATUS[link.relation]))
            else:
                skipped.append(link.to)
        await self.repository.add_links(decision.id, linked, decision.owner_github_id)
        # 빈 값은 싣지 않는다 — 도구 응답은 세션 컨텍스트에 남는다
        summary: dict[str, object] = {}
        if topics:
            summary["topics"] = topics
        if linked:
            summary["links"] = len(linked)
        if skipped:
            summary["links_skipped"] = skipped
        return summary
