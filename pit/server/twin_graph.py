"""트윈의 근거를 판단 그래프로 모은다 (그래프 B)

질문이 가리키는 노드를 찾고, 그 노드에 매달린 그 사람의 결정과 링크로 한 단계 이어진 결정을 근거로 삼는다.
주제·산출물이 프로젝트보다 먼저다 — 프로젝트는 너무 넓다. 그래프에 근거가 없으면 빈 목록을 돌려주고,
호출자는 글자 유사도로 물러난다.
"""

from pit.server.graph import normalize_node_name
from pit.server.records import StoredDecision
from pit.server.repository import DecisionRepository

BASIS_GRAPH, BASIS_TEXT = "graph", "text"
# 좁은 것부터: 주제·산출물이 맞으면 프로젝트는 보지 않는다
KIND_TIERS = (("topic", "artifact"), ("project",))
# 이름이 질의 안에 들어 있는 것으로 볼 최소 길이 — 한두 글자 이름이 아무 데나 걸리지 않게
MIN_NAME_CHARS = 2
# 링크를 따라갈 근거 결정 수 상한
HOP_SEEDS = 10


def _named(norm_name: str, query: str, about: set[str]) -> bool:
    return norm_name in about or (len(norm_name) >= MIN_NAME_CHARS and norm_name in query)


async def graph_evidence(
    repository: DecisionRepository, pool: list[StoredDecision], query: str, about: list[str]
) -> tuple[list[StoredDecision], list[str]]:
    """(근거 결정, 맞은 노드 이름). pool 은 이미 묻는 사람이 볼 수 있는 그 사람의 결정만이다."""
    refs = await repository.node_refs_of([d.id for d in pool])
    norm_query = normalize_node_name(query)
    wanted = {normalize_node_name(name) for name in about if name.strip()}
    for kinds in KIND_TIERS:
        seeds, matched = set(), []
        for decision_id, nodes in refs.items():
            for kind, name in nodes:
                if kind in kinds and _named(normalize_node_name(name), norm_query, wanted):
                    seeds.add(decision_id)
                    if name not in matched:
                        matched.append(name)
        if seeds:
            by_id = {d.id: d for d in pool}
            linked = await _one_hop(repository, sorted(seeds)[:HOP_SEEDS], set(by_id))
            return [by_id[i] for i in by_id if i in seeds | linked], matched
    return [], []


async def _one_hop(repository: DecisionRepository, seeds: list[str], allowed: set[str]) -> set[str]:
    """링크로 이어진 결정 중 같은 근거 풀(볼 수 있는 그 사람의 결정)에 있는 것"""
    linked: set[str] = set()
    for seed in seeds:
        for frm, to, _relation, _status in await repository.links_of(seed):
            other = to if frm == seed else frm
            if other in allowed:
                linked.add(other)
    return linked
