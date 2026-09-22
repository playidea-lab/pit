"""테스트용 가짜 구현"""

from dataclasses import dataclass, field

from pit.llm.client import LLMError, StructuredRequest
from pit.transcripts.records import JsonObject


@dataclass
class FakeLLMClient:
    """정해 둔 응답을 차례로 돌려주고, 받은 요청을 전부 기록한다

    응답 자리에 예외 객체를 넣으면 그 차례에 예외를 던진다.
    기록된 요청은 '이 글이 LLM에게 넘어갔는가'를 단언하는 데 쓴다.
    """

    responses: list[JsonObject | Exception] = field(default_factory=list)
    requests: list[StructuredRequest] = field(default_factory=list)

    def complete_structured(self, request: StructuredRequest) -> JsonObject:
        self.requests.append(request)
        if not self.responses:
            raise LLMError("준비된 응답이 없습니다")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def all_request_text(self) -> str:
        return "\n".join(f"{r.system}\n{r.user}" for r in self.requests)


class FakeClock:
    """호출할 때마다 정해진 만큼 흐르는 단조 시계 (테스트에서 sleep을 쓰지 않기 위함)"""

    def __init__(self, step_seconds: float = 1.0) -> None:
        self._now = 0.0
        self._step = step_seconds

    def __call__(self) -> float:
        self._now += self._step
        return self._now


class InMemoryRepository:
    """DecisionRepository 규약의 메모리 구현 (여러 사용자의 행을 한곳에 담는다)"""

    def __init__(self) -> None:
        self.accounts: dict[int, str] = {}
        self.rows: list = []
        # token_hash → (github_id, login)
        self.tokens: dict[str, tuple[int, str]] = {}
        # (github_id, project) → (visibility, team_id)
        self.project_defaults: dict[tuple[int, str], tuple[str, str | None]] = {}
        self.fail_with: Exception | None = None

    def _maybe_fail(self) -> None:
        if self.fail_with is not None:
            raise self.fail_with

    async def ensure_account(self, github_id: int, github_login: str) -> None:
        self._maybe_fail()
        self.accounts[github_id] = github_login

    async def insert_draft(self, decision) -> bool:  # noqa: ANN001
        self._maybe_fail()
        duplicate = any(
            row.owner_github_id == decision.owner_github_id and row.dedupe_key == decision.dedupe_key
            for row in self.rows
        )
        if duplicate:
            return False
        self.rows.append(decision)
        return True

    async def search_confirmed(self, owner_github_id: int, query: str, limit: int) -> list:
        self._maybe_fail()
        needle = query.lower()
        found = [
            row
            for row in self.rows
            if row.owner_github_id == owner_github_id
            and row.status == "confirmed"
            and needle in f"{row.situation} {row.proposal} {row.rationale} {row.human_quote}".lower()
        ]
        return found[:limit]

    async def get(self, owner_github_id: int, decision_id: str):  # noqa: ANN201
        self._maybe_fail()
        return next(
            (row for row in self.rows if row.owner_github_id == owner_github_id and row.id == decision_id), None
        )

    async def find_token_owner(self, token_hash: str):  # noqa: ANN201
        self._maybe_fail()
        from pit.server.identity import Caller

        found = self.tokens.get(token_hash)
        return Caller(github_id=found[0], github_login=found[1]) if found else None

    async def upsert_local(self, decisions: list) -> int:
        self._maybe_fail()
        for decision in decisions:
            self.rows = [row for row in self.rows if row.id != decision.id]
            self.rows.append(decision)
        return len(decisions)

    async def list_mine(self, owner_github_id: int, since, limit: int) -> list:  # noqa: ANN001
        self._maybe_fail()
        rows = [r for r in self.rows if r.owner_github_id == owner_github_id and (since is None or r.decided_at >= since)]
        return sorted(rows, key=lambda r: r.decided_at)[:limit]

    async def project_default(self, owner_github_id: int, project: str):  # noqa: ANN201
        self._maybe_fail()
        return self.project_defaults.get((owner_github_id, project))
