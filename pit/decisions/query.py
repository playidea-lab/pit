"""결정 조회와 검토 통계

결정은 저장소가 아니라 사람을 축으로 묶인다. 기본 조회는 프로젝트를 가로지른다.
"""

import math
import random
from dataclasses import dataclass
from datetime import datetime
from statistics import median

from pit.decisions.models import Decision, ExtractionMethod, ReviewAction, Verdict
from pit.decisions.store import ReviewEvent

# 게이트 1: 추출 품질 표본
GATE1_SAMPLE_SIZE = 120
GATE1_MAX_PER_SESSION = 10
GATE1_MAX_STRUCTURED = 30
GATE1_SAMPLE_SEED = 20260922
GATE1_MIN_USABLE_RATE = 0.70
GATE1_MIN_USABLE_WILSON = 0.60
GATE1_MAX_VERDICT_FLIP_RATE = 0.15
GATE1_MAX_MEDIAN_SECONDS = 10.0
GATE1_MAX_P90_SECONDS = 30.0

WILSON_Z_95 = 1.96
P90 = 0.9
# 이 필드를 고쳤다면 추출이 판정 자체를 틀린 것이다
VERDICT_FIELDS = frozenset({"verdict", "chosen"})
MAX_LIGHT_EDIT_FIELDS = 1


@dataclass(frozen=True)
class DecisionQuery:
    person: str | None = None
    project_contains: str | None = None
    verdict: Verdict | None = None
    since: datetime | None = None
    text: str | None = None


def filter_decisions(decisions: list[Decision], query: DecisionQuery) -> list[Decision]:
    def matches(decision: Decision) -> bool:
        if query.person and decision.person != query.person:
            return False
        if query.project_contains and query.project_contains not in (decision.project or ""):
            return False
        if query.verdict and decision.verdict is not query.verdict:
            return False
        if query.since and decision.decided_at < query.since:
            return False
        if query.text:
            haystack = " ".join(
                [decision.situation, decision.proposal, decision.rationale, decision.human_quote, *decision.tags]
            )
            return query.text.lower() in haystack.lower()
        return True

    return [decision for decision in decisions if matches(decision)]


def sample_for_gate1(candidates: list[Decision]) -> list[Decision]:
    """추출 품질을 볼 표본: 세션 편중과 구조 신호 편중을 막아 뽑는다 (시드 고정)"""
    rng = random.Random(GATE1_SAMPLE_SEED)
    shuffled = sorted(candidates, key=lambda d: d.id)
    rng.shuffle(shuffled)

    per_session: dict[str, int] = {}
    structured = 0
    sample: list[Decision] = []
    for candidate in shuffled:
        session = candidate.source.session_id
        is_structured = candidate.extractor.method is ExtractionMethod.STRUCTURED
        if per_session.get(session, 0) >= GATE1_MAX_PER_SESSION:
            continue
        if is_structured and structured >= GATE1_MAX_STRUCTURED:
            continue
        per_session[session] = per_session.get(session, 0) + 1
        structured += is_structured
        sample.append(candidate)
        if len(sample) == GATE1_SAMPLE_SIZE:
            break
    return sample


def wilson_lower_bound(successes: int, total: int) -> float:
    """비율의 95% Wilson 구간 하한 (표본이 작을 때 단순 비율보다 정직하다)"""
    if total == 0:
        return 0.0
    p = successes / total
    z2 = WILSON_Z_95**2
    center = p + z2 / (2 * total)
    margin = WILSON_Z_95 * math.sqrt(p * (1 - p) / total + z2 / (4 * total**2))
    return (center - margin) / (1 + z2 / total)


@dataclass(frozen=True)
class ReviewStats:
    reviewed: int
    usable_rate: float
    usable_wilson_lower: float
    verdict_flip_rate: float
    median_seconds: float
    p90_seconds: float

    @property
    def gate1_checks(self) -> dict[str, bool]:
        """게이트 1의 조건별 통과 여부 (문장이 아니라 값으로 판정한다)"""
        return {
            "usable_rate": self.usable_rate >= GATE1_MIN_USABLE_RATE,
            "usable_wilson_lower": self.usable_wilson_lower >= GATE1_MIN_USABLE_WILSON,
            "verdict_flip_rate": self.verdict_flip_rate <= GATE1_MAX_VERDICT_FLIP_RATE,
            "median_seconds": self.median_seconds <= GATE1_MAX_MEDIAN_SECONDS,
            "p90_seconds": self.p90_seconds <= GATE1_MAX_P90_SECONDS,
        }


def _is_usable(event: ReviewEvent) -> bool:
    review = event.review
    if review.action is ReviewAction.CONFIRMED:
        return True
    if review.action is ReviewAction.DISCARDED:
        return False
    fields = set(review.edited_fields)
    return len(fields) <= MAX_LIGHT_EDIT_FIELDS and not fields & VERDICT_FIELDS


def review_stats(events: list[ReviewEvent]) -> ReviewStats | None:
    if not events:
        return None
    total = len(events)
    usable = sum(1 for event in events if _is_usable(event))
    flips = sum(1 for event in events if set(event.review.edited_fields) & VERDICT_FIELDS)
    seconds = sorted(event.review.seconds for event in events)
    return ReviewStats(
        reviewed=total,
        usable_rate=usable / total,
        usable_wilson_lower=wilson_lower_bound(usable, total),
        verdict_flip_rate=flips / total,
        median_seconds=median(seconds),
        p90_seconds=seconds[min(total - 1, math.ceil(P90 * total) - 1)],
    )
