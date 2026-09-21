"""세션 파싱 테스트 — 합성 레코드만 사용"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from pit.personal.config import TwinConfig
from pit.transcripts.classify import classify_user, queued_human_text
from pit.transcripts.events import build_events, split_segments
from pit.transcripts.reader import ReadStats, iter_records
from pit.transcripts.records import EventKind, RawRecord, UserKind
from pit.transcripts.redact import RedactionRules, redact
from pit.transcripts.view import MAX_EVENT_CHARS, render_view
from pit.transcripts.view_cache import load_view_events, refresh_view
from pit.vault.manifest import load_manifest
from pit.vault.sync import sync_all
from tests.builders import (
    DEFAULT_SESSION_ID,
    append_records,
    assistant_record,
    human_record,
    queued_record,
    to_line,
    tool_result_record,
    tool_use_record,
    undated_record,
    write_session,
)

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
DEVICE = "test-mac"


def _raw(data: dict) -> RawRecord:
    return RawRecord(line_no=1, data=data)


def _session(tmp_path: Path, records: list[dict]) -> Path:
    return write_session(tmp_path, records)


# --- 사람 발화 판별 ---------------------------------------------------------


def test_classify_user_tool_result_block_returns_tool_result():
    assert classify_user(_raw(tool_result_record("t1"))) is UserKind.TOOL_RESULT


def test_classify_user_tool_use_result_field_returns_tool_result():
    assert classify_user(_raw(human_record("x", toolUseResult="denied"))) is UserKind.TOOL_RESULT


def test_classify_user_is_meta_returns_injected():
    assert classify_user(_raw(human_record("자동 주입", isMeta=True))) is UserKind.INJECTED


def test_classify_user_compact_summary_returns_injected():
    assert classify_user(_raw(human_record("요약", isCompactSummary=True))) is UserKind.INJECTED


def test_classify_user_peer_origin_returns_injected():
    """다른 에이전트가 보낸 자연어는 글만 봐서는 사람과 구분되지 않는다"""
    record = human_record("이것 좀 봐 줘", origin={"kind": "peer"})

    assert classify_user(_raw(record)) is UserKind.INJECTED


def test_classify_user_harness_tag_prefix_returns_injected():
    record = human_record("<task-notification>작업 완료</task-notification>")

    assert classify_user(_raw(record)) is UserKind.INJECTED


def test_classify_user_missing_prompt_source_returns_human():
    """구버전 레코드에는 promptSource·origin이 없다. 부재를 '사람 아님'으로 읽지 않는다."""
    assert classify_user(_raw(human_record("그거 말고 다른 방법으로"))) is UserKind.HUMAN


def test_classify_user_content_block_list_returns_human():
    record = human_record("")
    record["message"]["content"] = [{"type": "text", "text": "블록으로 온 사람 글"}]

    assert classify_user(_raw(record)) is UserKind.HUMAN


def test_classify_user_interrupt_marker_returns_interrupt():
    record = human_record("[Request interrupted by user for tool use]")

    assert classify_user(_raw(record)) is UserKind.INTERRUPT


def test_queued_human_text_human_prompt_returns_text():
    assert queued_human_text(_raw(queued_record("잠깐, 그 방향 아니야"))) == "잠깐, 그 방향 아니야"


def test_queued_human_text_task_notification_returns_none():
    record = queued_record("<task-notification>done</task-notification>", mode="task-notification", origin_kind=None)

    assert queued_human_text(_raw(record)) is None


def test_queued_human_text_peer_origin_returns_none():
    assert queued_human_text(_raw(queued_record("에이전트가 보낸 글", origin_kind="peer"))) is None


# --- 리더 -------------------------------------------------------------------


def test_iter_records_duplicate_uuid_keeps_first(tmp_path: Path):
    first, duplicate = human_record("처음"), human_record("중복")
    path = _session(tmp_path, [first, duplicate])
    stats = ReadStats()

    records = list(iter_records(path, stats))

    assert [r.data["message"]["content"] for r in records] == ["처음"]
    assert stats.duplicate_uuid == 1


def test_iter_records_malformed_line_skips_and_counts(tmp_path: Path):
    path = _session(tmp_path, [human_record("정상")])
    append_records(path, [], raw_tail=b"{broken json\n[1, 2]\n")
    stats = ReadStats()

    records = list(iter_records(path, stats))

    assert len(records) == 1
    assert stats.malformed == 2


# --- 이벤트 -----------------------------------------------------------------


def test_build_events_split_message_id_joins_text(tmp_path: Path):
    """한 assistant 메시지가 여러 레코드로 쪼개져 와도 하나의 제안으로 합쳐진다"""
    part1 = assistant_record("방법은 두 가지입니다.", minute=1, message_id="m1")
    part2 = assistant_record("A안을 권합니다.", minute=1, message_id="m1")
    part2["uuid"] = "a-1-m1-second"
    path = _session(tmp_path, [human_record("어떻게 할까", minute=0), part1, part2])

    events = build_events(path)

    assert [e.kind for e in events] == [EventKind.HUMAN, EventKind.ASSISTANT]
    assert events[1].text == "방법은 두 가지입니다.\nA안을 권합니다."
    assert events[1].uuid == part1["uuid"]


def test_build_events_only_allow_listed_records_are_used(tmp_path: Path):
    """세션 제목·마지막 프롬프트·요약처럼 '나중 일'을 담은 레코드는 이벤트가 되지 않는다"""
    records = [
        undated_record("ai-title", aiTitle="LEAK-TITLE"),
        undated_record("last-prompt", lastPrompt="LEAK-LAST-PROMPT"),
        {"type": "system", "subtype": "away_summary", "content": "LEAK-AWAY", "uuid": "s1"},
        {"type": "queue-operation", "content": "LEAK-QUEUE"},
        human_record("LEAK-SUMMARY", minute=1, isCompactSummary=True),
        human_record("진짜 발화", minute=2),
    ]
    path = _session(tmp_path, records)

    events = build_events(path)

    assert [e.text for e in events] == ["진짜 발화"]


def test_build_events_sidechain_records_excluded(tmp_path: Path):
    sidechain = human_record("부모 에이전트가 쓴 프롬프트", minute=1)
    sidechain["isSidechain"] = True
    path = _session(tmp_path, [sidechain, human_record("사람", minute=2)])

    assert [e.text for e in build_events(path)] == ["사람"]


def test_build_events_ask_user_question_becomes_choice_event(tmp_path: Path):
    questions = [
        {
            "question": "어느 쪽으로 할까요?",
            "multiSelect": False,
            "options": [{"label": "A안", "description": "빠름"}, {"label": "B안", "description": "안전"}],
        }
    ]
    result = tool_result_record(
        "q1", minute=2, toolUseResult={"questions": questions, "answers": {"어느 쪽으로 할까요?": "B안"}, "annotations": {}}
    )
    path = _session(tmp_path, [tool_use_record("q1", "AskUserQuestion", {"questions": questions}, minute=1), result])

    events = build_events(path)

    assert len(events) == 1 and events[0].kind is EventKind.CHOICE
    assert [o.label for o in events[0].questions[0].options] == ["A안", "B안"]
    assert events[0].answers == {"어느 쪽으로 할까요?": "B안"}


def test_build_events_non_dict_tool_use_result_is_ignored(tmp_path: Path):
    path = _session(tmp_path, [tool_result_record("t1", toolUseResult="plain string")])

    assert build_events(path) == []


def test_build_events_user_rejected_becomes_denial_with_tool_name(tmp_path: Path):
    use = tool_use_record("t9", "Bash", {"command": "rm -rf build"}, minute=1)
    denied = tool_result_record("t9", minute=2, toolDenialKind="user-rejected", toolUseResult="rejected")
    path = _session(tmp_path, [use, denied])

    events = build_events(path)

    assert len(events) == 1 and events[0].kind is EventKind.DENIAL
    assert events[0].tool_name == "Bash"
    assert "rm -rf build" in events[0].text


def test_build_events_permission_rule_denial_is_not_a_human_verdict(tmp_path: Path):
    """자동 권한 규칙이 막은 것은 사람의 판정이 아니다"""
    use = tool_use_record("t3", "Bash", {"command": "ls"}, minute=1)
    blocked = tool_result_record("t3", minute=2, toolDenialKind="permission-rule", toolUseResult="blocked")
    path = _session(tmp_path, [use, blocked])

    assert build_events(path) == []


def test_build_events_queued_prompt_is_human_event_marked_queued(tmp_path: Path):
    path = _session(tmp_path, [assistant_record("작업 중입니다", minute=1), queued_record("멈춰, 방향이 틀렸어", minute=2)])

    events = build_events(path)

    assert events[-1].kind is EventKind.HUMAN and events[-1].queued is True


def test_build_events_same_text_in_attachment_and_user_is_not_duplicated(tmp_path: Path):
    path = _session(tmp_path, [queued_record("같은 글", minute=1), human_record("같은 글", minute=2)])

    assert len(build_events(path)) == 1


def test_build_events_interrupted_message_id_is_kept_on_human_event(tmp_path: Path):
    path = _session(tmp_path, [human_record("아니 그거 말고", minute=1, interruptedMessageId="m7")])

    assert build_events(path)[0].interrupted_message_id == "m7"


def test_split_segments_idle_gap_exceeded_starts_new_segment(tmp_path: Path):
    records = [human_record("아침", minute=0), human_record("바로 이어서", minute=5)]
    late = human_record("다음 날", minute=0)
    late["uuid"], late["timestamp"] = "u-late", "2026-09-02T10:00:00.000Z"
    path = _session(tmp_path, [*records, late])

    segments = split_segments(build_events(path), idle_gap=timedelta(hours=4))

    assert [[e.text for e in segment] for segment in segments] == [["아침", "바로 이어서"], ["다음 날"]]


# --- 가림·뷰·캐시 -----------------------------------------------------------


def test_redact_api_key_pattern_is_masked():
    # 가짜 키는 실행 중에 조립한다 (소스에 키 모양의 문자열을 두지 않기 위함)
    fake_key = "sk-ant-" + "a1B2" * 6

    result = redact(f"키는 {fake_key} 입니다", RedactionRules())

    assert fake_key not in result.text
    assert result.counts["anthropic_key"] == 1


def test_redact_assigned_secret_is_masked():
    result = redact("DB_PASSWORD=hunter2hunter2 로 접속", RedactionRules())

    assert "hunter2" not in result.text


def test_redact_resident_number_and_email_are_masked():
    result = redact("900101-1234567 / someone@example.com", RedactionRules())

    assert "900101" not in result.text and "example.com" not in result.text


def test_redact_customer_term_is_masked_case_insensitively():
    result = redact("AcmeCorp 와 acmecorp 납품 건", RedactionRules(customer_terms=("AcmeCorp",)))

    assert "acme" not in result.text.lower()
    assert result.counts["customer_term"] == 2


def test_redact_plain_text_is_unchanged():
    text = "결정 단위로 시작하는 데 동의. 일은 그 다음."

    assert redact(text, RedactionRules()).text == text


def test_render_view_labels_map_back_to_events(tmp_path: Path):
    path = _session(tmp_path, [human_record("질문", minute=0), assistant_record("제안", minute=1)])
    events = build_events(path)

    view = render_view(events)

    assert view.lines == ["[H1] 질문", "[A2] 제안"]
    assert view.by_label["A2"] is events[1]


def test_render_view_long_text_is_clipped_keeping_head_and_tail(tmp_path: Path):
    long_text = "머리" + "x" * (MAX_EVENT_CHARS * 3) + "꼬리"
    path = _session(tmp_path, [human_record(long_text)])

    rendered = render_view(build_events(path)).text

    assert len(rendered) < MAX_EVENT_CHARS + 200
    assert "머리" in rendered and "꼬리" in rendered and "중략" in rendered


def _synced_entry(home: Path, source: Path):
    sync_all(home, source, TwinConfig(), DEVICE, NOW)
    return load_manifest(home)[f"{DEVICE}/{DEFAULT_SESSION_ID}"]


def test_refresh_view_secret_in_human_text_never_reaches_cache(tmp_path: Path):
    home, source = tmp_path / "home", tmp_path / "src"
    write_session(source, [human_record("토큰은 " + "ghp_" + "abcd1234" * 4 + " 이야")])
    entry = _synced_entry(home, source)

    meta = refresh_view(home, entry, TwinConfig())

    cached = (home / "views" / DEVICE / f"{DEFAULT_SESSION_ID}.jsonl").read_text(encoding="utf-8")
    assert "ghp_" not in cached
    assert meta.redactions == {"github_token": 1}


def test_refresh_view_restricted_cwd_returns_empty_view(tmp_path: Path):
    """고객 데이터가 섞이는 프로젝트는 보관은 하되 뷰를 만들지 않는다"""
    home, source = tmp_path / "home", tmp_path / "src"
    write_session(source, [human_record("고객 데이터 이야기", cwd="/work/customer-x/train")])
    entry = _synced_entry(home, source)

    meta = refresh_view(home, entry, TwinConfig(restricted_cwd_globs=["*/customer-x/*"]))

    assert meta.restricted is True and meta.events == 0
    assert load_view_events(home, entry) == []
    assert (home / entry.vault_relpath).read_bytes() == to_line(
        human_record("고객 데이터 이야기", cwd="/work/customer-x/train")
    )


def test_refresh_view_unchanged_vault_reuses_cache(tmp_path: Path):
    home, source = tmp_path / "home", tmp_path / "src"
    write_session(source, [human_record("한 번만 파싱")])
    entry = _synced_entry(home, source)
    refresh_view(home, entry, TwinConfig())
    events_path = home / "views" / DEVICE / f"{DEFAULT_SESSION_ID}.jsonl"
    events_path.write_text("", encoding="utf-8")

    refresh_view(home, entry, TwinConfig())

    assert events_path.read_text(encoding="utf-8") == ""


def test_refresh_view_appended_session_rebuilds_cache(tmp_path: Path):
    home, source = tmp_path / "home", tmp_path / "src"
    original = write_session(source, [human_record("첫 발화", minute=0)])
    entry = _synced_entry(home, source)
    refresh_view(home, entry, TwinConfig())
    append_records(original, [human_record("둘째 발화", minute=5)])
    entry = _synced_entry(home, source)

    meta = refresh_view(home, entry, TwinConfig())

    assert meta.events == 2
