"""구조에서 바로 읽히는 결정 (LLM 없이)

선택지 질문에는 '제시된 선택지'와 '고른 답'이, 도구 거부에는 '하려던 일'과
'막았다는 사실'이 값으로 남아 있다. 해석이 필요 없으므로 코드로만 후보를 만든다.
"""

from dataclasses import dataclass
from datetime import datetime

from pit.decisions.ids import make_decision_id
from pit.decisions.models import (
    OTHER_CHOICE,
    Decision,
    DecisionKind,
    DecisionSource,
    ExtractionMethod,
    ExtractorInfo,
    RejectKind,
    Verdict,
)
from pit.transcripts.records import ChoiceQuestion, Event, EventKind
from pit.transcripts.view import clip

MULTI_SELECT_SEPARATOR = ", "
# 거부 직후 몇 이벤트 안에 사람이 이유를 말했으면 그것을 근거로 삼는다
REASON_LOOKAHEAD_EVENTS = 2


@dataclass(frozen=True)
class SourceContext:
    """후보에 찍을 출처 정보"""

    person: str
    tool: str
    device: str
    session_id: str
    cwd: str | None
    now: datetime


def extract_structured(events: list[Event], ctx: SourceContext) -> list[Decision]:
    decisions: list[Decision] = []
    for index, event in enumerate(events):
        if event.kind is EventKind.CHOICE:
            decisions.extend(_from_choice(events, index, ctx))
        elif event.kind is EventKind.DENIAL:
            decisions.append(_from_denial(events, index, ctx))
    return decisions


def _last_assistant_before(events: list[Event], index: int) -> Event | None:
    return next((e for e in reversed(events[:index]) if e.kind is EventKind.ASSISTANT), None)


def _source(ctx: SourceContext, verdict: Event, proposal: Event | None) -> DecisionSource:
    return DecisionSource(
        tool=ctx.tool,
        device=ctx.device,
        session_id=ctx.session_id,
        cwd=ctx.cwd,
        verdict_uuid=verdict.uuid,
        verdict_line_no=verdict.line_no,
        proposal_uuid=proposal.uuid if proposal else None,
        proposal_line_no=proposal.line_no if proposal else None,
    )


def _chosen(question: ChoiceQuestion, answer: str) -> str:
    labels = {option.label for option in question.options}
    if answer in labels:
        return answer
    parts = answer.split(MULTI_SELECT_SEPARATOR)
    if question.multi_select and all(part in labels for part in parts):
        return answer
    return OTHER_CHOICE


def _from_choice(events: list[Event], index: int, ctx: SourceContext) -> list[Decision]:
    event = events[index]
    before = _last_assistant_before(events, index)
    decisions = []
    for part, question in enumerate(event.questions):
        answer = event.answers.get(question.question)
        if answer is None:
            continue
        chosen = _chosen(question, answer)
        decided_at = event.timestamp or ctx.now
        decisions.append(
            Decision(
                id=make_decision_id(ctx.session_id, event.uuid, decided_at, part),
                person=ctx.person,
                project=ctx.cwd,
                kind=DecisionKind.CHOICE,
                decided_at=decided_at,
                created_at=ctx.now,
                source=_source(ctx, event, before),
                situation=clip(before.text) if before else "",
                proposal=question.question,
                options=[option.label for option in question.options],
                chosen=chosen,
                # 선택지 밖의 답은 사람이 직접 쓴 말이다
                human_quote=answer if chosen == OTHER_CHOICE else "",
                extractor=ExtractorInfo(method=ExtractionMethod.STRUCTURED),
            )
        )
    return decisions


def _from_denial(events: list[Event], index: int, ctx: SourceContext) -> Decision:
    event = events[index]
    before = _last_assistant_before(events, index)
    following = events[index + 1 : index + 1 + REASON_LOOKAHEAD_EVENTS]
    reason = next((e for e in following if e.kind is EventKind.HUMAN), None)
    # 이유를 말한 발화가 있으면 그것을 판정의 닻으로 삼는다.
    # LLM 추출이 같은 발화를 또 집어도 같은 verdict_uuid라서 중복이 걸러진다.
    anchor = reason or event
    decided_at = anchor.timestamp or ctx.now

    return Decision(
        id=make_decision_id(ctx.session_id, anchor.uuid, decided_at),
        person=ctx.person,
        project=ctx.cwd,
        kind=DecisionKind.VERDICT,
        decided_at=decided_at,
        created_at=ctx.now,
        source=_source(ctx, anchor, before),
        situation=clip(before.text) if before else "",
        proposal=f"{event.tool_name or '도구'} 실행: {clip(event.text)}",
        verdict=Verdict.REJECT,
        reject_kind=RejectKind.REDIRECT if reason else RejectKind.STOP,
        human_quote=clip(reason.text) if reason else "",
        extractor=ExtractorInfo(method=ExtractionMethod.STRUCTURED),
    )
