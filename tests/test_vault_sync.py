"""보관함 sync 테스트 — 합성 세션만 사용"""

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pit.personal.config import TwinConfig
from pit.vault.manifest import load_manifest
from pit.vault.policy import PauseInterval, save_pauses
from pit.vault.sync import SyncStatus, sync_all
from tests.builders import (
    DEFAULT_SESSION_ID,
    append_records,
    assistant_record,
    human_record,
    to_line,
    write_session,
)

DEVICE = "test-mac"
NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def _sync(home: Path, source: Path, config: TwinConfig | None = None):
    return sync_all(home, source, config or TwinConfig(), DEVICE, NOW)


def _vault_file(home: Path, session_id: str = DEFAULT_SESSION_ID) -> Path:
    return home / "vault" / "claude-code" / DEVICE / f"{session_id}.jsonl"


def test_sync_session_new_file_copies_and_records_manifest(tmp_path: Path):
    """새 세션은 통째로 복사되고 출처가 manifest에 남는다"""
    home, source = tmp_path / "home", tmp_path / "src"
    original = write_session(source, [human_record("안녕"), assistant_record("네")])

    report = _sync(home, source)

    assert report.count(SyncStatus.NEW) == 1
    assert _vault_file(home).read_bytes() == original.read_bytes()
    entry = load_manifest(home)[f"{DEVICE}/{DEFAULT_SESSION_ID}"]
    assert entry.cwd == "/work/demo"
    assert entry.tool_version == "2.1.270"
    assert entry.source_bytes == original.stat().st_size
    assert entry.vault_sha256 == hashlib.sha256(original.read_bytes()).hexdigest()


def test_sync_session_source_appended_copies_only_new_bytes(tmp_path: Path):
    """원본이 자라면 늘어난 부분만 이어 붙인다"""
    home, source = tmp_path / "home", tmp_path / "src"
    original = write_session(source, [human_record("첫 턴")])
    _sync(home, source)
    appended = [assistant_record("답", minute=1)]
    append_records(original, appended)

    report = _sync(home, source)

    assert report.count(SyncStatus.APPENDED) == 1
    assert report.bytes_added == len(to_line(appended[0]))
    assert _vault_file(home).read_bytes() == original.read_bytes()


def test_sync_session_partial_last_line_stops_at_newline(tmp_path: Path):
    """쓰이는 도중인 마지막 줄은 다음 sync로 미룬다"""
    home, source = tmp_path / "home", tmp_path / "src"
    original = write_session(source, [human_record("완성된 줄")])
    complete = original.read_bytes()
    append_records(original, [], raw_tail=b'{"type":"assistant","uuid":"half')

    _sync(home, source)

    assert _vault_file(home).read_bytes() == complete

    append_records(original, [], raw_tail=b'"}\n')
    _sync(home, source)

    assert _vault_file(home).read_bytes() == original.read_bytes()


def test_sync_session_unchanged_source_adds_nothing(tmp_path: Path):
    """원본이 그대로면 두 번째 sync는 아무것도 하지 않는다"""
    home, source = tmp_path / "home", tmp_path / "src"
    write_session(source, [human_record("그대로")])
    _sync(home, source)

    report = _sync(home, source)

    assert report.count(SyncStatus.UNCHANGED) == 1
    assert report.bytes_added == 0


def test_sync_session_source_rewritten_keeps_old_generation(tmp_path: Path):
    """원본이 append가 아니라 다시 쓰이면 이전 사본을 세대 파일로 남긴다"""
    home, source = tmp_path / "home", tmp_path / "src"
    original = write_session(source, [human_record("이전 내용")])
    _sync(home, source)
    old_bytes = original.read_bytes()
    original.write_bytes(to_line(human_record("완전히 다른 내용, 길이도 더 길다")))
    append_records(original, [])

    report = _sync(home, source)

    assert report.count(SyncStatus.REWRITTEN) == 1
    kept = _vault_file(home).with_name(f"{DEFAULT_SESSION_ID}.g0.jsonl")
    assert kept.read_bytes() == old_bytes
    assert _vault_file(home).read_bytes() == original.read_bytes()
    assert load_manifest(home)[f"{DEVICE}/{DEFAULT_SESSION_ID}"].generation == 1


def test_sync_all_source_deleted_keeps_vault_copy(tmp_path: Path):
    """원본이 지워져도 보관함 사본과 manifest는 남는다"""
    home, source = tmp_path / "home", tmp_path / "src"
    original = write_session(source, [human_record("곧 지워질 세션")])
    _sync(home, source)
    saved = _vault_file(home).read_bytes()
    original.unlink()

    _sync(home, source)

    assert _vault_file(home).read_bytes() == saved
    assert f"{DEVICE}/{DEFAULT_SESSION_ID}" in load_manifest(home)


def test_sync_session_private_cwd_skips_collection(tmp_path: Path):
    """개인으로 표시한 작업 디렉터리는 수집하지 않는다"""
    home, source = tmp_path / "home", tmp_path / "src"
    write_session(source, [human_record("사적인 일", cwd="/Users/me/private/diary")])

    report = _sync(home, source, TwinConfig(private_cwd_globs=["*/private/*"]))

    assert report.count(SyncStatus.SKIPPED_PRIVATE) == 1
    assert not _vault_file(home).exists()
    assert load_manifest(home) == {}


def test_sync_session_without_cwd_is_skipped(tmp_path: Path):
    """cwd를 알 수 없으면 개인 프로젝트인지 판단할 수 없으므로 수집하지 않는다"""
    home, source = tmp_path / "home", tmp_path / "src"
    write_session(source, [{"type": "mode", "sessionId": DEFAULT_SESSION_ID}])

    report = _sync(home, source)

    assert report.count(SyncStatus.SKIPPED_UNKNOWN_CWD) == 1


def test_sync_session_paused_interval_records_are_dropped(tmp_path: Path):
    """일시정지 구간의 레코드는 보관함에 들어가지 않는다"""
    home, source = tmp_path / "home", tmp_path / "src"
    home.mkdir()
    before, during, after = (
        human_record("정지 전", minute=0),
        human_record("정지 중", minute=10),
        human_record("정지 후", minute=20),
    )
    write_session(source, [before, during, after])
    save_pauses(
        home,
        [
            PauseInterval(
                start=datetime(2026, 9, 1, 10, 5, tzinfo=timezone.utc),
                end=datetime(2026, 9, 1, 10, 15, tzinfo=timezone.utc),
            )
        ],
    )

    _sync(home, source)

    assert _vault_file(home).read_bytes() == to_line(before) + to_line(after)


def test_sync_all_subagent_file_stored_under_parent(tmp_path: Path):
    """서브에이전트 파일은 부모 세션 아래에 따로 보관된다"""
    home, source = tmp_path / "home", tmp_path / "src"
    write_session(source, [human_record("부모")])
    write_session(source, [human_record("에이전트 프롬프트")], agent_name="agent-abc")

    report = _sync(home, source)

    assert report.count(SyncStatus.NEW) == 2
    sub = home / "vault/claude-code" / DEVICE / DEFAULT_SESSION_ID / "subagents/agent-abc.jsonl"
    assert sub.exists()
    assert f"{DEVICE}/{DEFAULT_SESSION_ID}/agent-abc" in load_manifest(home)


@pytest.mark.skipif(os.geteuid() == 0, reason="root는 권한을 무시한다")
def test_sync_all_unreadable_source_logs_and_continues(tmp_path: Path):
    """읽을 수 없는 파일이 있어도 나머지는 계속 처리한다"""
    home, source = tmp_path / "home", tmp_path / "src"
    locked = write_session(source, [human_record("잠김")], session_id="a" * 8)
    write_session(source, [human_record("정상")], session_id="b" * 8)
    locked.chmod(0o000)

    try:
        report = _sync(home, source)
    finally:
        locked.chmod(0o600)

    assert report.count(SyncStatus.FAILED) == 1
    assert report.count(SyncStatus.NEW) == 1
    assert _vault_file(home, "b" * 8).exists()


def test_sync_all_vault_files_are_owner_only(tmp_path: Path):
    """보관함 파일은 본인만 읽을 수 있다"""
    home, source = tmp_path / "home", tmp_path / "src"
    write_session(source, [human_record("권한 확인")])

    _sync(home, source)

    assert _vault_file(home).stat().st_mode & 0o077 == 0
