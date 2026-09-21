"""MCP 기록의 누락과 수위를 잰다

같은 기간의 두 집합을 맞춘다:
- MCP: 세션의 LLM이 record_decision 으로 보낸 것 (origin=mcp, 서버에서 pull)
- 로컬: 원문에서 추출해 사람이 확정한 것 (origin=session, $PIT_HOME/decisions)

짝은 인용문으로 맞춘다 — MCP 기록의 human_quote 가 로컬 결정의 human_quote 와
겹치고(부분 문자열 어느 쪽이든) 시각이 가까우면 같은 결정으로 본다.
보고값은 문장이 아니라 값이다. 사전 선언한 기준과 비교해 통과 여부를 낸다.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from pydantic import BaseModel

from pit.decisions.models import Decision, DecisionOrigin, Verdict

MATCH_WINDOW = timedelta(hours=6)
MIN_QUOTE_CHARS = 8

# 사전 선언 기준 (계획 P7)
GATE_MIN_RECALL = 0.60
GATE_MIN_REJECT_RECALL = 0.50
GATE_MIN_VERDICT_AGREEMENT = 0.85


class McpRecord(BaseModel):
    """서버에서 내려받은 MCP 기록 중 대조에 쓰는 부분"""

    id: str
    verdict: str | None
    human_quote: str
    decided_at: datetime


@dataclass
class AuditReport:
    period_start: datetime | None
    period_end: datetime | None
    local_total: int
    mcp_total: int
    matched: int
    local_reject_total: int
    matched_reject: int
    verdict_agree: int
    verdict_pairs: int
    unmatched_local_ids: list[str] = field(default_factory=list)

    @property
    def recall(self) -> float | None:
        return self.matched / self.local_total if self.local_total else None

    @property
    def reject_recall(self) -> float | None:
        return self.matched_reject / self.local_reject_total if self.local_reject_total else None

    @property
    def verdict_agreement(self) -> float | None:
        return self.verdict_agree / self.verdict_pairs if self.verdict_pairs else None

    @property
    def gate_checks(self) -> dict[str, bool | None]:
        def check(value: float | None, minimum: float) -> bool | None:
            return None if value is None else value >= minimum

        return {
            "recall": check(self.recall, GATE_MIN_RECALL),
            "reject_recall": check(self.reject_recall, GATE_MIN_REJECT_RECALL),
            "verdict_agreement": check(self.verdict_agreement, GATE_MIN_VERDICT_AGREEMENT),
        }

    def as_dict(self) -> dict[str, object]:
        return {
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "local_total": self.local_total,
            "mcp_total": self.mcp_total,
            "matched": self.matched,
            "recall": self.recall,
            "local_reject_total": self.local_reject_total,
            "matched_reject": self.matched_reject,
            "reject_recall": self.reject_recall,
            "verdict_pairs": self.verdict_pairs,
            "verdict_agree": self.verdict_agree,
            "verdict_agreement": self.verdict_agreement,
            "gate": self.gate_checks,
            "unmatched_local_ids": self.unmatched_local_ids,
        }


def _normalize(text: str) -> str:
    return " ".join(text.split()).lower()


def quotes_overlap(a: str, b: str) -> bool:
    a, b = _normalize(a), _normalize(b)
    if len(a) < MIN_QUOTE_CHARS or len(b) < MIN_QUOTE_CHARS:
        return a == b and bool(a)
    return a in b or b in a


def match(local: list[Decision], mcp: list[McpRecord]) -> dict[str, McpRecord]:
    """로컬 결정 id → 짝이 된 MCP 기록. 한 MCP 기록은 한 번만 쓰인다."""
    pairs: dict[str, McpRecord] = {}
    taken: set[str] = set()
    for decision in sorted(local, key=lambda d: d.decided_at):
        candidates = [
            record
            for record in mcp
            if record.id not in taken
            and abs(record.decided_at - decision.decided_at) <= MATCH_WINDOW
            and quotes_overlap(record.human_quote, decision.human_quote)
        ]
        if candidates:
            best = min(candidates, key=lambda r: abs(r.decided_at - decision.decided_at))
            pairs[decision.id] = best
            taken.add(best.id)
    return pairs


def audit(local: list[Decision], mcp: list[McpRecord], since: datetime | None = None) -> AuditReport:
    """확정된 로컬 결정(origin=session)을 기준으로 MCP 기록의 재현율과 판정 일치율을 낸다"""
    local = [
        d for d in local
        if d.review is not None and d.origin is DecisionOrigin.SESSION and (since is None or d.decided_at >= since)
    ]  # fmt: skip
    mcp = [r for r in mcp if since is None or r.decided_at >= since]
    pairs = match(local, mcp)

    rejects = [d for d in local if d.verdict is Verdict.REJECT]
    verdict_pairs = [(d, pairs[d.id]) for d in local if d.id in pairs and d.verdict is not None]
    times = [d.decided_at for d in local] + [r.decided_at for r in mcp]

    return AuditReport(
        period_start=min(times) if times else None,
        period_end=max(times) if times else None,
        local_total=len(local),
        mcp_total=len(mcp),
        matched=len(pairs),
        local_reject_total=len(rejects),
        matched_reject=sum(1 for d in rejects if d.id in pairs),
        verdict_agree=sum(1 for d, r in verdict_pairs if r.verdict == d.verdict.value),
        verdict_pairs=len(verdict_pairs),
        unmatched_local_ids=[d.id for d in local if d.id not in pairs],
    )
