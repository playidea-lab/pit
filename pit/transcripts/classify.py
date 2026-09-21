"""사람의 실제 발화 가려내기

type=="user" 레코드의 92%는 도구 결과이고 2~3%는 하네스가 주입한 것이다.
사람이 직접 친 것은 5% 미만이다. 판별에 쓸 수 있는 필드가 버전마다 달라서
(promptSource는 7%에만 있다) 필드의 부재를 '아니다'로 읽지 않는다.
"""

from datetime import datetime

from pit.transcripts.records import JsonObject, JsonValue, RawRecord, UserKind

# 하네스가 user 레코드에 끼워 넣는 래퍼. 실측상 래퍼와 사람 글은 별도 레코드다.
HARNESS_TAGS = (
    "system-reminder",
    "command-name",
    "command-message",
    "command-args",
    "local-command-caveat",
    "local-command-stdout",
    "local-command-stderr",
    "user-prompt-submit-hook",
    "bash-input",
    "bash-stdout",
    "bash-stderr",
    "task-notification",
    "channel",
)
INTERRUPT_PREFIX = "[Request interrupted by user"
HUMAN_ORIGIN = "human"
QUEUED_COMMAND = "queued_command"
PROMPT_MODE = "prompt"


def content_text(content: JsonValue) -> str:
    """message.content에서 사람이 읽는 글만 뽑는다 (str과 블록 배열 둘 다 온다)"""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    texts = [
        block["text"]
        for block in content
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
    ]
    return "\n".join(texts)


def has_tool_result(content: JsonValue) -> bool:
    return isinstance(content, list) and any(
        isinstance(block, dict) and block.get("type") == "tool_result" for block in content
    )


def classify_user(record: RawRecord) -> UserKind:
    """user 레코드가 사람의 말인지 판정한다 (규칙의 순서가 곧 우선순위)"""
    data = record.data
    message = data.get("message")
    content = message.get("content") if isinstance(message, dict) else None

    if "toolUseResult" in data or has_tool_result(content):
        return UserKind.TOOL_RESULT
    if data.get("isMeta") is True or data.get("isCompactSummary") is True:
        return UserKind.INJECTED
    if _non_human_origin(data.get("origin")):
        return UserKind.INJECTED

    text = content_text(content).lstrip()
    if text.startswith(INTERRUPT_PREFIX):
        return UserKind.INTERRUPT
    if not text or any(text.startswith(f"<{tag}") for tag in HARNESS_TAGS):
        return UserKind.INJECTED
    return UserKind.HUMAN


def queued_human_text(record: RawRecord) -> str | None:
    """에이전트가 일하는 도중에 사람이 끼어든 발화면 그 글을, 아니면 None

    이런 발화는 user 레코드가 아니라 attachment 레코드로 온다. 같은 종류의
    attachment 대부분은 백그라운드 작업 알림이므로 세 조건을 모두 확인한다.
    """
    attachment = record.data.get("attachment")
    if not isinstance(attachment, dict) or attachment.get("type") != QUEUED_COMMAND:
        return None
    if attachment.get("commandMode") != PROMPT_MODE or attachment.get("isMeta") is True:
        return None
    origin = attachment.get("origin")
    if not isinstance(origin, dict) or origin.get("kind") != HUMAN_ORIGIN:
        return None

    text = content_text(attachment.get("prompt")).strip()
    return text or None


def record_time(data: JsonObject) -> datetime | None:
    raw = data.get("timestamp")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _non_human_origin(origin: JsonValue) -> bool:
    """origin이 있고 사람이 아닐 때만 True. origin이 없으면 판단을 보류한다."""
    return isinstance(origin, dict) and origin.get("kind") not in (None, HUMAN_ORIGIN)
