"""개인 결정의 데이터 모델

프로젝트의 .pit/decisions/ (팀 ADR, 제목 + 자유 본문)와는 다른 것이다.
여기의 결정은 한 사람이 LLM의 제안에 내린 판정 하나이고, 트윈의 학습·평가 단위다.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

DECISION_SCHEMA_VERSION = 1
# AskUserQuestion에서 선택지에 없는 답을 직접 입력한 경우
OTHER_CHOICE = "other"


class Verdict(str, Enum):
    """LLM의 제안에 대한 사람의 판정

    '수정'과 '방향 전환'의 경계는 본인도 일관되게 긋기 어렵다. 라벨 잡음은 곧
    측정할 수 있는 일치율의 천장이므로 세 가지로만 나눈다.
    """

    APPROVE = "approve"
    MODIFY = "modify"
    REJECT = "reject"


class RejectKind(str, Enum):
    STOP = "stop"
    REDIRECT = "redirect"


class DecisionKind(str, Enum):
    # 제안에 대한 승인·수정·거부
    VERDICT = "verdict"
    # 제시된 선택지 중 하나를 고름 (우연 기준선이 달라 따로 집계한다)
    CHOICE = "choice"


class DecisionOrigin(str, Enum):
    SESSION = "session"
    # 트윈의 예측을 본 뒤에 사람이 붙인 라벨 — 학습에는 쓰되 평가에서는 뺀다
    TWIN_PREDICTION = "twin_prediction"


class ExtractionMethod(str, Enum):
    STRUCTURED = "structured"
    LLM = "llm"


class ReviewAction(str, Enum):
    CONFIRMED = "confirmed"
    EDITED = "edited"
    DISCARDED = "discarded"


class DecisionSource(BaseModel):
    """원문으로 되돌아가는 닻"""

    tool: str
    device: str
    session_id: str
    cwd: str | None = None
    verdict_uuid: str
    verdict_line_no: int
    proposal_uuid: str | None = None
    proposal_line_no: int | None = None


class ExtractorInfo(BaseModel):
    method: ExtractionMethod
    model: str | None = None
    prompt_hash: str | None = None


class ReviewInfo(BaseModel):
    action: ReviewAction
    edited_fields: list[str] = Field(default_factory=list)
    seconds: float = 0.0
    reviewed_at: datetime


class Decision(BaseModel):
    """결정 하나. review가 없으면 아직 사람이 확인하지 않은 후보다."""

    schema_version: int = DECISION_SCHEMA_VERSION
    id: str
    person: str
    project: str | None = None
    kind: DecisionKind
    origin: DecisionOrigin = DecisionOrigin.SESSION
    decided_at: datetime
    created_at: datetime
    source: DecisionSource

    situation: str = ""
    proposal: str = ""
    verdict: Verdict | None = None
    reject_kind: RejectKind | None = None
    options: list[str] = Field(default_factory=list)
    chosen: str | None = None
    rationale: str = ""
    human_quote: str = ""

    tags: list[str] = Field(default_factory=list)
    # 이 결정이 뒤집은 이전 결정들. 반대 방향(superseded_by)은 읽을 때 파생한다.
    supersedes: list[str] = Field(default_factory=list)
    extractor: ExtractorInfo
    review: ReviewInfo | None = None
