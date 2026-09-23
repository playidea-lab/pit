"""충돌 후보 찾기 (G5, docs/GRAPH_ENGINEERING.md)

같은 주제에 매달린 결정 가운데, 비슷한 제안을 반대로 판정한 것을 찾는다.
규칙으로만 찾고 후보(proposed)로만 올린다 — 확정은 사람이 정리함에서 한다.
보정된 판정기(JEV 등)는 나중에 이 자리에 선택적으로 끼운다.
"""

from pit.server.records import StoredDecision, normalize_text

# 두 제안이 같은 것을 말한다고 볼 글자 쌍 겹침(자카드)의 하한 — 한국어에도 통하도록 글자 단위로 본다
PROPOSAL_SIMILARITY_MIN = 0.35
BIGRAM = 2
# 서로 반대인 판정. 수정(modify)은 반대로 치지 않는다 — 거부와도 승인과도 겹친다.
OPPOSITE_VERDICTS = frozenset({("approve", "reject"), ("reject", "approve")})


def _bigrams(text: str) -> set[str]:
    compact = normalize_text(text).replace(" ", "")
    if len(compact) < BIGRAM:
        return {compact} if compact else set()
    return {compact[i : i + BIGRAM] for i in range(len(compact) - 1)}


def proposal_similarity(a: str, b: str) -> float:
    left, right = _bigrams(a), _bigrams(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _opposite(new: StoredDecision, other: StoredDecision) -> bool:
    if new.verdict and other.verdict:
        return (new.verdict, other.verdict) in OPPOSITE_VERDICTS
    # 선택형끼리: 같은 문제에서 다른 것을 골랐다
    return new.kind == other.kind == "choice" and bool(new.chosen) and bool(other.chosen) and new.chosen != other.chosen


def conflict_candidates(new: StoredDecision, others: list[StoredDecision]) -> list[str]:
    """new 와 충돌하는 것으로 보이는 결정 id — 이미 뒤집기로 이어진 쌍은 빼고, 비슷한 순서로"""
    scored = []
    for other in others:
        if other.id == new.id or other.status == "discarded":
            continue
        if other.id in new.supersedes or new.id in other.supersedes:
            continue
        if not _opposite(new, other):
            continue
        similarity = proposal_similarity(new.proposal, other.proposal)
        if similarity >= PROPOSAL_SIMILARITY_MIN:
            scored.append((similarity, other.id))
    return [decision_id for _, decision_id in sorted(scored, reverse=True)]
