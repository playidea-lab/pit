"""검토·조회·통계 테스트"""

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

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
from pit.decisions.query import (
    DecisionQuery,
    filter_decisions,
    review_stats,
    sample_for_gate1,
    wilson_lower_bound,
)
from pit.decisions.review import ReviewCommand, ReviewInput, run_review_session
from pit.decisions.store import (
    ReviewEvent,
    load_candidates,
    load_decisions,
    load_review_events,
    save_candidate,
    save_decision_record,
    superseded_by,
)
from pit.personal.home import ensure_home
from tests.fakes import FakeClock

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def _candidate(
    n: int,
    method: ExtractionMethod = ExtractionMethod.LLM,
    session: str = "s1",
    project: str = "/work/demo",
    verdict: Verdict = Verdict.APPROVE,
    **fields: object,
) -> Decision:
    return Decision(
        id=f"PD-20260901-{n:08x}",
        person="cm",
        project=project,
        kind=DecisionKind.VERDICT,
        decided_at=datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc) + timedelta(minutes=n),
        created_at=NOW,
        source=DecisionSource(
            tool="claude-code", device="mac", session_id=session, verdict_uuid=f"u-{n}", verdict_line_no=n
        ),
        situation=f"상황 {n}",
        proposal=f"제안 {n}",
        verdict=verdict,
        human_quote=f"말 {n}",
        extractor=ExtractorInfo(method=method),
        **fields,
    )


def _home(tmp_path: Path, candidates: list[Decision]) -> Path:
    home = tmp_path / "home"
    ensure_home(home)
    for candidate in candidates:
        save_candidate(home, candidate)
    return home


def _scripted(inputs: list[ReviewInput]):
    queue = list(inputs)
    return lambda candidate: queue.pop(0)


def _git_log(home: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(home), "log", "--format=%s"], capture_output=True, text=True, check=True
    )
    return result.stdout.strip().splitlines()


def test_review_confirm_writes_decision_and_event(tmp_path: Path):
    home = _home(tmp_path, [_candidate(1)])

    summary = run_review_session(
        home, load_candidates(home), _scripted([ReviewInput(ReviewCommand.CONFIRM)]), FakeClock(2.5), NOW
    )

    (decision,) = load_decisions(home)
    (event,) = load_review_events(home)
    assert summary.confirmed == 1 and load_candidates(home) == []
    assert decision.review.action is ReviewAction.CONFIRMED
    assert event.decision_id == decision.id and event.review.seconds == 2.5


def test_review_verdict_hotkey_records_edited_fields(tmp_path: Path):
    home = _home(tmp_path, [_candidate(1, verdict=Verdict.APPROVE)])
    edit = ReviewInput(ReviewCommand.EDIT, edits={"verdict": Verdict.REJECT})

    summary = run_review_session(home, load_candidates(home), _scripted([edit]), FakeClock(), NOW)

    (decision,) = load_decisions(home)
    assert summary.edited == 1
    assert decision.verdict is Verdict.REJECT
    assert decision.review.edited_fields == ["verdict"]


def test_review_edit_without_change_counts_as_confirmed(tmp_path: Path):
    home = _home(tmp_path, [_candidate(1)])
    edit = ReviewInput(ReviewCommand.EDIT, edits={"situation": "상황 1"})

    summary = run_review_session(home, load_candidates(home), _scripted([edit]), FakeClock(), NOW)

    assert summary.confirmed == 1 and summary.edited == 0


def test_review_edit_of_protected_field_raises_error(tmp_path: Path):
    home = _home(tmp_path, [_candidate(1)])
    edit = ReviewInput(ReviewCommand.EDIT, edits={"id": "PD-hacked"})

    with pytest.raises(ValueError, match="id"):
        run_review_session(home, load_candidates(home), _scripted([edit]), FakeClock(), NOW)


def test_review_edit_with_invalid_verdict_raises_validation_error(tmp_path: Path):
    home = _home(tmp_path, [_candidate(1)])
    edit = ReviewInput(ReviewCommand.EDIT, edits={"verdict": "maybe"})

    with pytest.raises(ValidationError):
        run_review_session(home, load_candidates(home), _scripted([edit]), FakeClock(), NOW)


def test_review_discard_records_event_without_decision(tmp_path: Path):
    home = _home(tmp_path, [_candidate(1)])

    summary = run_review_session(
        home, load_candidates(home), _scripted([ReviewInput(ReviewCommand.DISCARD)]), FakeClock(), NOW
    )

    assert summary.discarded == 1
    assert load_decisions(home) == [] and load_candidates(home) == []
    assert load_review_events(home)[0].review.action is ReviewAction.DISCARDED


def test_review_session_end_makes_single_commit_without_raw_data(tmp_path: Path):
    home = _home(tmp_path, [_candidate(1), _candidate(2), _candidate(3)])
    (home / "vault" / "raw.jsonl").write_text("원문", encoding="utf-8")
    inputs = [ReviewInput(ReviewCommand.CONFIRM), ReviewInput(ReviewCommand.DISCARD), ReviewInput(ReviewCommand.CONFIRM)]

    summary = run_review_session(home, load_candidates(home), _scripted(inputs), FakeClock(), NOW)

    assert summary.committed is True
    assert _git_log(home) == ["review: +2 confirmed, 0 edited, 1 discarded"]
    tracked = subprocess.run(
        ["git", "-C", str(home), "ls-files"], capture_output=True, text=True, check=True
    ).stdout
    assert "decisions/" in tracked and "reviews.jsonl" in tracked
    assert "vault" not in tracked and "candidates" not in tracked


def test_review_quit_stops_and_skip_keeps_candidate(tmp_path: Path):
    home = _home(tmp_path, [_candidate(1), _candidate(2), _candidate(3)])
    inputs = [ReviewInput(ReviewCommand.SKIP), ReviewInput(ReviewCommand.QUIT)]

    summary = run_review_session(home, load_candidates(home), _scripted(inputs), FakeClock(), NOW)

    assert summary.skipped == 1 and summary.committed is False
    assert len(load_candidates(home)) == 3


def test_review_structured_candidates_come_first(tmp_path: Path):
    home = _home(tmp_path, [_candidate(1), _candidate(2, method=ExtractionMethod.STRUCTURED)])
    seen: list[str] = []

    def ask(candidate: Decision) -> ReviewInput:
        seen.append(candidate.id)
        return ReviewInput(ReviewCommand.SKIP)

    run_review_session(home, load_candidates(home), ask, FakeClock(), NOW)

    assert seen == ["PD-20260901-00000002", "PD-20260901-00000001"]


def test_commit_failure_preserves_review_results(tmp_path: Path, monkeypatch):
    """git이 실패해도 확정한 결정은 파일로 남는다"""
    home = _home(tmp_path, [_candidate(1)])

    def broken_git(*args: object, **kwargs: object):
        raise OSError("git not found")

    monkeypatch.setattr("pit.personal.gitrepo.subprocess.run", broken_git)

    summary = run_review_session(
        home, load_candidates(home), _scripted([ReviewInput(ReviewCommand.CONFIRM)]), FakeClock(), NOW
    )

    assert summary.committed is False and len(load_decisions(home)) == 1


def test_load_decisions_supersedes_derives_superseded_by(tmp_path: Path):
    home = _home(tmp_path, [])
    old, new = _candidate(1), _candidate(2, supersedes=["PD-20260901-00000001"])
    for decision in (old, new):
        save_decision_record(home, decision)

    decisions = load_decisions(home)

    assert superseded_by(decisions) == {old.id: [new.id]}
    assert "superseded_by" not in (home / "decisions" / f"{old.id}.md").read_text(encoding="utf-8")


def test_load_decisions_malformed_file_is_skipped(tmp_path: Path):
    home = _home(tmp_path, [])
    save_decision_record(home, _candidate(1))
    (home / "decisions" / "PD-broken.md").write_text("---\nid: only-id\n---\n", encoding="utf-8")

    assert [d.id for d in load_decisions(home)] == ["PD-20260901-00000001"]


def test_filter_decisions_across_projects_returns_person_scoped():
    decisions = [
        _candidate(1, project="/git/borch", rationale="기준선 설정부터 확인"),
        _candidate(2, project="/git/ocudu", rationale="기준선이 최약 모드였다"),
        _candidate(3, project="/git/pit", rationale="무관한 이야기"),
    ]

    found = filter_decisions(decisions, DecisionQuery(person="cm", text="기준선"))

    assert [d.project for d in found] == ["/git/borch", "/git/ocudu"]
    assert filter_decisions(decisions, DecisionQuery(person="someone-else")) == []


def test_sample_for_gate1_caps_per_session_and_structured():
    candidates = [_candidate(i, session="big") for i in range(50)]
    candidates += [_candidate(100 + i, method=ExtractionMethod.STRUCTURED, session=f"s{i}") for i in range(40)]

    sample = sample_for_gate1(candidates)

    assert sum(1 for d in sample if d.source.session_id == "big") == 10
    assert sum(1 for d in sample if d.extractor.method is ExtractionMethod.STRUCTURED) == 30
    assert [d.id for d in sample] == [d.id for d in sample_for_gate1(list(reversed(candidates)))]


def _event(action: ReviewAction, fields: list[str], seconds: float) -> ReviewEvent:
    review = ReviewInfo(action=action, edited_fields=fields, seconds=seconds, reviewed_at=NOW)
    return ReviewEvent(decision_id="PD-x", review=review, extractor_method="llm")


def test_review_stats_counts_light_edits_as_usable_and_verdict_edits_as_flips():
    events = [
        _event(ReviewAction.CONFIRMED, [], 4.0),
        _event(ReviewAction.EDITED, ["situation"], 8.0),
        _event(ReviewAction.EDITED, ["verdict"], 12.0),
        _event(ReviewAction.DISCARDED, [], 2.0),
    ]

    stats = review_stats(events)

    assert stats.reviewed == 4
    assert stats.usable_rate == 0.5 and stats.verdict_flip_rate == 0.25
    assert stats.median_seconds == 6.0 and stats.p90_seconds == 12.0
    assert stats.gate1_checks["usable_rate"] is False and stats.gate1_checks["median_seconds"] is True


def test_review_stats_no_events_returns_none():
    assert review_stats([]) is None


def test_wilson_lower_bound_is_below_point_estimate_and_zero_safe():
    assert wilson_lower_bound(0, 0) == 0.0
    assert 0.60 < wilson_lower_bound(84, 120) < 0.70
