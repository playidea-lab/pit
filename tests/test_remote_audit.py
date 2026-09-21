"""로컬 pit ↔ pithub 왕복과 MCP 감사 테스트"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from pit.audit.mcp_audit import McpRecord, audit, quotes_overlap
from pit.decisions.models import (
    Decision,
    DecisionKind,
    DecisionSource,
    ExtractionMethod,
    ExtractorInfo,
    ReviewAction,
    ReviewInfo,
    Verdict,
)
from pit.personal.remote import RemoteClient, RemoteError, load_pulled, save_pulled, to_wire

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def _local(n: int, verdict: Verdict = Verdict.APPROVE, quote: str = "", confirmed: bool = True) -> Decision:
    review = ReviewInfo(action=ReviewAction.CONFIRMED, reviewed_at=NOW) if confirmed else None
    return Decision(
        id=f"PD-20260922-{n:08x}",
        person="cm",
        project="/work/demo",
        kind=DecisionKind.VERDICT,
        decided_at=NOW + timedelta(minutes=n),
        created_at=NOW,
        source=DecisionSource(tool="claude-code", device="mac", session_id="s1", verdict_uuid=f"u{n}", verdict_line_no=n),
        situation="상황",
        proposal=f"제안 {n}",
        verdict=verdict,
        human_quote=quote or f"내 말 {n} 그거 말고 다른 걸로",
        extractor=ExtractorInfo(method=ExtractionMethod.LLM),
        review=review,
    )


def _mcp(n: int, verdict: str, quote: str, offset: timedelta = timedelta(0)) -> McpRecord:
    return McpRecord(id=f"mcp-{n}", verdict=verdict, human_quote=quote, decided_at=NOW + timedelta(minutes=n) + offset)


# --- 감사 -------------------------------------------------------------------


def test_quotes_overlap_substring_either_direction_after_whitespace_normalization():
    assert quotes_overlap("아니  그거 말고", "아니 그거 말고 다른 걸로 하자")
    assert quotes_overlap("아니 그거 말고 다른 걸로 하자", "아니 그거 말고")
    assert not quotes_overlap("좋아", "아니 그거 말고")


def test_audit_counts_recall_reject_recall_and_verdict_agreement():
    local = [
        _local(1, Verdict.REJECT, "아니 그거 말고"),
        _local(2, Verdict.APPROVE, "좋아 그렇게 해"),
        _local(3, Verdict.REJECT, "그건 필요 없어"),
        _local(4, Verdict.MODIFY, "좋은데 X는 빼고"),
    ]
    mcp = [
        _mcp(1, "reject", "아니 그거 말고"),
        _mcp(2, "approve", "좋아 그렇게 해"),
        # 거부를 승인으로 누그러뜨려 기록한 경우
        _mcp(3, "approve", "그건 필요 없어"),
    ]

    report = audit(local, mcp)

    assert (report.local_total, report.mcp_total, report.matched) == (4, 3, 3)
    assert report.recall == 0.75 and report.reject_recall == 1.0
    assert report.verdict_agreement == pytest.approx(2 / 3)
    assert report.unmatched_local_ids == [local[3].id]
    assert report.gate_checks == {"recall": True, "reject_recall": True, "verdict_agreement": False}


def test_audit_ignores_unconfirmed_local_decisions_and_far_apart_records():
    local = [_local(1, Verdict.REJECT, "아니 그거 말고"), _local(2, Verdict.REJECT, "이건 초안", confirmed=False)]
    mcp = [_mcp(1, "reject", "아니 그거 말고", offset=timedelta(days=2))]

    report = audit(local, mcp)

    assert report.local_total == 1 and report.matched == 0
    assert report.gate_checks["recall"] is False


def test_audit_empty_inputs_reports_undecidable():
    report = audit([], [])

    assert report.recall is None and report.gate_checks == {"recall": None, "reject_recall": None, "verdict_agreement": None}


def test_audit_one_mcp_record_matches_at_most_one_local_decision():
    local = [_local(1, Verdict.REJECT, "아니 그거 말고"), _local(2, Verdict.REJECT, "아니 그거 말고")]
    mcp = [_mcp(1, "reject", "아니 그거 말고")]

    assert audit(local, mcp).matched == 1


# --- 원격 클라이언트 ----------------------------------------------------------


class _SyncAsgiTransport(httpx.BaseTransport):
    """동기 httpx 클라이언트로 ASGI 앱을 부른다 (CLI 클라이언트는 동기다)"""

    def __init__(self, app) -> None:  # noqa: ANN001
        self._inner = httpx.ASGITransport(app=app)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        import asyncio

        async def call() -> httpx.Response:
            response = await self._inner.handle_async_request(request)
            body = await response.aread()
            # 비동기 스트림을 동기 응답으로 바꾼다
            return httpx.Response(response.status_code, headers=response.headers, content=body)

        return asyncio.run(call())


def test_to_wire_omits_session_text_and_lets_server_assign_owner():
    wire = to_wire(_local(1, Verdict.REJECT, "아니"))

    assert wire["owner_github_id"] == 0
    assert set(wire["source"]) == {"tool", "device", "session_id", "project"}
    assert "verdict_uuid" not in str(wire["source"])


def test_remote_client_server_error_becomes_remote_error():
    client = RemoteClient(
        "https://example.test", "pit_x", httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"error": "nope"})))
    )

    with pytest.raises(RemoteError, match="401"):
        client.whoami()


def test_save_and_load_pulled_roundtrip_is_owner_only(tmp_path: Path):
    rows = [{"id": "a", "origin": "mcp"}, {"id": "b", "origin": "local_extract"}]

    path = save_pulled(tmp_path, rows)

    assert load_pulled(tmp_path) == rows
    assert path.stat().st_mode & 0o077 == 0


@pytest.mark.skipif(pytest.importorskip("fastmcp", reason="server extra") is None, reason="server extra")
def test_push_and_pull_roundtrip_through_real_server():
    """로컬 클라이언트 → 실제 서버 코드(인메모리 ASGI) → 가짜 저장소 → 다시 로컬"""
    from pit.server.app import build_server
    from pit.server.settings import ServerSettings
    from pit.server.tokens import generate_token, hash_token
    from tests.fakes import InMemoryRepository

    repository = InMemoryRepository()
    token = generate_token()
    repository.tokens[hash_token(token)] = (1001, "alice")
    settings = ServerSettings(
        github_client_id="placeholder-id", github_client_secret="placeholder-secret",
        base_url="http://127.0.0.1:8000", host="127.0.0.1", port=8000,
    )  # fmt: skip
    transport = _SyncAsgiTransport(build_server(settings, repository).http_app())
    client = RemoteClient("http://test", token, httpx.Client(transport=transport))

    assert client.whoami()["github_login"] == "alice"
    assert client.push([_local(1, Verdict.REJECT, "아니 그거 말고"), _local(2)]) == 2
    pulled = client.pull()

    assert len(pulled) == 2
    assert {row["origin"] for row in pulled} == {"local_extract"}
    assert {row["source"]["local_id"] for row in pulled} == {_local(1).id, _local(2).id}
