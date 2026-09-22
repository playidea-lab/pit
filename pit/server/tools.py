"""MCP 도구의 실제 동작 (전송·인증과 분리되어 있어 그대로 테스트할 수 있다)"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from pydantic import ValidationError

from pit.server.identity import Caller
from pit.server.ratelimit import RateLimiter
from pit.server.records import (
    REPEAT_WINDOW_DAYS,
    RecordDecisionInput,
    StoredDecision,
    normalize_text,
    to_stored,
)
from pit.server.repository import DecisionRepository

logger = logging.getLogger(__name__)

DEFAULT_SEARCH_LIMIT = 8
MAX_SEARCH_LIMIT = 30
# AI에게 돌려주는 요약의 글자 상한 — 세션 컨텍스트를 잡아먹지 않기 위해
SUMMARY_CHARS = 140


class ToolFailure(Exception):
    """도구를 호출한 모델에게 그대로 보여 줄 수 있는 실패 사유"""


@dataclass
class DecisionTools:
    repository: DecisionRepository
    limiter: RateLimiter
    now: Callable[[], datetime]

    async def record_decision(self, caller: Caller, arguments: dict[str, object]) -> dict[str, object]:
        try:
            payload = RecordDecisionInput.model_validate(arguments)
        except ValidationError as e:
            reasons = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
            raise ToolFailure(f"입력이 올바르지 않습니다 — {reasons}") from e

        if not self.limiter.allow(caller.github_id):
            raise ToolFailure("기록 요청이 너무 잦습니다. 잠시 뒤에 다시 시도하세요.")

        try:
            decision = to_stored(payload, caller.github_id, self.now())
        except ValueError as e:
            raise ToolFailure(f"입력이 올바르지 않습니다 — {e}") from e
        await self.repository.ensure_account(caller.github_id, caller.github_login)
        # 프로젝트별 기본 범위 (없으면 private). 초안에 붙는 것은 의도일 뿐, 노출은 확정 뒤다.
        if payload.project:
            default = await self.repository.project_default(caller.github_id, payload.project)
            if default is not None:
                decision = decision.model_copy(update={"visibility": default[0], "team_id": default[1]})
        if payload.supersedes and not await self.repository.owns_all(caller.github_id, payload.supersedes):
            raise ToolFailure("supersedes 에 본인 결정이 아닌 id가 있습니다.")

        # 며칠 안에 같은 제안이 또 오면 새 행 대신 반복 횟수를 올린다 (반복도 정보다)
        since = self.now() - timedelta(days=REPEAT_WINDOW_DAYS)
        repeated = await self.repository.find_recent_same_proposal(
            caller.github_id, payload.project, normalize_text(payload.proposal), since
        )
        same_outcome = repeated is not None and (repeated.verdict, repeated.chosen) == (decision.verdict, decision.chosen)
        if repeated is not None and same_outcome and repeated.dedupe_key != decision.dedupe_key:
            await self.repository.bump_repeat(repeated.id)
            logger.info("반복 결정 접힘", extra={"decision_id": repeated.id})
            return {"id": repeated.id, "status": "repeated", "redacted": 0}

        created = await self.repository.insert_draft(decision)

        # 글의 내용은 로그에 남기지 않는다
        logger.info(
            "결정 기록",
            extra={"decision_id": decision.id, "stored": created, "redacted": sum(decision.redactions.values())},
        )
        return {
            "id": decision.id,
            "status": "recorded" if created else "already_recorded",
            "redacted": sum(decision.redactions.values()),
        }

    async def search_my_decisions(
        self, caller: Caller, query: str, limit: int = DEFAULT_SEARCH_LIMIT, client: str | None = None
    ) -> list[dict[str, object]]:
        bounded = max(1, min(limit, MAX_SEARCH_LIMIT))
        found = await self.repository.search_recorded(caller.github_id, query, bounded)
        found = _rank(found)
        await self.repository.record_search(caller.github_id, query, [d.id for d in found], client)
        return [_summary(decision) for decision in found]

    async def get_decision(self, caller: Caller, decision_id: str) -> dict[str, object]:
        decision = await self.repository.get(caller.github_id, decision_id)
        if decision is None:
            raise ToolFailure("그런 결정이 없습니다.")
        # 전체 내용을 가져갔다 = 실제로 썼다. 검색 순위와 A1 측정의 재료.
        await self.repository.mark_cited(caller.github_id, decision_id)
        return _detail(decision)


def _rank(found: list[StoredDecision]) -> list[StoredDecision]:
    """원칙 > 확인됨 > 인용 > 반복 > 최근 — 대체된 결정은 뒤로"""
    superseded = {old for d in found for old in d.supersedes}

    def key(d: StoredDecision) -> tuple[int, int, int, int, str]:
        return (
            0 if d.id in superseded else 1,
            1 if "principle" in d.tags else 0,
            1 if d.status == "confirmed" else 0,
            d.cited_count + d.repeat_count,
            d.decided_at.isoformat(),
        )

    return sorted(found, key=key, reverse=True)


def _summary(decision: StoredDecision) -> dict[str, object]:
    return {
        "id": decision.id,
        "decided_at": decision.decided_at.date().isoformat(),
        "proposal": decision.proposal[:SUMMARY_CHARS],
        "verdict": decision.verdict,
        "chosen": decision.chosen,
        "human_quote": decision.human_quote[:SUMMARY_CHARS],
        # 사람이 확인한 기록인지 — 모델이 인용할 때 무게를 달리 둘 수 있다
        "verified": decision.status == "confirmed",
        "principle": "principle" in decision.tags,
        "superseded_by": None,
    }


def _detail(decision: StoredDecision) -> dict[str, object]:
    return {
        **_summary(decision),
        "status": decision.status,
        "situation": decision.situation,
        "reject_kind": decision.reject_kind,
        "options": decision.options,
        "rationale": decision.rationale,
        "tags": decision.tags,
        "supersedes": decision.supersedes,
    }
