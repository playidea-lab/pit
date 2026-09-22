"""MCP 도구의 실제 동작 (전송·인증과 분리되어 있어 그대로 테스트할 수 있다)"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError

from pit.server.identity import Caller
from pit.server.ratelimit import RateLimiter
from pit.server.records import RecordDecisionInput, StoredDecision, to_stored
from pit.server.repository import DecisionRepository

logger = logging.getLogger(__name__)

DEFAULT_SEARCH_LIMIT = 10
MAX_SEARCH_LIMIT = 50


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

        decision = to_stored(payload, caller.github_id, self.now())
        await self.repository.ensure_account(caller.github_id, caller.github_login)
        # 프로젝트별 기본 범위 (없으면 private). 초안에 붙는 것은 의도일 뿐, 노출은 확정 뒤다.
        if payload.project:
            default = await self.repository.project_default(caller.github_id, payload.project)
            if default is not None:
                decision = decision.model_copy(update={"visibility": default[0], "team_id": default[1]})
        created = await self.repository.insert_draft(decision)

        # 글의 내용은 로그에 남기지 않는다
        logger.info(
            "결정 기록",
            extra={"decision_id": decision.id, "created": created, "redacted": sum(decision.redactions.values())},
        )
        return {
            "id": decision.id,
            "status": "recorded" if created else "already_recorded",
            "redacted": sum(decision.redactions.values()),
        }

    async def search_my_decisions(
        self, caller: Caller, query: str, limit: int = DEFAULT_SEARCH_LIMIT
    ) -> list[dict[str, object]]:
        bounded = max(1, min(limit, MAX_SEARCH_LIMIT))
        found = await self.repository.search_confirmed(caller.github_id, query, bounded)
        return [_summary(decision) for decision in found]

    async def get_decision(self, caller: Caller, decision_id: str) -> dict[str, object]:
        decision = await self.repository.get(caller.github_id, decision_id)
        if decision is None:
            raise ToolFailure("그런 결정이 없습니다.")
        return _detail(decision)


def _summary(decision: StoredDecision) -> dict[str, object]:
    return {
        "id": decision.id,
        "decided_at": decision.decided_at.isoformat(),
        "proposal": decision.proposal,
        "verdict": decision.verdict,
        "chosen": decision.chosen,
        "human_quote": decision.human_quote,
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
