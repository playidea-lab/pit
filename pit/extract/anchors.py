"""LLM이 돌려준 색인을 실제 이벤트로 되짚고 검증한다

LLM은 [A12], [H13] 같은 색인만 말한다. 색인이 실제로 있는지, 제안이 판정보다
앞인지, 인용이 정말 그 사람의 말인지를 코드가 확인한다. 하나라도 어기면 버린다.
"""

from dataclasses import dataclass

from pydantic import BaseModel

from pit.decisions.models import RejectKind, Verdict
from pit.transcripts.records import Event, EventKind
from pit.transcripts.view import ConversationView


class RawPairLabel(BaseModel):
    """LLM이 (제안, 판정) 쌍 하나에 붙인 라벨"""

    proposal_label: str
    verdict_label: str
    verdict: Verdict
    reject_kind: RejectKind | None = None
    situation: str
    proposal: str
    rationale: str = ""
    human_quote: str


@dataclass(frozen=True)
class AnchorResult:
    proposal: Event | None = None
    verdict: Event | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _normalize(text: str) -> str:
    return " ".join(text.split())


def resolve_anchor(view: ConversationView, raw: RawPairLabel) -> AnchorResult:
    proposal = view.by_label.get(raw.proposal_label.strip("[]"))
    verdict = view.by_label.get(raw.verdict_label.strip("[]"))

    if proposal is None or verdict is None:
        return AnchorResult(error="unknown_label")
    if verdict.kind is not EventKind.HUMAN:
        return AnchorResult(error="verdict_not_human")
    if proposal.kind is not EventKind.ASSISTANT:
        return AnchorResult(error="proposal_not_assistant")
    if proposal.line_no >= verdict.line_no:
        return AnchorResult(error="proposal_after_verdict")
    if not raw.human_quote.strip() or _normalize(raw.human_quote) not in _normalize(verdict.text):
        return AnchorResult(error="quote_not_in_utterance")
    return AnchorResult(proposal=proposal, verdict=verdict)
