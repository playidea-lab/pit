"""세션 파일 → 대화 이벤트 목록

채택하는 레코드는 user · assistant · 사람이 끼어든 attachment 셋뿐이다(allow-list).
세션 제목, 마지막 프롬프트, 부재 요약 같은 레코드에는 '나중에 일어난 일'이 담겨 있고
timestamp도 없어서, 빼는 목록으로는 안전을 보장할 수 없다.
"""

from collections.abc import Callable, Iterable
from datetime import timedelta
from pathlib import Path

from pit.transcripts.classify import classify_user, content_text, queued_human_text, record_time
from pit.transcripts.reader import ReadStats, iter_records
from pit.transcripts.records import (
    ChoiceOption,
    ChoiceQuestion,
    Event,
    EventKind,
    JsonValue,
    RawRecord,
    UserKind,
)

ASK_USER_QUESTION = "AskUserQuestion"
USER_REJECTED = "user-rejected"
TOOL_INPUT_SUMMARY_CHARS = 400


class EventBuilder:
    """레코드를 순서대로 받아 이벤트를 쌓는다"""

    def __init__(self) -> None:
        self.events: list[Event] = []
        self._assistant_by_message: dict[str, Event] = {}
        # tool_use id → (도구 이름, 입력 요약). 거부된 호출이 무엇이었는지 찾는 데 쓴다.
        self._tool_uses: dict[str, tuple[str, str]] = {}

    def feed(self, record: RawRecord) -> None:
        if record.data.get("isSidechain") is True:
            return
        if record.type == "assistant":
            self._feed_assistant(record)
        elif record.type == "user":
            self._feed_user(record)
        elif record.type == "attachment":
            self._feed_attachment(record)

    def _feed_assistant(self, record: RawRecord) -> None:
        message = record.data.get("message")
        if not isinstance(message, dict):
            return
        content = message.get("content")
        self._remember_tool_uses(content)

        text = content_text(content).strip()
        if not text:
            return
        # 한 메시지가 여러 레코드로 쪼개져 온다 → message.id로 이어 붙인다
        message_id = message.get("id") if isinstance(message.get("id"), str) else None
        existing = self._assistant_by_message.get(message_id) if message_id else None
        if existing is not None:
            existing.text = f"{existing.text}\n{text}"
            return

        event = self._append(EventKind.ASSISTANT, record, text=text, message_id=message_id)
        if message_id:
            self._assistant_by_message[message_id] = event

    def _feed_user(self, record: RawRecord) -> None:
        kind = classify_user(record)
        message = record.data.get("message")
        content = message.get("content") if isinstance(message, dict) else None

        if kind is UserKind.HUMAN:
            interrupted = record.data.get("interruptedMessageId")
            self._append_human(
                record,
                content_text(content).strip(),
                interrupted_message_id=interrupted if isinstance(interrupted, str) else None,
            )
        elif kind is UserKind.INTERRUPT:
            self._append(EventKind.INTERRUPT, record, text=content_text(content).strip())
        elif kind is UserKind.TOOL_RESULT:
            self._feed_tool_result(record, content)

    def _feed_attachment(self, record: RawRecord) -> None:
        text = queued_human_text(record)
        if text is not None:
            self._append_human(record, text, queued=True)

    def _feed_tool_result(self, record: RawRecord, content: JsonValue) -> None:
        result = record.data.get("toolUseResult")
        if isinstance(result, dict) and isinstance(result.get("answers"), dict):
            questions = _parse_questions(result.get("questions"))
            answers = {str(q): str(a) for q, a in result["answers"].items()}
            if questions and answers:
                self._append(EventKind.CHOICE, record, questions=questions, answers=answers)
            return

        if record.data.get("toolDenialKind") == USER_REJECTED:
            name, summary = self._tool_uses.get(_first_tool_use_id(content) or "", ("", ""))
            self._append(EventKind.DENIAL, record, text=summary, tool_name=name or None)

    def _remember_tool_uses(self, content: JsonValue) -> None:
        if not isinstance(content, list):
            return
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tool_id, name = block.get("id"), block.get("name")
                if isinstance(tool_id, str) and isinstance(name, str):
                    summary = str(block.get("input", ""))[:TOOL_INPUT_SUMMARY_CHARS]
                    self._tool_uses[tool_id] = (name, summary)

    def _append_human(self, record: RawRecord, text: str, **fields: object) -> None:
        # 끼어든 발화가 attachment와 user 레코드 양쪽에 남는 경우를 대비한 중복 방지
        last_human = next((e for e in reversed(self.events) if e.kind is EventKind.HUMAN), None)
        if last_human is not None and last_human.text == text:
            return
        self._append(EventKind.HUMAN, record, text=text, **fields)

    def _append(self, kind: EventKind, record: RawRecord, **fields: object) -> Event:
        event = Event(
            kind=kind,
            uuid=record.uuid or f"line-{record.line_no}",
            line_no=record.line_no,
            timestamp=record_time(record.data),
            **fields,
        )
        self.events.append(event)
        return event


def build_events(path: Path, stats: ReadStats | None = None) -> list[Event]:
    """세션 파일 하나를 대화 이벤트 목록으로 바꾼다"""
    builder = EventBuilder()
    for record in iter_records(path, stats):
        builder.feed(record)
    return builder.events


# 도구 이름(manifest의 tool) → 그 도구의 세션 파일을 이벤트로 바꾸는 함수.
# 이벤트 모델 이후의 단계는 도구를 모른다.
EVENT_BUILDERS: dict[str, Callable[[Path, ReadStats | None], list[Event]]] = {
    "claude-code": build_events,
}


def split_segments(events: Iterable[Event], idle_gap: timedelta) -> list[list[Event]]:
    """유휴 시간이 길면 다른 작업으로 보고 나눈다

    세션 파일 하나가 수십 일에 걸쳐 이어지므로 '세션'은 맥락의 단위가 못 된다.
    """
    segments: list[list[Event]] = []
    current: list[Event] = []
    last_time = None
    for event in events:
        if (
            current
            and event.timestamp is not None
            and last_time is not None
            and event.timestamp - last_time > idle_gap
        ):
            segments.append(current)
            current = []
        current.append(event)
        if event.timestamp is not None:
            last_time = event.timestamp
    if current:
        segments.append(current)
    return segments


def _parse_questions(raw: JsonValue) -> list[ChoiceQuestion]:
    if not isinstance(raw, list):
        return []
    questions = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("question"), str):
            continue
        options = [
            ChoiceOption(label=str(opt.get("label", "")), description=str(opt.get("description", "")))
            for opt in item.get("options") or []
            if isinstance(opt, dict)
        ]
        questions.append(
            ChoiceQuestion(
                question=item["question"],
                options=options,
                multi_select=item.get("multiSelect") is True,
            )
        )
    return questions


def _first_tool_use_id(content: JsonValue) -> str | None:
    if not isinstance(content, list):
        return None
    for block in content:
        if isinstance(block, dict) and isinstance(block.get("tool_use_id"), str):
            return block["tool_use_id"]
    return None
