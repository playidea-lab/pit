"""MCP로 들어오는 결정의 입력·저장 모델과 가공

서버가 받는 글은 LLM이 쓴 요약이다. 저장하기 전에 반드시 가림 처리를 하고,
같은 결정을 두 번 보내도 한 번만 남도록 중복 키를 만든다.
"""

import hashlib
from collections import Counter
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field, model_validator

from pit.decisions.ids import make_decision_id
from pit.decisions.models import DecisionKind, RejectKind, Verdict
from pit.transcripts.redact import RedactionRules, redact

MAX_TEXT_CHARS = 4000
MAX_OPTIONS = 12
MAX_TAGS = 8
MAX_SUPERSEDES = 5
# 이 기간 안에 같은 프로젝트에 같은 제안이 다시 오면 새 행 대신 반복 횟수를 올린다
REPEAT_WINDOW_DAYS = 7
MAX_TAG_CHARS = 40
DEDUPE_KEY_CHARS = 32
ORIGIN_MCP = "mcp"
# 백필로 넣을 수 있는 과거 시각의 하한. 이보다 오래된 것은 시간 분할 평가에서 의미가 없다.
MAX_BACKDATE = timedelta(days=3 * 365)
# 클라이언트 시계 오차 허용치
MAX_FUTURE_SKEW = timedelta(minutes=10)
# 메모·문서에서 옮긴 기록임을 나타내는 client 값 — 인용문이 실제 발화가 아니므로 감사에서 제외한다
BACKFILL_CLIENTS = frozenset({"claude-memory", "backfill"})


class RecordDecisionInput(BaseModel):
    """record_decision 도구의 입력"""

    situation: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    proposal: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    human_quote: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    verdict: Verdict | None = None
    reject_kind: RejectKind | None = None
    rationale: str = Field(default="", max_length=MAX_TEXT_CHARS)
    options: list[str] = Field(default_factory=list, max_length=MAX_OPTIONS)
    chosen: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
    project: str | None = Field(default=None, max_length=200)
    client: str | None = Field(default=None, max_length=80)
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS)
    # 이 결정이 뒤집는 과거 결정의 id (record 전에 search_my_decisions 로 찾은 것)
    supersedes: list[str] = Field(default_factory=list, max_length=MAX_SUPERSEDES)
    # 과거 결정을 옮길 때만 준다 (메모·문서 백필). 없으면 서버 시각.
    decided_at: datetime | None = None

    @model_validator(mode="after")
    def _verdict_or_choice(self) -> "RecordDecisionInput":
        if self.verdict is None and self.chosen is None:
            raise ValueError("verdict(승인·수정·거부) 또는 chosen(고른 선택지) 중 하나는 있어야 합니다.")
        if self.reject_kind is not None and self.verdict is not Verdict.REJECT:
            raise ValueError("reject_kind는 verdict가 reject일 때만 씁니다.")
        return self

    @property
    def kind(self) -> DecisionKind:
        return DecisionKind.VERDICT if self.verdict is not None else DecisionKind.CHOICE


class StoredDecision(BaseModel):
    """저장소에 들어가는(그리고 나오는) 결정 한 건 — decisions 테이블의 행과 같은 모양"""

    id: str
    owner_github_id: int
    status: str = "draft"
    visibility: str = "private"
    team_id: str | None = None
    origin: str = ORIGIN_MCP
    kind: str
    verdict: str | None = None
    reject_kind: str | None = None
    situation: str
    proposal: str
    options: list[str] = Field(default_factory=list)
    chosen: str | None = None
    rationale: str = ""
    human_quote: str
    tags: list[str] = Field(default_factory=list)
    supersedes: list[str] = Field(default_factory=list)
    consulted: list[dict[str, str | int]] = Field(default_factory=list)
    decided_at: datetime
    cited_count: int = 0
    repeat_count: int = 1
    source: dict[str, str] = Field(default_factory=dict)
    redactions: dict[str, int] = Field(default_factory=dict)
    dedupe_key: str


def normalize_text(text: str) -> str:
    """공백·대소문자를 무시한 비교용 형태"""
    return " ".join(text.split()).lower()


_normalize = normalize_text


def make_dedupe_key(proposal: str, human_quote: str, decided_at: datetime) -> str:
    """같은 날 같은 (제안 + 인용)이면 같은 키. 모델이 같은 결정을 다시 보내는 일이 흔하다."""
    basis = f"{decided_at:%Y-%m-%d}\n{_normalize(proposal)}\n{_normalize(human_quote)}"
    return hashlib.sha256(basis.encode()).hexdigest()[:DEDUPE_KEY_CHARS]


def _resolve_decided_at(requested: datetime | None, now: datetime) -> datetime:
    """클라이언트가 준 시각을 받되, 미래와 너무 먼 과거는 거부한다"""
    if requested is None:
        return now
    if requested.tzinfo is None:
        requested = requested.replace(tzinfo=timezone.utc)
    if requested > now + MAX_FUTURE_SKEW:
        raise ValueError("decided_at 이 미래입니다.")
    if requested < now - MAX_BACKDATE:
        raise ValueError(f"decided_at 이 {MAX_BACKDATE.days}일보다 오래됐습니다.")
    return requested


def to_stored(payload: RecordDecisionInput, owner_github_id: int, now: datetime) -> StoredDecision:
    """입력을 가림 처리해 저장할 모양으로 바꾼다 (중복 키는 가리기 전의 글로 만든다)"""
    counts: Counter[str] = Counter()
    rules = RedactionRules()

    def clean(text: str) -> str:
        result = redact(text, rules)
        counts.update(result.counts)
        return result.text

    decided_at = _resolve_decided_at(payload.decided_at, now)
    dedupe_key = make_dedupe_key(payload.proposal, payload.human_quote, decided_at)
    source = {key: value for key, value in (("client", payload.client), ("project", payload.project)) if value}
    return StoredDecision(
        id=make_decision_id(str(owner_github_id), dedupe_key, decided_at),
        owner_github_id=owner_github_id,
        kind=payload.kind.value,
        verdict=payload.verdict.value if payload.verdict else None,
        reject_kind=payload.reject_kind.value if payload.reject_kind else None,
        situation=clean(payload.situation),
        proposal=clean(payload.proposal),
        options=[clean(option) for option in payload.options],
        chosen=clean(payload.chosen) if payload.chosen else None,
        rationale=clean(payload.rationale),
        human_quote=clean(payload.human_quote),
        tags=[clean(tag)[:MAX_TAG_CHARS] for tag in payload.tags if tag.strip()],
        supersedes=list(dict.fromkeys(payload.supersedes)),
        decided_at=decided_at,
        source={key: clean(value) for key, value in source.items()},
        redactions=dict(counts),
        dedupe_key=dedupe_key,
    )
