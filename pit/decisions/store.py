"""후보와 확정 결정의 저장

    candidates/<id>.json   사람이 아직 보지 않은 후보 (git 미추적)
    decisions/<id>.md      확정된 결정 (git 추적, 파일 하나가 결정 하나)
    reviews.jsonl          검토 이력 — 버린 후보도 남는다 (git 추적)
"""

import json
import logging
from pathlib import Path

from pydantic import BaseModel, ValidationError

from pit.decisions.models import Decision, DecisionKind, ReviewAction, ReviewInfo
from pit.loaders.frontmatter import dump_frontmatter, parse_frontmatter

logger = logging.getLogger(__name__)

CANDIDATES_DIR = Path("candidates")
DECISIONS_DIR = Path("decisions")
REVIEW_LOG = Path("reviews.jsonl")
STORE_FILE_MODE = 0o600


class ReviewEvent(BaseModel):
    """검토 한 건의 기록. 확정·수정·버림 모두 남긴다."""

    decision_id: str
    review: ReviewInfo
    extractor_method: str


def save_candidate(home: Path, decision: Decision) -> Path:
    path = home / CANDIDATES_DIR / f"{decision.id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(decision.model_dump_json(indent=2), encoding="utf-8")
    path.chmod(STORE_FILE_MODE)
    return path


def load_candidates(home: Path) -> list[Decision]:
    """후보를 판정 시각 순으로 돌려준다. 읽을 수 없는 파일은 건너뛴다."""
    candidates = []
    for path in sorted((home / CANDIDATES_DIR).glob("PD-*.json")):
        try:
            candidates.append(Decision.model_validate_json(path.read_text(encoding="utf-8")))
        except ValidationError as e:
            logger.warning("후보를 읽을 수 없어 건너뜀", extra={"file": path.name, "errors": e.error_count()})
    return sorted(candidates, key=lambda d: d.decided_at)


def delete_candidate(home: Path, decision_id: str) -> None:
    (home / CANDIDATES_DIR / f"{decision_id}.json").unlink(missing_ok=True)


def _readable_body(decision: Decision) -> str:
    if decision.kind is DecisionKind.CHOICE:
        outcome = f"고른 답: {decision.chosen} (선택지: {' | '.join(decision.options)})"
    else:
        outcome = f"판정: {decision.verdict.value if decision.verdict else '-'}"
    parts = [f"# {decision.proposal[:80]}", outcome]
    if decision.human_quote:
        parts.append(f"> {decision.human_quote}")
    return "\n\n".join(parts) + "\n"


def save_decision_record(home: Path, decision: Decision) -> Path:
    """확정된 결정을 decisions/<id>.md 로 쓴다 (기존 팀 원장의 save_decision 과 별개)"""
    path = home / DECISIONS_DIR / f"{decision.id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = decision.model_dump(mode="json", exclude_none=True)
    path.write_text(dump_frontmatter(fields, _readable_body(decision)), encoding="utf-8")
    path.chmod(STORE_FILE_MODE)
    return path


def load_decisions(home: Path) -> list[Decision]:
    """확정된 결정을 판정 시각 순으로 돌려준다. 깨진 파일은 경고하고 건너뛴다."""
    decisions = []
    for path in sorted((home / DECISIONS_DIR).glob("PD-*.md")):
        fields, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        try:
            decisions.append(Decision.model_validate(fields))
        except ValidationError as e:
            logger.warning("결정을 읽을 수 없어 건너뜀", extra={"file": path.name, "errors": e.error_count()})
    return sorted(decisions, key=lambda d: d.decided_at)


def superseded_by(decisions: list[Decision]) -> dict[str, list[str]]:
    """어떤 결정이 나중의 어떤 결정들에 의해 뒤집혔는가 (supersedes 에서 파생)"""
    reverse: dict[str, list[str]] = {}
    for decision in decisions:
        for target in decision.supersedes:
            reverse.setdefault(target, []).append(decision.id)
    return reverse


def append_review_event(home: Path, event: ReviewEvent) -> None:
    path = home / REVIEW_LOG
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n")
    path.chmod(STORE_FILE_MODE)


def load_review_events(home: Path) -> list[ReviewEvent]:
    path = home / REVIEW_LOG
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [ReviewEvent.model_validate_json(line) for line in f if line.strip()]


def known_ids(home: Path) -> set[str]:
    """이미 후보이거나, 확정됐거나, 버려진 결정의 ID — 다시 후보로 만들지 않는다"""
    ids = {path.stem for path in (home / CANDIDATES_DIR).glob("PD-*.json")}
    ids |= {path.stem for path in (home / DECISIONS_DIR).glob("PD-*.md")}
    ids |= {e.decision_id for e in load_review_events(home) if e.review.action is ReviewAction.DISCARDED}
    return ids
