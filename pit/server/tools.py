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
    TEAM_SHARE_GRACE,
    RecordDecisionInput,
    StoredDecision,
    is_team_shared,
    normalize_text,
    to_stored,
)
from pit.server.repository import DecisionRepository

logger = logging.getLogger(__name__)

DEFAULT_SEARCH_LIMIT = 8
MAX_SEARCH_LIMIT = 30
# AI에게 돌려주는 요약의 글자 상한 — 세션 컨텍스트를 잡아먹지 않기 위해
SUMMARY_CHARS = 140

# 검색 범위: 본인만 / 본인 + 속한 팀 전부 / 본인 + 특정 팀
SCOPE_MINE = "mine"
SCOPE_TEAM = "team"
TEAM_SCOPE_PREFIX = "team:"
VISIBILITY_TEAM = "team"
STATUS_CONFIRMED = "confirmed"
# 팀 주소로 왔지만 아직 구성원이 아닌 사람의 기록: private 로 두고 승인 순간 DB 트리거가 팀 범위로 옮긴다
TEAM_STATUS_PENDING = "pending"
TEAM_STATUS_MEMBER = "member"
# transfers.via — 판단이 어떤 경로로 건너갔나
TRANSFER_VIA_GET = "get"


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
        decision = await self._apply_scope(caller, payload, decision)
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
        result: dict[str, object] = {
            "id": decision.id,
            "status": "recorded" if created else "already_recorded",
            "redacted": sum(decision.redactions.values()),
            "visibility": decision.visibility,
        }
        if decision.visibility == VISIBILITY_TEAM:
            result["note"] = (
                f"{TEAM_SHARE_GRACE.days}일 뒤 팀 '{caller.team_slug}'에 보입니다. 그 전에는 본인이 pithub 정리함에서 "
                "빼거나 고칠 수 있습니다. 팀에 보인 뒤에는 회사의 기록입니다."
            )
        if decision.source.get("team_status") == TEAM_STATUS_PENDING:
            result["note"] = (
                f"팀 '{caller.team_slug}' 가입 요청을 보냈습니다. 소유자가 승인하면 이 기록은 팀 범위로 옮겨집니다. "
                "그때까지는 본인만 봅니다."
            )
        return result

    async def _apply_scope(self, caller: Caller, payload: RecordDecisionInput, decision: StoredDecision) -> StoredDecision:
        """팀 커넥터로 들어왔으면 팀 범위(주소가 힌트보다 세다), 아니면 프로젝트별 기본값, 없으면 private.
        범위는 의도일 뿐이고 노출은 확정 뒤다."""
        if caller.team_slug:
            team_id, status = await self.team_status(caller, caller.team_slug)
            source = {**decision.source, "team": caller.team_slug}
            if status == TEAM_STATUS_MEMBER:
                return decision.model_copy(update={"visibility": VISIBILITY_TEAM, "team_id": team_id, "source": source})
            # 구성원이 아니면 거부하지 않고 대기열에 넣는다 — 저장소 접근이 이미 신뢰다. 첫 기록도 버리지 않는다.
            return decision.model_copy(update={"source": {**source, "team_status": TEAM_STATUS_PENDING}})
        if payload.project:
            default = await self.repository.project_default(caller.github_id, payload.project)
            if default is not None:
                return decision.model_copy(update={"visibility": default[0], "team_id": default[1]})
        return decision

    async def team_status(self, caller: Caller, slug: str) -> tuple[str | None, str]:
        """(team_id, member | pending). 팀이 있고 구성원이 아니면 가입 요청을 남긴다."""
        for team_id, team_slug in await self.repository.member_teams(caller.github_id):
            if team_slug == slug:
                return team_id, TEAM_STATUS_MEMBER
        team_id = await self.repository.find_team(slug)
        if team_id is None:
            raise ToolFailure(f"팀 '{slug}'이 없습니다. 주소를 확인하세요. 기록은 저장되지 않았습니다.")
        await self.repository.ensure_account(caller.github_id, caller.github_login)
        await self.repository.request_join(team_id, caller.github_id)
        return team_id, TEAM_STATUS_PENDING

    async def _teams_in_scope(self, caller: Caller, scope: str) -> dict[str, str]:
        """scope 가 가리키는 팀들의 {team_id: slug}. mine 이면 빈 dict."""
        if scope == SCOPE_MINE:
            return {}
        teams = dict(await self.repository.member_teams(caller.github_id))
        if scope == SCOPE_TEAM:
            return teams
        if scope.startswith(TEAM_SCOPE_PREFIX):
            wanted = scope[len(TEAM_SCOPE_PREFIX):]
            chosen = {team_id: slug for team_id, slug in teams.items() if slug == wanted}
            if not chosen:
                raise ToolFailure(f"팀 '{wanted}'의 구성원이 아닙니다.")
            return chosen
        raise ToolFailure(f"scope 는 {SCOPE_MINE} · {SCOPE_TEAM} · {TEAM_SCOPE_PREFIX}<slug> 중 하나입니다.")

    async def search_my_decisions(
        self, caller: Caller, query: str, limit: int = DEFAULT_SEARCH_LIMIT, client: str | None = None,
        scope: str | None = None,
    ) -> list[dict[str, object]]:  # fmt: skip
        bounded = max(1, min(limit, MAX_SEARCH_LIMIT))
        # 팀 커넥터로 들어온 세션은 묻지 않아도 팀까지 본다
        scope = scope or (SCOPE_TEAM if caller.team_slug else SCOPE_MINE)
        teams = await self._teams_in_scope(caller, scope)
        found = await self.repository.search_recorded(caller.github_id, query, bounded)
        if teams:
            found = _merge(found, await self.repository.search_team(list(teams), query, bounded))
        found = _rank(found)[:bounded]
        logins = await self.repository.logins_of(
            [d.owner_github_id for d in found if d.owner_github_id != caller.github_id]
        )
        await self.repository.record_search(caller.github_id, query, [d.id for d in found], client)
        return [_summary(d, by=logins.get(d.owner_github_id), team=teams.get(d.team_id or "")) for d in found]

    async def get_decision(self, caller: Caller, decision_id: str, client: str | None = None) -> dict[str, object]:
        decision = await self.repository.get_by_id(decision_id)
        if decision is None or not await self._can_read(caller, decision):
            raise ToolFailure("그런 결정이 없습니다.")
        # 전체 내용을 가져갔다 = 실제로 썼다. 검색 순위와 A1 측정의 재료.
        await self.repository.mark_cited(decision.owner_github_id, decision_id)
        if decision.owner_github_id == caller.github_id:
            return _detail(decision)
        # 남의 판단을 가져갔다 = 판단이 사람 사이를 건너갔다 (북극성 지표, cites 엣지)
        await self.repository.record_transfer(decision, caller.github_id, TRANSFER_VIA_GET, client)
        logger.info("판단 건너감", extra={"decision_id": decision_id, "team_id": decision.team_id})
        teams = dict(await self.repository.member_teams(caller.github_id))
        logins = await self.repository.logins_of([decision.owner_github_id])
        return _detail(decision, by=logins.get(decision.owner_github_id), team=teams.get(decision.team_id or ""))

    async def _can_read(self, caller: Caller, decision: StoredDecision) -> bool:
        """본인 것이거나, 내가 속한 팀에 보이게 된(확인됐거나 유예가 지난) 팀 범위 결정"""
        if decision.owner_github_id == caller.github_id:
            return True
        if not is_team_shared(decision, self.now()) or not decision.team_id:
            return False
        return decision.team_id in dict(await self.repository.member_teams(caller.github_id))


def _merge(mine: list[StoredDecision], team: list[StoredDecision]) -> list[StoredDecision]:
    seen = {d.id for d in mine}
    return mine + [d for d in team if d.id not in seen]


def _rank(found: list[StoredDecision]) -> list[StoredDecision]:
    """원칙 > 확인됨 > 인용 > 반복 > 최근 — 대체된 결정은 뒤로"""
    superseded = {old for d in found for old in d.supersedes}

    def key(d: StoredDecision) -> tuple[int, int, int, int, str]:
        return (
            0 if d.id in superseded else 1,
            1 if "principle" in d.tags else 0,
            1 if d.status == STATUS_CONFIRMED else 0,
            d.cited_count + d.repeat_count,
            d.decided_at.isoformat(),
        )

    return sorted(found, key=key, reverse=True)


def _summary(decision: StoredDecision, by: str | None = None, team: str | None = None) -> dict[str, object]:
    summary: dict[str, object] = {
        "id": decision.id,
        "decided_at": decision.decided_at.date().isoformat(),
        "proposal": decision.proposal[:SUMMARY_CHARS],
        "verdict": decision.verdict,
        "chosen": decision.chosen,
        "human_quote": decision.human_quote[:SUMMARY_CHARS],
        # 사람이 확인한 기록인지 — 모델이 인용할 때 무게를 달리 둘 수 있다
        "verified": decision.status == STATUS_CONFIRMED,
        "principle": "principle" in decision.tags,
        "superseded_by": None,
    }
    # 남의 결정에만 붙는다: 누구의 것이고 어느 팀에 낸 것인지
    if by is not None:
        summary["by"] = by
    if team is not None:
        summary["team"] = team
    return summary


def _detail(decision: StoredDecision, by: str | None = None, team: str | None = None) -> dict[str, object]:
    return {
        **_summary(decision, by=by, team=team),
        "status": decision.status,
        "situation": decision.situation,
        "reject_kind": decision.reject_kind,
        "options": decision.options,
        "rationale": decision.rationale,
        "tags": decision.tags,
        "supersedes": decision.supersedes,
    }
