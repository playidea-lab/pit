"""세션 레코드와 대화 이벤트의 타입"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

# JSON 값의 재귀 타입 (any 대신 사용)
JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]


@dataclass(frozen=True)
class RawRecord:
    """JSONL 한 줄. line_no는 파일 안의 1부터 시작하는 줄 번호."""

    line_no: int
    data: JsonObject

    @property
    def type(self) -> str | None:
        value = self.data.get("type")
        return value if isinstance(value, str) else None

    @property
    def uuid(self) -> str | None:
        value = self.data.get("uuid")
        return value if isinstance(value, str) else None


class UserKind(str, Enum):
    """type=="user" 레코드의 실제 정체"""

    HUMAN = "human"
    TOOL_RESULT = "tool_result"
    INJECTED = "injected"
    INTERRUPT = "interrupt"


class EventKind(str, Enum):
    HUMAN = "H"
    ASSISTANT = "A"
    # AskUserQuestion: 선택지(제안)와 고른 답(판정)이 구조화된 채로 남은 경우
    CHOICE = "Q"
    # 사용자가 도구 실행을 거부함
    DENIAL = "D"
    INTERRUPT = "I"


class ChoiceOption(BaseModel):
    label: str
    description: str = ""


class ChoiceQuestion(BaseModel):
    question: str
    options: list[ChoiceOption] = Field(default_factory=list)
    multi_select: bool = False


class Event(BaseModel):
    """결정 추출이 보는 대화의 최소 단위

    원문의 5% 남짓만 남긴 것이다. 도구 입출력은 버리는데, 시크릿 노출면의
    대부분이 거기에 있어서 이 축소가 프라이버시 필터를 겸한다.
    """

    kind: EventKind
    # 원문으로 되돌아갈 닻 (해당 레코드의 uuid와 줄 번호)
    uuid: str
    line_no: int
    timestamp: datetime | None = None
    text: str = ""

    # HUMAN: 에이전트가 일하는 도중에 끼어든 발화인가
    queued: bool = False
    # HUMAN: 이 발화가 중단시킨 assistant 메시지
    interrupted_message_id: str | None = None
    # ASSISTANT
    message_id: str | None = None
    # CHOICE
    questions: list[ChoiceQuestion] = Field(default_factory=list)
    answers: dict[str, str] = Field(default_factory=dict)
    # DENIAL
    tool_name: str | None = None
