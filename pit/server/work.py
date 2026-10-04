"""작업 보고 (report_start / report_commit) — 결정을 어떻게 실행했는지 에이전트가 남기는 요약.

결정(decisions)이 "무엇을 하기로 했나"라면 작업 보고는 "그 결정을 어떻게 실행했나"다.
보고는 주장이다. 원자성·실투입·규모의 검증은 git_watcher 가 독립 근거(diff, 텔레메트리, 재현 실험)로 한다.
일을 시작할 때 남긴 예상 규모(report_start)는 커밋 뒤에 고칠 수 없다 — 사후 부풀리기를 막는 사전 추정이다.

공개 범위 (대표 결정 2026-10-04): 본인과 그 팀의 소유자만 읽는다 (DB 정책 work_reports_select_self_or_team_owner).
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, Field, ValidationError, field_validator

from pit.server.identity import Caller
from pit.server.ratelimit import RateLimiter
from pit.server.records import redact_text

MAX_TASK_CHARS = 200
MAX_TEXT_CHARS = 1000
MAX_IMPLEMENTS = 8
MAX_PRINCIPLES = 12
MAX_HOURS = 200.0
MAX_AGENT_MINUTES = 24 * 60.0
MAX_SHA_CHARS = 64
ID_PREFIX = "W-"
TaskKind = Literal["feature", "fix", "research", "ops", "docs", "refactor"]


class WorkToolFailure(Exception):
    """도구를 호출한 모델에게 그대로 보여 줄 수 있는 실패 사유"""


class _Common(BaseModel):
    task: str = Field(min_length=1, max_length=MAX_TASK_CHARS)
    task_kind: TaskKind
    repo: str | None = Field(default=None, max_length=MAX_TASK_CHARS)
    intent: str = Field(default="", max_length=MAX_TEXT_CHARS)
    position: str = Field(default="", max_length=MAX_TEXT_CHARS)
    implements: list[str] = Field(default_factory=list, max_length=MAX_IMPLEMENTS)
    expected_manual_hours: float | None = Field(default=None, ge=0, le=MAX_HOURS)
    expected_agent_minutes: float | None = Field(default=None, ge=0, le=MAX_AGENT_MINUTES)
    client: str | None = Field(default=None, max_length=MAX_TASK_CHARS)


class ReportStartInput(_Common):
    pass


class ReportCommitInput(_Common):
    commit_sha: str = Field(min_length=7, max_length=MAX_SHA_CHARS)
    start_id: str | None = None
    atomic: bool
    atomic_note: str = Field(default="", max_length=MAX_TEXT_CHARS)
    message_ok: bool
    message_note: str = Field(default="", max_length=MAX_TEXT_CHARS)
    principles_kept: list[str] = Field(default_factory=list, max_length=MAX_PRINCIPLES)
    principles_missed: list[str] = Field(default_factory=list, max_length=MAX_PRINCIPLES)

    @field_validator("commit_sha")
    @classmethod
    def _hex_sha(cls, value: str) -> str:
        if not all(c in "0123456789abcdef" for c in value.lower()):
            raise ValueError("commit_sha 는 16진수 커밋 해시여야 합니다")
        return value.lower()


class StoredWorkReport(BaseModel):
    id: str
    owner_github_id: int
    team_id: str | None
    kind: Literal["start", "commit"]
    start_id: str | None = None
    task: str
    task_kind: str
    repo: str | None = None
    commit_sha: str | None = None
    intent: str = ""
    position: str = ""
    implements: list[str] = Field(default_factory=list)
    expected_manual_hours: float | None = None
    expected_agent_minutes: float | None = None
    atomic: bool | None = None
    atomic_note: str = ""
    message_ok: bool | None = None
    message_note: str = ""
    principles_kept: list[str] = Field(default_factory=list)
    principles_missed: list[str] = Field(default_factory=list)
    client: str | None = None
    redactions: dict[str, int] = Field(default_factory=dict)
    reported_at: datetime


class WorkRepository(Protocol):
    async def ensure_account(self, github_id: int, github_login: str) -> None: ...

    async def member_teams(self, github_id: int) -> list[tuple[str, str]]: ...

    async def insert_work_report(self, report: StoredWorkReport) -> None: ...

    async def get_work_report(self, owner_github_id: int, report_id: str) -> StoredWorkReport | None:
        """본인의 보고 하나. 남의 것이면 None."""
        ...

    async def get_many(self, decision_ids: list[str]) -> list: ...  # 실행한 결정이 실제로 있는지


# 글이 담기는 필드 — 받는 순간 시크릿·개인정보를 가린다 (결정 기록과 같은 규칙)
REDACTED_FIELDS = ("task", "intent", "position", "atomic_note", "message_note")


def _redact(fields: dict[str, object]) -> tuple[dict[str, object], dict[str, int]]:
    cleaned, counts = dict(fields), {}
    for name in REDACTED_FIELDS:
        text = str(cleaned.get(name) or "")
        redacted = redact_text(text)
        if redacted != text:
            counts[name] = 1
        cleaned[name] = redacted
    return cleaned, counts


@dataclass
class WorkTools:
    repository: WorkRepository
    limiter: RateLimiter
    now: Callable[[], datetime]

    async def report_start(self, caller: Caller, arguments: dict[str, object]) -> dict[str, object]:
        payload = self._validate(ReportStartInput, arguments)
        report = await self._store(caller, "start", payload.model_dump())
        return {"id": report.id, "status": "recorded", "redacted": sum(report.redactions.values()),
                "note": "커밋할 때 report_commit 의 start_id 로 이 id 를 넘기세요. 예상 규모는 이제 고칠 수 없습니다."}

    async def report_commit(self, caller: Caller, arguments: dict[str, object]) -> dict[str, object]:
        payload = self._validate(ReportCommitInput, arguments)
        if payload.start_id and await self.repository.get_work_report(caller.github_id, payload.start_id) is None:
            raise WorkToolFailure("start_id 가 본인의 report_start 기록이 아닙니다.")
        report = await self._store(caller, "commit", payload.model_dump())
        flags = [] if payload.atomic and payload.message_ok else ["원자성 또는 커밋 설명을 고칠 여지가 있습니다"]
        return {"id": report.id, "status": "recorded", "redacted": sum(report.redactions.values()), "flags": flags}

    def _validate(self, model: type[BaseModel], arguments: dict[str, object]):  # noqa: ANN202 — 입력 모델
        try:
            return model.model_validate(arguments)
        except ValidationError as e:
            reasons = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
            raise WorkToolFailure(f"입력이 올바르지 않습니다 — {reasons}") from e

    async def _store(self, caller: Caller, kind: str, fields: dict[str, object]) -> StoredWorkReport:
        if not self.limiter.allow(caller.github_id):
            raise WorkToolFailure("보고 요청이 너무 잦습니다. 잠시 뒤에 다시 시도하세요.")
        implements = list(fields.get("implements") or [])
        if implements and len(await self.repository.get_many(implements)) != len(set(implements)):
            raise WorkToolFailure("implements 에 없는 결정 id가 있습니다 (search_my_decisions 로 찾은 id만 쓰세요).")
        await self.repository.ensure_account(caller.github_id, caller.github_login)
        cleaned, counts = _redact(fields)
        report = StoredWorkReport(
            id=f"{ID_PREFIX}{uuid.uuid4().hex[:12]}", owner_github_id=caller.github_id,
            team_id=await self._team_id(caller), kind=kind, redactions=counts, reported_at=self.now(), **cleaned,
        )  # fmt: skip
        await self.repository.insert_work_report(report)
        return report

    async def _team_id(self, caller: Caller) -> str | None:
        """팀 주소로 왔으면 그 팀, 아니면 속한 팀이 하나뿐일 때 그 팀. 소유자가 읽을 범위를 정한다."""
        teams = await self.repository.member_teams(caller.github_id)
        if caller.team_slug:
            return next((team_id for team_id, slug in teams if slug == caller.team_slug), None)
        return teams[0][0] if len(teams) == 1 else None
