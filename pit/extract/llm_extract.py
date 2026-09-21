"""LLM으로 (제안, 판정) 쌍에 라벨을 붙인다"""

import hashlib
import logging
from importlib import resources
from pathlib import Path

from pydantic import BaseModel, ValidationError

from pit.extract.anchors import RawPairLabel
from pit.llm.client import LLMClient, StructuredRequest
from pit.loaders.prompts import load_prompt
from pit.transcripts.records import Event, EventKind, JsonObject
from pit.transcripts.view import ConversationView, render_event

logger = logging.getLogger(__name__)

EXTRACT_PROMPT_NAME = "extract-decisions.md"
PROMPTS_PACKAGE = "pit.twin.prompts"
EXTRACT_TOOL_NAME = "record_decisions"
EXTRACT_MAX_TOKENS = 4096
PROMPT_HASH_CHARS = 12
# 판정 발화 직전의 assistant 글 몇 개만 본다. 그 앞의 글은 사람이 반응한 대상이 아니다.
PROPOSAL_TAIL_MESSAGES = 2
MAX_WINDOW_CHARS = 40_000
SCHEMA_RETRIES = 1

EXTRACT_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "proposal_label": {"type": "string"},
                    "verdict_label": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["approve", "modify", "reject"]},
                    "reject_kind": {"type": ["string", "null"], "enum": ["stop", "redirect", None]},
                    "situation": {"type": "string"},
                    "proposal": {"type": "string"},
                    "rationale": {"type": "string"},
                    "human_quote": {"type": "string"},
                },
                "required": ["proposal_label", "verdict_label", "verdict", "situation", "proposal", "human_quote"],
            },
        }
    },
    "required": ["decisions"],
}


class _ExtractionPayload(BaseModel):
    decisions: list[RawPairLabel]


def load_extract_prompt(home: Path) -> tuple[str, str]:
    """추출 프롬프트와 그 지문을 돌려준다 ($PIT_HOME/prompts/ 가 패키지 기본값을 덮어쓴다)"""
    override = home / "prompts" / EXTRACT_PROMPT_NAME
    if override.exists():
        prompt = load_prompt(override)
    else:
        # 설치된 패키지 안의 데이터로 읽는다 (소스 트리의 경로에 기대지 않는다)
        with resources.as_file(resources.files(PROMPTS_PACKAGE) / EXTRACT_PROMPT_NAME) as bundled:
            prompt = load_prompt(bundled)
    if prompt is None:
        raise FileNotFoundError(f"추출 프롬프트를 읽을 수 없습니다: {EXTRACT_PROMPT_NAME}")
    digest = hashlib.sha256(prompt.content.encode()).hexdigest()[:PROMPT_HASH_CHARS]
    return prompt.content, digest


def compact_for_extraction(events: list[Event]) -> list[Event]:
    """판정이 될 수 있는 이벤트와, 그 직전의 assistant 글 몇 개만 남긴다"""
    kept: list[Event] = []
    pending: list[Event] = []
    for event in events:
        if event.kind is EventKind.ASSISTANT:
            pending.append(event)
            continue
        kept.extend(pending[-PROPOSAL_TAIL_MESSAGES:])
        kept.append(event)
        pending = []
    return kept


def split_windows(events: list[Event], max_chars: int = MAX_WINDOW_CHARS) -> list[list[Event]]:
    """한 번의 호출에 넣을 크기로 나눈다. (assistant 글 + 그에 대한 반응) 묶음은 쪼개지 않는다."""
    windows: list[list[Event]] = []
    current: list[Event] = []
    group: list[Event] = []
    size = 0
    for event in events:
        group.append(event)
        if event.kind is EventKind.ASSISTANT:
            continue
        group_size = sum(len(render_event(e)) for e in group)
        if current and size + group_size > max_chars:
            windows.append(current)
            current, size = [], 0
        current.extend(group)
        size += group_size
        group = []
    if current:
        windows.append(current)
    return windows


def extract_with_llm(
    view: ConversationView, client: LLMClient, system_prompt: str, model_id: str
) -> list[RawPairLabel]:
    """뷰 하나에서 라벨을 받는다. 구조가 틀리면 한 번 더 시도하고, 그래도 틀리면 예외.

    Raises:
        LLMError: 호출 자체가 실패함
        ValidationError: 재시도 후에도 약속한 구조가 아님
    """
    request = StructuredRequest(
        model=model_id,
        system=system_prompt,
        user=view.text,
        tool_name=EXTRACT_TOOL_NAME,
        tool_description="대화에서 찾은 결정 지점을 기록한다",
        schema=EXTRACT_SCHEMA,
        max_tokens=EXTRACT_MAX_TOKENS,
    )
    for attempt in range(SCHEMA_RETRIES + 1):
        payload = client.complete_structured(request)
        try:
            return _ExtractionPayload.model_validate(payload).decisions
        except ValidationError as e:
            if attempt == SCHEMA_RETRIES:
                raise
            logger.warning("추출 응답의 구조가 틀려 재시도", extra={"errors": e.error_count()})
    return []
