"""JEV 판정기 — TypeSafe System One (선택 부품, D-0009 §7)

"이 사람이라면 이 제안을 승인·수정·거부 중 무엇으로 판정할까?"를 보기 셋의 choice 질문으로 묻고,
보정된 확신도를 받는다. 입력(state)은 서버가 기록에서 조립한다 — 묻는 사람의 글은 판정 대상 한 건으로만
들어간다(조종 방지). 이름·계정은 보내지 않는다. 호출이 실패하면 호출자가 무료 판정기로 물러난다.
"""

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

# 공개 API 엔드포인트 (상수 허용 — no-hardcoded-urls 예외)
JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-latest"
JEV_TIMEOUT_SECONDS = 10.0
JEV_EVIDENCE_TEXT_CHARS = 400
VERDICT_QUESTION = "verdict"
VERDICT_CRITERIA = {
    "approve": "This person would accept the proposal as it is.",
    "modify": "This person would accept the direction but change important details.",
    "reject": "This person would turn the proposal down or redirect to a different approach.",
}
VERDICT_INSTRUCTIONS = (
    "The state lists how one person judged earlier proposals at work, then a new proposal. "
    "Judging only from the pattern in their earlier judgments, how would this person judge the new proposal?"
)


class JevError(Exception):
    """JEV 호출 실패 — 호출자는 무료 판정기로 물러난다"""


@dataclass(frozen=True)
class JevVerdict:
    label: str
    confidence: float
    probabilities: dict[str, float]


def build_request(history: list[tuple[str, str, str]], situation: str, proposal: str) -> dict[str, object]:
    """history: (상황, 제안, 판정) — 가장 비슷한 과거 판단들. 새 제안은 마지막 한 건."""
    past = [
        {"situation": s[:JEV_EVIDENCE_TEXT_CHARS], "proposal": p[:JEV_EVIDENCE_TEXT_CHARS], "their_verdict": v}
        for s, p, v in history
    ]
    return {
        "model": JEV_MODEL,
        "state": {"earlier_judgments": past, "new_proposal": {"situation": situation, "proposal": proposal}},
        "questions": {
            VERDICT_QUESTION: {"type": "choice", "instructions": VERDICT_INSTRUCTIONS, "criteria": VERDICT_CRITERIA}
        },
    }


def parse_response(body: dict[str, object]) -> JevVerdict:
    try:
        answer = body["answers"][VERDICT_QUESTION]  # type: ignore[index]
        label = str(answer["choice"])
        if label not in VERDICT_CRITERIA:
            raise JevError(f"알 수 없는 판정: {label}")
        return JevVerdict(label, float(answer.get("confidence", 0.0)), dict(answer.get("probabilities") or {}))
    except (KeyError, TypeError, ValueError) as e:
        raise JevError(f"JEV 응답 형식이 다릅니다: {type(e).__name__}") from e


@dataclass
class JevJudge:
    api_key: str
    client: httpx.AsyncClient | None = None

    async def judge(self, history: list[tuple[str, str, str]], situation: str, proposal: str) -> JevVerdict:
        client = self.client or httpx.AsyncClient(timeout=JEV_TIMEOUT_SECONDS)
        try:
            response = await client.post(
                JEV_ENDPOINT,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=build_request(history, situation, proposal),
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            # 본문에는 판단 글이 섞여 있어 로그에 남기지 않는다
            logger.warning("JEV 호출 실패, 무료 판정기로 물러남", extra={"error": type(e).__name__})
            raise JevError(type(e).__name__) from e
        finally:
            if self.client is None:
                await client.aclose()
        return parse_response(response.json())
