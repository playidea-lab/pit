"""트윈에게 묻기 (G6, docs/GRAPH_ENGINEERING.md)

트윈은 따로 학습시킨 모델이 아니라 그 사람의 판단 그래프를 묻는 사람의 권한만큼 잘라 본 관점이다(D-0009 §8).
판정기는 팀 소유자가 동의한 팀이면 JEV(보정된 확신도), 아니면 비용이 들지 않는 kNN
(오프라인 시험 G7에서 확신 ≥ 0.6 → 정확도 0.89).
확신하지 못하면 답하지 않고 본인에게 묻는다. 트윈은 설명하고 제안할 뿐 결정하지 않는다(D-0009 §3).
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from pit.server.conflicts import proposal_similarity
from pit.server.graph import readable_for
from pit.server.identity import Caller
from pit.server.jev import JevError, JevJudge
from pit.server.records import SUMMARY_CHARS, StoredDecision, redact_text
from pit.server.repository import DecisionRepository
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
MAX_QUESTION_CHARS = 1000


class TwinUnavailable(Exception):
    """물을 수 없는 트윈 — 모델에게 그대로 보여 줄 사유"""


@dataclass
class TwinService:
    repository: DecisionRepository
    now: Callable[[], datetime]
    # 선택 판정기. 동의한 팀의 결정으로만 부른다 (D-0009 §7). 없거나 실패하면 kNN.
    jev: JevJudge | None = None

    async def ask(self, caller: Caller, login: str, proposal: str, situation: str = "") -> dict[str, object]:
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
        evidence = sorted(pool, key=lambda d: proposal_similarity(query, f"{d.situation} {d.proposal}"), reverse=True)
        prediction, confidence, judge = await self._judge(pool, evidence, situation, proposal, query)
        evidence = evidence[:TWIN_EVIDENCE_LIMIT]
        abstained = prediction is None or confidence < TWIN_CONFIDENCE_MIN
        await self.repository.record_consult(
            caller.github_id, twin_id, proposal, [d.id for d in evidence], confidence, abstained
        )
        await self._follow_up(caller, twin_id, departed, abstained, evidence, situation, proposal, confidence, teams)
        answer = _answer(login, departed, None if abstained else prediction, confidence, abstained, evidence)
        return {**answer, "judge": judge}

    async def _judge(
        self, pool: list[StoredDecision], ranked: list[StoredDecision], situation: str, proposal: str, query: str
    ) -> tuple[str | None, float, str]:
        """동의한 팀의 결정이 있고 JEV가 있으면 JEV, 아니면(또는 실패하면) kNN"""
        if self.jev is not None:
            consenting = await self.repository.consenting_teams(list({d.team_id for d in ranked if d.team_id}))
            history = [(d.situation, d.proposal, d.verdict) for d in ranked if d.team_id in consenting and d.verdict]
            if history:
                try:
                    verdict = await self.jev.judge(history[:JEV_HISTORY_LIMIT], situation, proposal)
                    return verdict.label, verdict.confidence, JUDGE_JEV
                except JevError as e:
                    # 무료 판정기로 물러난다 (원인은 jev.py 가 경고로 남겼다)
                    logger.info("트윈 판정기 kNN으로 대체", extra={"reason": str(e)})
        items = [Item(id=d.id, decided_at=d.decided_at, text=f"{d.situation} {d.proposal}", label=d.verdict)
                 for d in pool if d.verdict]  # fmt: skip
        if not items:
            return None, 0.0, JUDGE_KNN
        predicted = knn_judge(items, Item(id="?", decided_at=self.now(), text=query, label=""))
        return predicted.label, predicted.confidence, JUDGE_KNN

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
