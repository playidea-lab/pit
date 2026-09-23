"""테스트용 가짜 구현"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from pit.llm.client import LLMError, StructuredRequest
from pit.server.records import is_team_shared
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
        # github_id → [(team_id, slug)] — 수락까지 끝난 팀만
        self.memberships: dict[int, list[tuple[str, str]]] = {}
        # slug → team_id (존재하는 팀)
        self.teams: dict[str, str] = {}
        # (team_id, github_id) — 승인 대기 중인 가입 요청
        self.join_requests: set[tuple[str, int]] = set()
        self.fail_with: Exception | None = None
        # 팀 공유 유예를 따질 때 쓰는 시각 — 테스트가 고정한다
        self.now = lambda: datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)

    def _maybe_fail(self) -> None:
        if self.fail_with is not None:
            raise self.fail_with

    async def ensure_account(self, github_id: int, github_login: str) -> None:
        self._maybe_fail()
        self.accounts[github_id] = github_login

    async def insert_draft(self, decision) -> bool:  # noqa: ANN001
        self._maybe_fail()
        # DB가 채우는 created_at 을 흉내 낸다
        if decision.created_at is None:
            decision = decision.model_copy(update={"created_at": self.now()})
        duplicate = any(
            row.owner_github_id == decision.owner_github_id and row.dedupe_key == decision.dedupe_key
            for row in self.rows
        )
        if duplicate:
            return False
        self.rows.append(decision)
        return True

    async def search_recorded(self, owner_github_id: int, query: str, limit: int) -> list:
        self._maybe_fail()
        needle = query.lower()
        found = [
            row
            for row in self.rows
            if row.owner_github_id == owner_github_id
            and row.status != "discarded"
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

    async def find_recent_same_proposal(self, owner_github_id: int, project, proposal_normalized: str, since):  # noqa: ANN001, ANN201
        self._maybe_fail()
        for row in sorted(self.rows, key=lambda r: r.decided_at, reverse=True):
            same_project = row.source.get("project") == project
            if (row.owner_github_id == owner_github_id and same_project and row.status != "discarded"
                    and row.decided_at >= since and " ".join(row.proposal.split()).lower() == proposal_normalized):
                return row
        return None

    async def bump_repeat(self, decision_id: str) -> None:
        self.rows = [r.model_copy(update={"repeat_count": r.repeat_count + 1}) if r.id == decision_id else r for r in self.rows]

    async def owns_all(self, owner_github_id: int, decision_ids: list[str]) -> bool:
        mine = {r.id for r in self.rows if r.owner_github_id == owner_github_id}
        return set(decision_ids) <= mine

    async def record_search(self, owner_github_id: int, query: str, returned_ids: list[str], client) -> None:  # noqa: ANN001
        self.searches = getattr(self, "searches", []) + [(owner_github_id, query, returned_ids)]

    async def mark_cited(self, owner_github_id: int, decision_id: str) -> None:
        self.rows = [
            r.model_copy(update={"cited_count": r.cited_count + 1})
            if r.id == decision_id and r.owner_github_id == owner_github_id else r
            for r in self.rows
        ]

    async def member_teams(self, github_id: int) -> list[tuple[str, str]]:
        self._maybe_fail()
        return list(self.memberships.get(github_id, []))

    async def search_team(self, team_ids: list[str], query: str, limit: int) -> list:
        self._maybe_fail()
        needle = query.lower()
        found = [
            row
            for row in self.rows
            if row.team_id in team_ids and is_team_shared(row, self.now())
            and needle in f"{row.situation} {row.proposal} {row.rationale} {row.human_quote}".lower()
        ]
        return found[:limit]

    async def get_by_id(self, decision_id: str):  # noqa: ANN201
        self._maybe_fail()
        return next((row for row in self.rows if row.id == decision_id), None)

    async def logins_of(self, github_ids: list[int]) -> dict[int, str]:
        return {github_id: self.accounts.get(github_id, f"user{github_id}") for github_id in github_ids}

    async def find_team(self, slug: str) -> str | None:
        return self.teams.get(slug)

    async def request_join(self, team_id: str, github_id: int) -> None:
        self.join_requests.add((team_id, github_id))

    async def record_transfer(self, decision, reader_github_id: int, via: str, client) -> None:  # noqa: ANN001
        self.transfers = getattr(self, "transfers", []) + [(decision.id, decision.owner_github_id, reader_github_id, via, client)]

    # --- 판단 그래프 (G2) ---

    async def resolve_node(self, namespace, kind: str, name: str, norm: str, created_by: int) -> str:  # noqa: ANN001
        self.nodes = getattr(self, "nodes", {})
        key = (namespace.team_id, namespace.owner_github_id, kind, norm)
        if key not in self.nodes:
            self.nodes[key] = (f"N{len(self.nodes) + 1}", name)
        return self.nodes[key][0]

    async def attach_nodes(self, decision_id: str, node_ids: list[str]) -> None:
        self.decision_nodes = getattr(self, "decision_nodes", set()) | {(decision_id, n) for n in node_ids}

    async def add_links(self, from_decision: str, links: list, created_by: int) -> None:
        self.links = getattr(self, "links", set()) | {(from_decision, to, rel, status) for to, rel, status in links}

    async def topics_of(self, decision_ids: list[str]) -> dict[str, list[str]]:
        names = {node_id: name for node_id, name in getattr(self, "nodes", {}).values()}
        topics: dict[str, list[str]] = {}
        for decision_id, node_id in sorted(getattr(self, "decision_nodes", set())):
            if decision_id in decision_ids:
                topics.setdefault(decision_id, []).append(names[node_id])
        return topics

    # --- 판단 그래프 읽기 (G4) ---

    async def find_nodes(self, team_ids: list[str], owner_github_id: int, norm_query: str, limit: int) -> list[str]:
        hits = [
            node_id for (team, owner, _kind, norm), (node_id, _name) in getattr(self, "nodes", {}).items()
            if (team in team_ids or owner == owner_github_id) and norm_query and norm_query in norm
        ]  # fmt: skip
        return hits[:limit]

    async def decision_ids_on_nodes(self, node_ids: list[str], limit: int) -> list[str]:
        return list(dict.fromkeys(d for d, n in sorted(getattr(self, "decision_nodes", set())) if n in node_ids))[:limit]

    async def get_many(self, decision_ids: list[str]) -> list:
        return [row for row in self.rows if row.id in decision_ids]

    async def links_of(self, decision_id: str) -> list:
        return [(frm, to, rel, status) for frm, to, rel, status in getattr(self, "links", set()) if decision_id in (frm, to)]

    # --- 트윈 (G6) ---

    async def find_account(self, github_login: str):  # noqa: ANN201
        departed = getattr(self, "departed", set())
        for github_id, login in self.accounts.items():
            if login == github_login:
                return github_id, github_id in departed
        return None

    async def team_decisions_of(self, owner_github_id: int, team_ids: list[str], limit: int) -> list:
        rows = [r for r in self.rows if r.owner_github_id == owner_github_id and r.visibility == "team"
                and r.team_id in team_ids and r.status != "discarded"]  # fmt: skip
        return rows[:limit]

    async def record_consult(self, asker: int, twin: int, question: str, decision_ids: list, confidence: float, abstained: bool) -> None:
        self.consults = getattr(self, "consults", []) + [(asker, twin, question, decision_ids, abstained)]

    async def create_twin_question(self, asker: int, twin: int, team_id, situation: str, proposal: str, confidence: float) -> None:  # noqa: ANN001
        self.twin_questions = getattr(self, "twin_questions", []) + [(asker, twin, team_id, proposal)]
