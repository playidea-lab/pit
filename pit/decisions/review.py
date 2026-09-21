"""후보 검토 — 확정 · 고치기 · 버리기

하루 한 번 몰아서 하는 5분짜리 일이고, 1인 단계에서 사람이 하는 유일한 일이다.
화면 입출력은 호출자가 주입한다. 여기서는 판정을 적용하고 기록하는 일만 한다.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from pit.decisions.models import Decision, ExtractionMethod, ReviewAction, ReviewInfo
from pit.decisions.store import (
    DECISIONS_DIR,
    REVIEW_LOG,
    ReviewEvent,
    append_review_event,
    delete_candidate,
    save_decision_record,
)
from pit.personal.gitrepo import commit_paths

REVIEW_DAILY_LIMIT = 40
# 사람이 고칠 수 있는 필드. 출처·ID·추출 정보는 고치지 않는다.
EDITABLE_FIELDS = (
    "situation", "proposal", "verdict", "reject_kind", "chosen", "rationale", "human_quote", "tags", "supersedes",
)  # fmt: skip


class ReviewCommand(str, Enum):
    CONFIRM = "confirm"
    EDIT = "edit"
    DISCARD = "discard"
    SKIP = "skip"
    QUIT = "quit"


@dataclass(frozen=True)
class ReviewInput:
    command: ReviewCommand
    # EDIT일 때 바꿀 필드와 값
    edits: dict[str, object] = field(default_factory=dict)


@dataclass
class ReviewSummary:
    confirmed: int = 0
    edited: int = 0
    discarded: int = 0
    skipped: int = 0
    committed: bool = False

    @property
    def message(self) -> str:
        return f"review: +{self.confirmed} confirmed, {self.edited} edited, {self.discarded} discarded"


def order_for_review(candidates: list[Decision]) -> list[Decision]:
    """구조 신호에서 나온 후보를 먼저 (확정이 빠르다), 그 안에서는 시간순"""
    return sorted(
        candidates,
        key=lambda d: (d.extractor.method is not ExtractionMethod.STRUCTURED, d.decided_at),
    )


def apply_review(
    home: Path, candidate: Decision, review_input: ReviewInput, seconds: float, now: datetime
) -> Decision | None:
    """검토 결과 하나를 저장한다. 확정·수정이면 결정을, 버림이면 None을 돌려준다."""
    edited_fields: list[str] = []
    decision = candidate
    if review_input.command is ReviewCommand.EDIT:
        unknown = set(review_input.edits) - set(EDITABLE_FIELDS)
        if unknown:
            raise ValueError(f"고칠 수 없는 필드: {sorted(unknown)}")
        merged = {**candidate.model_dump(), **review_input.edits}
        decision = Decision.model_validate(merged)
        edited_fields = sorted(
            name for name in review_input.edits if getattr(decision, name) != getattr(candidate, name)
        )

    action = {
        ReviewCommand.CONFIRM: ReviewAction.CONFIRMED,
        ReviewCommand.EDIT: ReviewAction.EDITED if edited_fields else ReviewAction.CONFIRMED,
        ReviewCommand.DISCARD: ReviewAction.DISCARDED,
    }[review_input.command]
    review = ReviewInfo(action=action, edited_fields=edited_fields, seconds=seconds, reviewed_at=now)

    append_review_event(
        home,
        ReviewEvent(decision_id=candidate.id, review=review, extractor_method=candidate.extractor.method.value),
    )
    delete_candidate(home, candidate.id)
    if action is ReviewAction.DISCARDED:
        return None

    decision = decision.model_copy(update={"review": review})
    save_decision_record(home, decision)
    return decision


def run_review_session(
    home: Path,
    candidates: list[Decision],
    ask: Callable[[Decision], ReviewInput],
    clock: Callable[[], float],
    now: datetime,
    limit: int = REVIEW_DAILY_LIMIT,
) -> ReviewSummary:
    """후보를 차례로 검토하고, 끝나면 commit 한 번으로 묶는다

    Args:
        ask: 후보 하나를 보여 주고 사람의 입력을 받아 오는 함수
        clock: 단조 증가 시계 (검토에 걸린 시간을 재는 데 쓴다)
    """
    summary = ReviewSummary()
    for candidate in order_for_review(candidates)[:limit]:
        started = clock()
        review_input = ask(candidate)
        if review_input.command is ReviewCommand.QUIT:
            break
        if review_input.command is ReviewCommand.SKIP:
            summary.skipped += 1
            continue

        result = apply_review(home, candidate, review_input, clock() - started, now)
        if result is None:
            summary.discarded += 1
        elif result.review and result.review.action is ReviewAction.EDITED:
            summary.edited += 1
        else:
            summary.confirmed += 1

    if summary.confirmed or summary.edited or summary.discarded:
        tracked = [home / DECISIONS_DIR, home / REVIEW_LOG, home / ".gitignore"]
        summary.committed = commit_paths(home, tracked, summary.message)
    return summary
