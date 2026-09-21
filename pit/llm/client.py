"""LLM 클라이언트 규약

추출과 트윈은 이 규약에만 의존한다. 테스트는 가짜 구현을 주입하고,
통제군 비교에서는 같은 구현에 입력만 바꿔 넣는다.
"""

import os
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from pit.transcripts.records import JsonObject


class LLMError(Exception):
    """LLM 호출이 실패했거나 약속한 구조의 값을 돌려주지 않음"""


class ModelTask(str, Enum):
    EXTRACT = "extract"
    TWIN = "twin"


@dataclass(frozen=True)
class StructuredRequest:
    """스키마에 맞는 JSON 하나를 돌려 달라는 요청"""

    model: str
    system: str
    user: str
    tool_name: str
    tool_description: str
    schema: JsonObject
    max_tokens: int


class LLMClient(Protocol):
    def complete_structured(self, request: StructuredRequest) -> JsonObject: ...


def require_model_id(models: dict[str, str], task: ModelTask) -> str:
    """태스크에 쓸 모델 ID를 설정에서 읽는다

    우선순위: 환경변수 PIT_MODEL_<TASK> → twin.yaml 의 models.<task>.
    코드에 기본 모델을 두지 않는다. 통제군 비교에서 모델은 고정·기록되어야 하는
    변수라서, 모르는 사이에 기본값이 바뀌는 일이 없어야 한다.

    Raises:
        LLMError: 어디에도 지정돼 있지 않을 때
    """
    env_name = f"PIT_MODEL_{task.value.upper()}"
    model_id = os.environ.get(env_name) or models.get(task.value)
    if not model_id:
        raise LLMError(
            f"'{task.value}'에 쓸 모델이 지정되지 않았습니다. "
            f"twin.yaml 의 models.{task.value} 또는 환경변수 {env_name} 를 설정하세요."
        )
    return model_id
