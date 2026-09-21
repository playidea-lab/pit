"""개인 보관함 위치·초기화·설정·스냅샷 테스트"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from pit.core.context import find_pit_root
from pit.personal.config import ConfigError, load_config
from pit.personal.home import PersonalHomeError, ensure_home, resolve_pit_home
from pit.vault.manifest import MANIFEST_RELPATH, ManifestEntry, load_manifest, write_manifest
from pit.vault.policy import PauseInterval, end_pause, filter_paused, load_pauses, start_pause
from pit.vault.snapshot import snapshot_control_inputs
from tests.builders import human_record, to_line, undated_record

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def test_resolve_pit_home_env_set_returns_env_path(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PIT_HOME", str(tmp_path / "custom"))

    assert resolve_pit_home() == tmp_path / "custom"


def test_resolve_pit_home_env_unset_returns_dot_pit_under_home(monkeypatch):
    monkeypatch.delenv("PIT_HOME", raising=False)

    assert resolve_pit_home() == Path.home() / ".pit"


def test_find_pit_root_personal_home_present_returns_none(tmp_path: Path):
    """개인 보관함이 있어도 프로젝트 탐지는 그것을 프로젝트로 보지 않는다

    ~/.pit 에 config.yaml 이 생기면 홈 아래 모든 폴더에서 팀 결정이 개인 보관함에
    저장되는 사고가 난다. 그 회귀를 막는 테스트다.
    """
    fake_home = tmp_path / "user"
    ensure_home(fake_home / ".pit")
    workdir = fake_home / "git" / "some-repo"
    workdir.mkdir(parents=True)

    assert find_pit_root(workdir) is None


def test_ensure_home_project_marker_present_raises_error(tmp_path: Path):
    """프로젝트의 .pit/ 폴더를 개인 보관함으로 쓰려 하면 거부한다"""
    project_pit = tmp_path / ".pit"
    project_pit.mkdir()
    (project_pit / "config.yaml").write_text("id: demo\n", encoding="utf-8")

    with pytest.raises(PersonalHomeError):
        ensure_home(project_pit)


def test_ensure_home_creates_gitignore_excluding_raw_data(tmp_path: Path):
    """원문과 캐시는 개인 git repo에서도 제외된다"""
    home = tmp_path / "home"

    ensure_home(home)

    ignored = (home / ".gitignore").read_text(encoding="utf-8").split()
    assert {"vault/", "views/", "candidates/", "snapshots/", "cache/"} <= set(ignored)
    assert "decisions/" not in ignored
    assert home.stat().st_mode & 0o077 == 0


def test_load_config_missing_file_returns_defaults(tmp_path: Path):
    config = load_config(tmp_path)

    assert config.private_cwd_globs == []
    assert config.person_id


def test_load_config_invalid_field_type_raises_config_error(tmp_path: Path):
    (tmp_path / "twin.yaml").write_text("private_cwd_globs: not-a-list\n", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_filter_paused_undated_record_next_to_paused_is_dropped():
    """timestamp 없는 레코드는 앞뒤 중 하나라도 정지 구간이면 함께 빠진다

    last-prompt 같은 레코드에는 사람의 프롬프트 원문이 들어 있다.
    """
    pause = PauseInterval(
        start=datetime(2026, 9, 1, 10, 5, tzinfo=timezone.utc),
        end=datetime(2026, 9, 1, 10, 15, tzinfo=timezone.utc),
    )
    kept_first = to_line(human_record("전", minute=0))
    undated_before_pause = to_line(undated_record(lastPrompt="정지 중에 친 말"))
    paused = to_line(human_record("정지 중", minute=10))
    undated_after_pause = to_line(undated_record(lastPrompt="역시 정지 중"))
    kept_last = to_line(human_record("후", minute=20))
    undated_tail = to_line(undated_record(lastPrompt="정지와 무관"))

    lines = [kept_first, undated_before_pause, paused, undated_after_pause, kept_last, undated_tail]

    assert list(filter_paused(lines, [pause])) == [kept_first, kept_last, undated_tail]


def test_start_pause_already_paused_returns_false(tmp_path: Path):
    assert start_pause(tmp_path, NOW) is True
    assert start_pause(tmp_path, NOW) is False
    assert end_pause(tmp_path, NOW) is True
    assert end_pause(tmp_path, NOW) is False
    assert load_pauses(tmp_path)[0].end == NOW


def _entry(key: str) -> ManifestEntry:
    return ManifestEntry(
        key=key, tool="claude-code", device="mac", session_id=key, source_path="/x",
        source_bytes=1, source_prefix_sha256="0", source_mtime_ns=1,
        vault_relpath="v", vault_bytes=1, vault_sha256="0", synced_at=NOW,
    )  # fmt: skip


def test_write_manifest_interrupted_write_leaves_old_manifest(tmp_path: Path, monkeypatch):
    """쓰는 도중 실패해도 이전 manifest가 그대로 남는다"""
    write_manifest(tmp_path, {"mac/s1": _entry("s1")})

    def boom(fd: int) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("pit.vault.manifest.os.fsync", boom)
    with pytest.raises(OSError):
        write_manifest(tmp_path, {"mac/s1": _entry("s1"), "mac/s2": _entry("s2")})

    assert list(load_manifest(tmp_path)) == ["mac/s1"]


def test_load_manifest_malformed_line_is_skipped(tmp_path: Path):
    write_manifest(tmp_path, {"mac/s1": _entry("s1")})
    with (tmp_path / MANIFEST_RELPATH).open("a", encoding="utf-8") as f:
        f.write("{not json}\n")

    assert list(load_manifest(tmp_path)) == ["mac/s1"]


def test_snapshot_control_inputs_unchanged_content_reuses_blob(tmp_path: Path):
    """내용이 같으면 새 스냅샷을 만들지 않고, 바뀌면 새 지문이 추가된다"""
    claude_home, home = tmp_path / "claude", tmp_path / "home"
    (claude_home / "rules").mkdir(parents=True)
    (claude_home / "CLAUDE.md").write_text("규칙 v1", encoding="utf-8")
    (claude_home / "rules" / "a.md").write_text("a", encoding="utf-8")
    ensure_home(home)
    globs = ["CLAUDE.md", "rules/*.md"]

    first = snapshot_control_inputs(claude_home, home, globs, NOW)
    second = snapshot_control_inputs(claude_home, home, globs, NOW)
    (claude_home / "CLAUDE.md").write_text("규칙 v2", encoding="utf-8")
    third = snapshot_control_inputs(claude_home, home, globs, NOW)

    assert first is not None and set(first.files) == {"CLAUDE.md", "rules/a.md"}
    assert second is None
    assert third is not None and third.files["CLAUDE.md"] != first.files["CLAUDE.md"]
    assert third.files["rules/a.md"] == first.files["rules/a.md"]
    assert len(list((home / "snapshots" / "blobs").iterdir())) == 3
