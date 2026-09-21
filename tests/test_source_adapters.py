"""소스 어댑터 규약 테스트 — 새 도구를 붙이는 자리가 실제로 열려 있는지"""

import logging
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pit.personal.config import TwinConfig
from pit.transcripts.view_cache import load_view_events, refresh_view
from pit.vault.manifest import load_manifest
from pit.vault.sources import SessionFile, SessionMeta, UnknownSourceError, get_source
from pit.vault.sync import SyncStatus, sync_all

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
DEVICE = "test-mac"


class FakeToolSource:
    """Claude Code와 전혀 다른 배치·형식을 가진 가상의 도구"""

    tool = "fake-tool"

    def default_root(self) -> Path:
        return Path("/nonexistent")

    def discover(self, root: Path) -> Iterator[SessionFile]:
        for path in sorted(root.glob("*.log")):
            yield SessionFile(path=path, session_id=path.stem)

    def peek_meta(self, path: Path) -> SessionMeta:
        return SessionMeta(cwd="/work/from-fake-tool", version="9.9")


def test_get_source_default_is_claude_code():
    assert get_source().tool == "claude-code"


def test_get_source_unknown_tool_raises_error():
    with pytest.raises(UnknownSourceError, match="codex"):
        get_source("codex")


def test_sync_all_custom_adapter_stores_under_its_own_tool_directory(tmp_path: Path):
    home, source_root = tmp_path / "home", tmp_path / "src"
    source_root.mkdir()
    (source_root / "session-a.log").write_bytes(b"line one\nline two\n")

    report = sync_all(home, source_root, TwinConfig(), DEVICE, NOW, source=FakeToolSource())

    entry = load_manifest(home)[f"{DEVICE}/session-a"]
    assert report.count(SyncStatus.NEW) == 1
    assert entry.tool == "fake-tool" and entry.cwd == "/work/from-fake-tool"
    assert entry.vault_relpath == f"vault/fake-tool/{DEVICE}/session-a.jsonl"
    assert (home / entry.vault_relpath).read_bytes() == b"line one\nline two\n"


def test_refresh_view_tool_without_parser_is_kept_but_not_parsed(tmp_path: Path, caplog):
    """파서가 없는 도구의 세션은 보관만 되고, 뷰 단계는 죽지 않고 건너뛴다"""
    home, source_root = tmp_path / "home", tmp_path / "src"
    source_root.mkdir()
    (source_root / "session-a.log").write_bytes(b"not claude code format\n")
    sync_all(home, source_root, TwinConfig(), DEVICE, NOW, source=FakeToolSource())
    entry = load_manifest(home)[f"{DEVICE}/session-a"]

    with caplog.at_level(logging.WARNING):
        meta = refresh_view(home, entry, TwinConfig())

    assert meta.unsupported is True and meta.events == 0
    assert load_view_events(home, entry) == []
    assert any("파서가 없는 도구" in record.message for record in caplog.records)
