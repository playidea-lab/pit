from git_watcher.gitlab import Account, Commit
from git_watcher.work_reports import CheckedCommit, Judgment, by_decision, compare, matches, verify


def commit(sha: str, message: str = "feat: x") -> Commit:
    return Commit(sha=sha, project="org/app", title=message, message=message,
                  authored_at="2026-10-05T10:00:00+09:00", additions=10, deletions=2, files=["src/a.py"])


class FakeSummarizer:
    def __init__(self, reply: str) -> None:
        self.reply = reply

    def ask(self, system_prompt: str, text: str) -> str:
        return self.reply


def test_matches_handles_short_and_full_hashes() -> None:
    assert matches("a1b2c3d4e5f60718", "a1b2c3d4") and matches("a1b2c3d4", "a1b2c3d4e5f6")
    assert not matches("ffff0000", "a1b2c3d4")


def test_verify_counts_missing_reports_per_person() -> None:
    accounts = {"alice": Account("alice", "Alice", [commit("aaaa1111"), commit("bbbb2222")])}
    reports = [{"id": "W-1", "kind": "commit", "owner_github_id": 1, "commit_sha": "aaaa1111ffff",
                "atomic": True, "message_ok": True}]
    (alice,) = verify(accounts, reports, {1: "alice"}, None)
    assert alice.missing == 1 and alice.checked[0].report is not None


def test_compare_flags_claims_that_disagree_with_judgment_and_size() -> None:
    checked = CheckedCommit(commit("aaaa1111"),
                            report={"atomic": True, "message_ok": True},
                            start={"expected_manual_hours": 20},
                            judgment=Judgment(atomic=False, message_ok=True, manual_low=2, manual_high=4,
                                              reason="리팩터와 기능이 섞임"))
    flags = compare(checked)
    assert any("원자적이라 보고" in f for f in flags) and any("예상 20시간" in f for f in flags)


def test_verify_judges_only_reported_commits() -> None:
    reply = '{"atomic": true, "message_ok": false, "manual_low": 1, "manual_high": 2, "reason": "r"}'
    accounts = {"alice": Account("alice", "Alice", [commit("aaaa1111"), commit("bbbb2222")])}
    reports = [{"id": "W-1", "kind": "commit", "owner_github_id": 1, "commit_sha": "aaaa1111",
                "atomic": True, "message_ok": True}]
    (alice,) = verify(accounts, reports, {1: "alice"}, FakeSummarizer(reply))  # type: ignore[arg-type]
    reported, unreported = alice.checked
    assert reported.judgment is not None and unreported.judgment is None
    assert reported.flags == ["메시지가 충분하다 보고했지만 판정은 부족"]


def test_by_decision_groups_under_goal_or_marks_unlinked() -> None:
    a = CheckedCommit(commit("aaaa1111"), report={"implements": ["D-1"]})
    b = CheckedCommit(commit("bbbb2222"), report={"implements": []}, start={"implements": ["D-1"]})
    c = CheckedCommit(commit("cccc3333"), report={"implements": []})
    from git_watcher.work_reports import NO_DECISION, PersonWork
    groups = by_decision([PersonWork("alice", [a, b, c])], {"D-1": "10월 목표: 1.0 납품"})
    assert [len(groups["10월 목표: 1.0 납품"]), len(groups[NO_DECISION])] == [2, 1]


def test_pithub_client_builds_postgrest_filters_and_encodes_timezone() -> None:
    from datetime import datetime, timezone

    import httpx
    from git_watcher.work_reports import PithubClient
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    with PithubClient("https://db.example", "k") as ph:
        ph._http._transport = httpx.MockTransport(handler)  # 네트워크 없이 요청 모양만 본다
        ph.reports(datetime(2026, 10, 5, tzinfo=timezone.utc), datetime(2026, 10, 6, tzinfo=timezone.utc))
        assert ph.logins([]) == {} and ph.decision_titles([]) == {}  # 빈 목록은 요청하지 않는다
    (req,) = seen
    assert req.url.path == "/rest/v1/work_reports"
    assert req.url.params["and"] == "(reported_at.gte.2026-10-05T00:00:00+00:00,reported_at.lt.2026-10-06T00:00:00+00:00)"
    assert "%2B00%3A00" in str(req.url)  # '+' 가 공백으로 바뀌지 않게 인코딩
    assert req.headers["apikey"] == "k"
