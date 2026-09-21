"""이벤트 목록 → 색인이 붙은 대화 뷰

LLM에게는 uuid가 아니라 [H3], [A4] 같은 색인만 보여 준다. LLM이 색인을 돌려주면
코드가 실제 이벤트로 되짚는다 — uuid를 지어내는 일을 구조적으로 막기 위함이다.
"""

from dataclasses import dataclass, field

from pit.transcripts.records import Event, EventKind

# 붙여넣은 로그 한 덩이가 수십만 자일 수 있다. 앞뒤만 남긴다
# (제안은 글의 끝에, 맥락은 글의 앞에 있는 경우가 많다).
MAX_EVENT_CHARS = 2400
CLIP_HEAD_CHARS = 1400
CLIP_TAIL_CHARS = 900
CLIP_MARKER = "\n[…중략 {omitted}자…]\n"


@dataclass
class ConversationView:
    """렌더된 대화와, 색인에서 이벤트로 되돌아가는 표"""

    lines: list[str] = field(default_factory=list)
    by_label: dict[str, Event] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n\n".join(self.lines)


def clip(text: str) -> str:
    if len(text) <= MAX_EVENT_CHARS:
        return text
    omitted = len(text) - CLIP_HEAD_CHARS - CLIP_TAIL_CHARS
    return text[:CLIP_HEAD_CHARS] + CLIP_MARKER.format(omitted=omitted) + text[-CLIP_TAIL_CHARS:]


def render_event(event: Event) -> str:
    """이벤트 하나의 본문 (색인 제외)"""
    if event.kind is EventKind.CHOICE:
        parts = []
        for question in event.questions:
            labels = " | ".join(option.label for option in question.options)
            answer = event.answers.get(question.question, "")
            parts.append(f"질문: {question.question}\n선택지: {labels}\n고른 답: {answer}")
        return "\n".join(parts)
    if event.kind is EventKind.DENIAL:
        return f"(사용자가 도구 실행을 거부함: {event.tool_name or '알 수 없음'}) {clip(event.text)}"
    if event.kind is EventKind.INTERRUPT:
        return "(사용자가 작업을 중단함)"
    prefix = "(작업 중 끼어듦) " if event.queued else ""
    return prefix + clip(event.text)


def render_view(events: list[Event], start_index: int = 1) -> ConversationView:
    """이벤트에 [종류+번호] 색인을 붙여 렌더한다"""
    view = ConversationView()
    for offset, event in enumerate(events):
        label = f"{event.kind.value}{start_index + offset}"
        view.by_label[label] = event
        view.lines.append(f"[{label}] {render_event(event)}")
    return view
