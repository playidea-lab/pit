"""결정 후보 추출 테스트 — 합성 세션과 가짜 LLM만 사용"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from pit.decisions.ids import make_decision_id
from pit.decisions.models import (
    OTHER_CHOICE,
    DecisionKind,
    RejectKind,
    ReviewAction,
    ReviewInfo,
    Verdict,
)
from pit.decisions.store import ReviewEvent, append_review_event, load_candidates
from pit.extract.anchors import RawPairLabel, resolve_anchor
from pit.extract.llm_extract import compact_for_extraction, split_windows
from pit.extract.pipeline import ExtractionLimits, run_extraction
from pit.extract.structured import SourceContext, extract_structured
from pit.llm.client import LLMError, ModelTask, require_model_id
from pit.personal.config import TwinConfig
from pit.transcripts.events import build_events
from pit.transcripts.view import render_view
from pit.vault.sync import sync_all
from tests.builders import (
    DEFAULT_SESSION_ID,
    assistant_record,
    human_record,
    tool_result_record,
    tool_use_record,
    write_session,
)
from tests.fakes import FakeLLMClient

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
DEVICE = "test-mac"
MODEL = "test-model"
CTX = SourceContext(
    person="cm", tool="claude-code", device=DEVICE, session_id=DEFAULT_SESSION_ID, cwd="/work/demo", now=NOW
)


def _choice_records(answer: str) -> list[dict]:
    questions = [
        {
            "question": "어느 쪽으로 할까요?",
            "multiSelect": False,
            "options": [{"label": "A안", "description": ""}, {"label": "B안", "description": ""}],
        }
    ]
    result = tool_result_record(
        "q1", minute=2, toolUseResult={"questions": questions, "answers": {"어느 쪽으로 할까요?": answer}}
    )
    return [
        assistant_record("두 가지 방법이 있습니다.", minute=1, message_id="m-ctx"),
        tool_use_record("q1", "AskUserQuestion", {"questions": questions}, minute=1),
        result,
    ]


def _label(**overrides: object) -> dict:
    base = {
        "proposal_label": "A2",
        "verdict_label": "H3",
        "verdict": "modify",
        "reject_kind": None,
        "situation": "캐시 전략을 정하던 중",
        "proposal": "전체를 매번 다시 읽는 방식",
        "rationale": "",
        "human_quote": "바뀐 세션만 다시 읽자",
    }
    return {**base, **overrides}


PAIR = [
    human_record("캐시를 어떻게 할까", minute=0),
    assistant_record("매번 전체를 다시 읽겠습니다.", minute=1, message_id="m1"),
    human_record("좋은데 바뀐 세션만 다시 읽자", minute=2),
]


# --- ID · 구조 신호 ---------------------------------------------------------


def test_make_decision_id_same_inputs_returns_same_id():
    first = make_decision_id("s1", "u1", NOW)
    assert first == make_decision_id("s1", "u1", NOW)
    assert first != make_decision_id("s1", "u1", NOW, part=1)
    assert first.startswith("PD-20260922-")


def test_extract_structured_ask_user_question_maps_label_to_chosen(tmp_path: Path):
    events = build_events(write_session(tmp_path, _choice_records("B안")))

    (decision,) = extract_structured(events, CTX)

    assert decision.kind is DecisionKind.CHOICE
    assert decision.options == ["A안", "B안"] and decision.chosen == "B안"
    assert decision.situation == "두 가지 방법이 있습니다."
    assert decision.verdict is None


def test_extract_structured_free_text_answer_maps_to_other(tmp_path: Path):
    events = build_events(write_session(tmp_path, _choice_records("둘 다 말고 C로")))

    (decision,) = extract_structured(events, CTX)

    assert decision.chosen == OTHER_CHOICE
    assert decision.human_quote == "둘 다 말고 C로"


def test_extract_structured_user_rejected_yields_reject_anchored_to_reason(tmp_path: Path):
    records = [
        assistant_record("빌드 폴더를 지우겠습니다.", minute=1),
        tool_use_record("t9", "Bash", {"command": "rm -rf build"}, minute=1),
        tool_result_record("t9", minute=2, toolDenialKind="user-rejected", toolUseResult="rejected"),
        human_record("지우지 말고 옮겨", minute=3),
    ]
    events = build_events(write_session(tmp_path, records))

    (decision,) = extract_structured(events, CTX)

    assert decision.verdict is Verdict.REJECT and decision.reject_kind is RejectKind.REDIRECT
    assert decision.source.verdict_uuid == "u-3"
    assert decision.human_quote == "지우지 말고 옮겨"


# --- 닻 검증 ----------------------------------------------------------------


def _view(tmp_path: Path):
    return render_view(build_events(write_session(tmp_path, PAIR)))


def test_resolve_anchor_valid_label_returns_events(tmp_path: Path):
    result = resolve_anchor(_view(tmp_path), RawPairLabel.model_validate(_label()))

    assert result.ok and result.proposal.uuid == "a-1-m1" and result.verdict.uuid == "u-2"


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"verdict_label": "H99"}, "unknown_label"),
        ({"verdict_label": "A2", "proposal_label": "A2"}, "verdict_not_human"),
        ({"proposal_label": "H1"}, "proposal_not_assistant"),
        ({"verdict_label": "H1"}, "proposal_after_verdict"),
        ({"human_quote": "사람이 하지 않은 말"}, "quote_not_in_utterance"),
    ],
)
def test_resolve_anchor_invalid_label_is_rejected(tmp_path: Path, overrides: dict, error: str):
    result = resolve_anchor(_view(tmp_path), RawPairLabel.model_validate(_label(**overrides)))

    assert result.error == error


# --- 윈도 -------------------------------------------------------------------


def test_compact_for_extraction_keeps_only_tail_assistant_messages(tmp_path: Path):
    records = [human_record("시작", minute=0)]
    records += [assistant_record(f"중간 보고 {i}", minute=i, message_id=f"m{i}") for i in range(1, 6)]
    records.append(human_record("좋아", minute=9))
    events = build_events(write_session(tmp_path, records))

    kept = [e.text for e in compact_for_extraction(events)]

    assert kept == ["시작", "중간 보고 4", "중간 보고 5", "좋아"]


def test_split_windows_never_separates_proposal_from_reaction(tmp_path: Path):
    records = []
    for i in range(4):
        records.append(assistant_record("제안 " + "가" * 50, minute=i * 2, message_id=f"m{i}"))
        records.append(human_record(f"반응 {i}", minute=i * 2 + 1))
    events = build_events(write_session(tmp_path, records))

    windows = split_windows(events, max_chars=130)

    assert len(windows) > 1
    assert all(w[0].kind.value == "A" and w[-1].kind.value == "H" for w in windows)


# --- 파이프라인 -------------------------------------------------------------


def _home_with(tmp_path: Path, records: list[dict]) -> Path:
    home, source = tmp_path / "home", tmp_path / "src"
    write_session(source, records)
    sync_all(home, source, TwinConfig(), DEVICE, NOW)
    return home


def _run(home: Path, client: FakeLLMClient | None, **limits: object):
    return run_extraction(home, TwinConfig(person_id="cm"), client, MODEL, ExtractionLimits(**limits), NOW)


def test_run_extraction_llm_label_becomes_candidate_with_source(tmp_path: Path):
    home = _home_with(tmp_path, PAIR)
    client = FakeLLMClient(responses=[{"decisions": [_label()]}])

    report = _run(home, client)

    (candidate,) = load_candidates(home)
    assert report.llm == 1 and report.calls == 1
    assert candidate.verdict is Verdict.MODIFY
    assert candidate.source.verdict_uuid == "u-2" and candidate.source.proposal_uuid == "a-1-m1"
    assert candidate.extractor.model == MODEL and candidate.extractor.prompt_hash
    assert candidate.review is None


def test_run_extraction_processed_pair_is_not_resent(tmp_path: Path):
    home = _home_with(tmp_path, PAIR)
    client = FakeLLMClient(responses=[{"decisions": [_label()]}])
    _run(home, client)

    report = _run(home, client)

    assert report.calls == 0 and len(client.requests) == 1


def test_run_extraction_invalid_anchor_is_counted_not_saved(tmp_path: Path):
    home = _home_with(tmp_path, PAIR)
    client = FakeLLMClient(responses=[{"decisions": [_label(human_quote="지어낸 인용")]}])

    report = _run(home, client)

    assert load_candidates(home) == []
    assert report.errors["quote_not_in_utterance"] == 1


def test_run_extraction_invalid_schema_retries_once_then_records_error(tmp_path: Path):
    home = _home_with(tmp_path, PAIR)
    client = FakeLLMClient(responses=[{"decisions": [{"verdict": "maybe"}]}, {"wrong": True}])

    report = _run(home, client)

    assert len(client.requests) == 2
    assert report.errors["ValidationError"] == 1
    assert _run(home, FakeLLMClient(responses=[{"decisions": []}])).calls == 1


def test_run_extraction_api_error_is_recorded_and_retried_next_run(tmp_path: Path):
    home = _home_with(tmp_path, PAIR)

    report = _run(home, FakeLLMClient(responses=[LLMError("rate limited")]))

    assert report.errors["LLMError"] == 1 and load_candidates(home) == []


def test_run_extraction_structured_wins_over_llm_duplicate(tmp_path: Path):
    records = [
        assistant_record("빌드 폴더를 지우겠습니다.", minute=1, message_id="m1"),
        tool_use_record("t9", "Bash", {"command": "rm -rf build"}, minute=1),
        tool_result_record("t9", minute=2, toolDenialKind="user-rejected", toolUseResult="rejected"),
        human_record("지우지 말고 옮겨", minute=3),
    ]
    home = _home_with(tmp_path, records)
    duplicate = _label(proposal_label="A1", verdict_label="H3", verdict="reject", human_quote="지우지 말고 옮겨")

    report = _run(home, FakeLLMClient(responses=[{"decisions": [duplicate]}]))

    (candidate,) = load_candidates(home)
    assert candidate.extractor.method.value == "structured"
    assert report.structured == 1 and report.llm == 0 and report.already_known == 1


def test_run_extraction_discarded_candidate_does_not_reappear(tmp_path: Path):
    home = _home_with(tmp_path, _choice_records("B안"))
    _run(home, None)
    (candidate,) = load_candidates(home)
    (home / "candidates" / f"{candidate.id}.json").unlink()
    review = ReviewInfo(action=ReviewAction.DISCARDED, reviewed_at=NOW)
    append_review_event(home, ReviewEvent(decision_id=candidate.id, review=review, extractor_method="structured"))

    report = _run(home, None)

    assert load_candidates(home) == [] and report.already_known == 1


def test_run_extraction_dry_run_counts_calls_without_saving(tmp_path: Path):
    home = _home_with(tmp_path, PAIR)
    client = FakeLLMClient()

    report = _run(home, client, dry_run=True)

    assert report.planned_calls == 1 and report.calls == 0
    assert client.requests == [] and load_candidates(home) == []


def test_run_extraction_max_calls_limits_llm_usage(tmp_path: Path):
    home = _home_with(tmp_path, PAIR)

    report = _run(home, FakeLLMClient(), max_calls=0)

    assert report.calls == 0 and report.planned_calls == 1


def test_require_model_id_missing_raises_llm_error(monkeypatch):
    monkeypatch.delenv("PIT_MODEL_EXTRACT", raising=False)

    with pytest.raises(LLMError):
        require_model_id({}, ModelTask.EXTRACT)


def test_require_model_id_env_overrides_config(monkeypatch):
    monkeypatch.setenv("PIT_MODEL_EXTRACT", "from-env")

    assert require_model_id({"extract": "from-config"}, ModelTask.EXTRACT) == "from-env"
