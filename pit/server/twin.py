"""트윈에게 묻기 (G6, docs/GRAPH_ENGINEERING.md)

트윈은 따로 학습시킨 모델이 아니라 그 사람의 판단 그래프를 묻는 사람의 권한만큼 잘라 본 관점이다(D-0009 §8).
답은 비용이 들지 않는 kNN이 한다(오프라인 시험 G7: 균형 정확도 0.456, 확신 ≥ 0.6 → 0.89).
팀 소유자가 동의한 팀이면 JEV가 같은 질문을 그림자로 판정해 기록만 한다 — 주인의 채점으로 둘을 다시 비교한다.
확신하지 못하면 답하지 않고 본인에게 묻는다. 트윈은 설명하고 제안할 뿐 결정하지 않는다(D-0009 §3).
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from pit.server.conflicts import proposal_similarity
from pit.server.graph import readable_for
from pit.server.identity import Caller
from pit.server.jev import JevError, JevJudge
from pit.server.ratelimit import RateLimiter
from pit.server.records import SUMMARY_CHARS, StoredDecision, redact_text
from pit.server.repository import DecisionRepository
from pit.server.twin_graph import BASIS_GRAPH, BASIS_TEXT, graph_evidence
from pit.twin.offline import Item, knn_judge

logger = logging.getLogger(__name__)

# 이 확신도 아래면 답하지 않고 본인에게 묻는다
TWIN_CONFIDENCE_MIN = 0.6
TWIN_POOL_LIMIT = 200
TWIN_EVIDENCE_LIMIT = 5
TRANSFER_VIA_TWIN = "twin"
# JEV 에 보여 줄 가장 비슷한 과거 판단 수
JEV_HISTORY_LIMIT = 8
JUDGE_JEV, JUDGE_KNN = "jev", "knn"
# 띄워 둔 그림자 판정 — 참조를 잡아 두지 않으면 끝나기 전에 수거될 수 있다
_SHADOW_TASKS: set[asyncio.Task[None]] = set()
MAX_QUESTION_CHARS = 1000
# 한 사람이 한 시간에 트윈에게 물을 수 있는 횟수
TWIN_ASKS_PER_HOUR = 60


class TwinUnavailable(Exception):
    """물을 수 없는 트윈 — 모델에게 그대로 보여 줄 사유"""


@dataclass
class TwinService:
    repository: DecisionRepository
    now: Callable[[], datetime]
    # 선택 판정기. 동의한 팀의 결정으로만 부른다 (D-0009 §7). 없거나 실패하면 kNN.
    jev: JevJudge | None = None
    # 묻는 사람별 빈도 제한 — 폭주하는 에이전트가 JEV 비용과 자문 기록을 끝없이 늘리지 못하게
    limiter: RateLimiter | None = None

    async def ask(
        self, caller: Caller, login: str, proposal: str, situation: str = "", about: list[str] | None = None
    ) -> dict[str, object]:
        if self.limiter is not None and not self.limiter.allow(caller.github_id):
            raise TwinUnavailable("트윈에게 너무 자주 묻고 있습니다. 잠시 뒤에 다시 물으세요.")
        proposal, situation = redact_text(proposal[:MAX_QUESTION_CHARS]), redact_text(situation[:MAX_QUESTION_CHARS])
        found = await self.repository.find_account(login)
        if found is None:
            raise TwinUnavailable(f"'{login}' 은 pithub 계정이 아닙니다.")
        twin_id, departed = found
        if twin_id == caller.github_id:
            raise TwinUnavailable("본인의 판단은 search_my_decisions 로 찾으세요.")
        teams = dict(await self.repository.member_teams(caller.github_id))
        readable = readable_for(caller.github_id, teams, self.now())
        pool = [d for d in await self.repository.team_decisions_of(twin_id, list(teams), TWIN_POOL_LIMIT) if readable(d)]
        query = f"{situation} {proposal}"
        # 근거는 그래프가 먼저: 질문의 주제에 매달린 그 사람의 결정 + 한 단계 이어진 결정 (D-0009 §8)
        graph_pool, matched = await graph_evidence(self.repository, pool, query, about or [])
        basis = BASIS_GRAPH if graph_pool else BASIS_TEXT
        pool = graph_pool or pool
        evidence = sorted(pool, key=lambda d: proposal_similarity(query, f"{d.situation} {d.proposal}"), reverse=True)
        # 답은 무료 kNN이 한다 (오프라인 시험: kNN 0.456 > JEV 0.389). JEV는 그림자로만 (2026-09-24 사용자 결정).
        prediction, confidence = self._knn(pool, query)
        evidence = evidence[:TWIN_EVIDENCE_LIMIT]
        abstained = prediction is None or confidence < TWIN_CONFIDENCE_MIN
        consult_id = await self.repository.record_consult(
            caller.github_id, twin_id, proposal, [d.id for d in evidence], confidence, abstained,
            None if abstained else prediction, JUDGE_KNN,
        )  # fmt: skip
        self._start_shadow(consult_id, evidence, situation, proposal)
        await self._follow_up(caller, twin_id, departed, abstained, evidence, situation, proposal, confidence, teams)
        answer = _answer(login, departed, None if abstained else prediction, confidence, abstained, evidence)
        graph = {"basis": basis, "topics": matched} if matched else {"basis": basis}
        return {**answer, "judge": JUDGE_KNN, **graph}

    def _knn(self, pool: list[StoredDecision], query: str) -> tuple[str | None, float]:
        items = [Item(id=d.id, decided_at=d.decided_at, text=f"{d.situation} {d.proposal}", label=d.verdict)
                 for d in pool if d.verdict]  # fmt: skip
        if not items:
            return None, 0.0
        predicted = knn_judge(items, Item(id="?", decided_at=self.now(), text=query, label=""))
        return predicted.label, predicted.confidence

    def _start_shadow(self, consult_id: int, ranked: list[StoredDecision], situation: str, proposal: str) -> None:
        """JEV 그림자 판정을 기다리지 않고 띄운다 — 트윈의 응답 속도에 영향을 주지 않는다"""
        if self.jev is None:
            return
        task = asyncio.create_task(self._shadow(consult_id, ranked, situation, proposal))
        _SHADOW_TASKS.add(task)
        task.add_done_callback(_SHADOW_TASKS.discard)

    async def shadow_now(self, consult_id: int, ranked: list[StoredDecision], situation: str, proposal: str) -> None:
        """테스트와 재실행용: 그림자 판정을 기다려서 돌린다"""
        await self._shadow(consult_id, ranked, situation, proposal)

    async def _shadow(self, consult_id: int, ranked: list[StoredDecision], situation: str, proposal: str) -> None:
        """동의한 팀의 결정으로만 JEV를 부른다 (D-0009 §7). 실패는 경고만 남기고 답에는 영향이 없다."""
        consenting = await self.repository.consenting_teams(list({d.team_id for d in ranked if d.team_id}))
        history = [(d.situation, d.proposal, d.verdict) for d in ranked if d.team_id in consenting and d.verdict]
        if not history or self.jev is None:
            return
        try:
            verdict = await self.jev.judge(history[:JEV_HISTORY_LIMIT], situation, proposal)
        except JevError as e:
            logger.info("JEV 그림자 판정 실패", extra={"reason": str(e), "consult_id": consult_id})
            return
        await self.repository.record_shadow(consult_id, JUDGE_JEV, verdict.label, verdict.confidence)

    async def _follow_up(
        self, caller: Caller, twin_id: int, departed: bool, abstained: bool, evidence: list[StoredDecision],
        situation: str, proposal: str, confidence: float, teams: dict[str, str],
    ) -> None:  # fmt: skip
        """답했으면 근거가 건너간 것이고, 기권했으면 본인에게 묻는다 (떠난 사람에게는 묻지 않는다)"""
        if not abstained and evidence:
            await self.repository.record_transfer(evidence[0], caller.github_id, TRANSFER_VIA_TWIN, None)
        if abstained and not departed:
            team_id = next((d.team_id for d in evidence if d.team_id in teams), next(iter(teams), None))
            await self.repository.create_twin_question(caller.github_id, twin_id, team_id, situation, proposal, confidence)


def _answer(
    login: str, departed: bool, prediction: str | None, confidence: float, abstained: bool, evidence: list[StoredDecision]
) -> dict[str, object]:
    answer: dict[str, object] = {
        "twin": login,
        "prediction": prediction,
        "confidence": round(confidence, 2),
        "abstained": abstained,
        "evidence": [
            {"id": d.id, "decided_at": d.decided_at.date().isoformat(), "proposal": d.proposal[:SUMMARY_CHARS],
             "verdict": d.verdict, "human_quote": d.human_quote[:SUMMARY_CHARS], "verified": d.status == "confirmed"}
            for d in evidence
        ],  # fmt: skip
        "note": _note(login, departed, abstained),
    }
    if departed:
        answer["departed"] = True
    return answer


def _note(login: str, departed: bool, abstained: bool) -> str:
    if abstained and departed:
        return f"{login}의 기록으로는 판단할 수 없습니다. {login}은 떠난 구성원이라 물어볼 수 없습니다 — 팀과 정하세요."
    if abstained:
        return f"{login}의 기록으로는 판단할 수 없어 {login}에게 질문을 남겼습니다. 답하면 {login}의 결정으로 기록됩니다."
    return f"{login}이라면 이렇게 판단할 것이라는 예측입니다 — {login}이 정한 것이 아닙니다. 근거를 함께 말하세요."
