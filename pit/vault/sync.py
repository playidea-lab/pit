"""세션 원문을 보관함으로 복사

세션 파일은 append 전용이고 한 파일이 수십 일에 걸쳐 자란다. 그래서 매번 통째로
복사하지 않고 지난번에 멈춘 곳부터 마지막 개행까지만 이어 붙인다.
원본이 사라져도 보관함의 사본은 지우지 않는다 — 그게 이 모듈의 존재 이유다.
"""

import hashlib
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import BinaryIO

from pit.personal.config import TwinConfig
from pit.personal.home import ensure_home
from pit.vault.manifest import ManifestEntry, load_manifest, write_manifest
from pit.vault.policy import CollectionPolicy, filter_paused, is_collectable, load_pauses
from pit.vault.sources import SOURCE_TOOL, SessionFile, discover_sessions, peek_session_meta

logger = logging.getLogger(__name__)

HASH_CHUNK_BYTES = 1024 * 1024
TAIL_SCAN_CHUNK_BYTES = 64 * 1024
VAULT_FILE_MODE = 0o600
VAULT_DIR_MODE = 0o700
NEWLINE = b"\n"


class SyncStatus(str, Enum):
    NEW = "new"
    APPENDED = "appended"
    UNCHANGED = "unchanged"
    REWRITTEN = "rewritten"
    SKIPPED_PRIVATE = "skipped_private"
    SKIPPED_UNKNOWN_CWD = "skipped_unknown_cwd"
    FAILED = "failed"


@dataclass(frozen=True)
class SyncResult:
    key: str
    status: SyncStatus
    bytes_added: int = 0
    entry: ManifestEntry | None = None


@dataclass
class SyncReport:
    results: list[SyncResult] = field(default_factory=list)

    def count(self, status: SyncStatus) -> int:
        return sum(1 for result in self.results if result.status == status)

    @property
    def bytes_added(self) -> int:
        return sum(result.bytes_added for result in self.results)


def vault_relpath(device: str, src: SessionFile) -> Path:
    base = Path("vault") / SOURCE_TOOL / device
    if src.agent_name is None:
        return base / f"{src.session_id}.jsonl"
    return base / src.session_id / "subagents" / f"{src.agent_name}.jsonl"


def sync_all(
    home: Path, source_root: Path, config: TwinConfig, device: str, now: datetime
) -> SyncReport:
    """루트 아래 모든 세션을 보관함에 반영한다

    파일 하나가 실패해도 나머지는 계속한다. manifest는 중간에 죽어도 그때까지의
    결과가 남도록 마지막에 반드시 쓴다.
    """
    ensure_home(home)
    entries = load_manifest(home)
    policy = CollectionPolicy(
        private_cwd_globs=config.private_cwd_globs, pauses=load_pauses(home)
    )
    report = SyncReport()

    try:
        for src in discover_sessions(source_root):
            manifest_key = f"{device}/{src.key}"
            try:
                result = sync_session(src, home, entries.get(manifest_key), policy, device, now)
            except OSError as e:
                logger.warning(
                    "세션 파일을 읽지 못해 건너뜀",
                    extra={"key": src.key, "error": type(e).__name__},
                )
                result = SyncResult(key=src.key, status=SyncStatus.FAILED)
            if result.entry is not None:
                entries[manifest_key] = result.entry
            report.results.append(result)
    finally:
        write_manifest(home, entries)

    return report


def sync_session(
    src: SessionFile,
    home: Path,
    entry: ManifestEntry | None,
    policy: CollectionPolicy,
    device: str,
    now: datetime,
) -> SyncResult:
    """세션 파일 하나를 보관함에 반영한다"""
    stat = src.path.stat()
    target = home / vault_relpath(device, src)
    unchanged = entry is not None and entry.source_mtime_ns == stat.st_mtime_ns
    if unchanged and target.exists():
        return SyncResult(key=src.key, status=SyncStatus.UNCHANGED, entry=entry)

    meta = peek_session_meta(src.path)
    cwd = meta.cwd or (entry.cwd if entry else None)
    if cwd is None:
        return SyncResult(key=src.key, status=SyncStatus.SKIPPED_UNKNOWN_CWD)
    if not is_collectable(cwd, policy):
        return SyncResult(key=src.key, status=SyncStatus.SKIPPED_PRIVATE)

    target.parent.mkdir(mode=VAULT_DIR_MODE, parents=True, exist_ok=True)

    hasher, start, generation, status = _resume_point(src.path, target, entry, stat.st_size)
    end = _last_newline_offset(src.path, start, stat.st_size)
    added = _copy_range(src.path, target, start, end, hasher, policy, append=start > 0)

    if status is SyncStatus.APPENDED and end == start:
        status = SyncStatus.UNCHANGED

    new_entry = ManifestEntry(
        key=src.key,
        tool=SOURCE_TOOL,
        device=device,
        session_id=src.session_id,
        agent_name=src.agent_name,
        cwd=cwd,
        tool_version=meta.version or (entry.tool_version if entry else None),
        source_path=str(src.path),
        source_bytes=end,
        source_prefix_sha256=hasher.hexdigest(),
        source_mtime_ns=stat.st_mtime_ns,
        vault_relpath=str(vault_relpath(device, src)),
        vault_bytes=target.stat().st_size,
        vault_sha256=_sha256_file(target),
        generation=generation,
        synced_at=now,
    )
    return SyncResult(key=src.key, status=status, bytes_added=added, entry=new_entry)


def _resume_point(
    source: Path, target: Path, entry: ManifestEntry | None, source_size: int
) -> tuple["hashlib._Hash", int, int, SyncStatus]:
    """어디서부터 복사할지 정한다: (이어 갈 해시, 시작 오프셋, 세대, 상태)"""
    if entry is None or not target.exists():
        return hashlib.sha256(), 0, 0, SyncStatus.NEW

    if source_size >= entry.source_bytes:
        hasher = _hash_prefix(source, entry.source_bytes)
        if hasher.hexdigest() == entry.source_prefix_sha256:
            return hasher, entry.source_bytes, entry.generation, SyncStatus.APPENDED

    # 원본이 append가 아니라 다시 쓰였다. 이전 사본은 세대 파일로 남긴다.
    kept = target.with_name(f"{target.stem}.g{entry.generation}{target.suffix}")
    target.replace(kept)
    logger.warning("원본이 다시 쓰여 이전 사본을 세대 파일로 보존", extra={"key": entry.key})
    return hashlib.sha256(), 0, entry.generation + 1, SyncStatus.REWRITTEN


def _hash_prefix(path: Path, length: int) -> "hashlib._Hash":
    hasher = hashlib.sha256()
    remaining = length
    with path.open("rb") as f:
        while remaining > 0:
            chunk = f.read(min(HASH_CHUNK_BYTES, remaining))
            if not chunk:
                break
            hasher.update(chunk)
            remaining -= len(chunk)
    return hasher


def _sha256_file(path: Path) -> str:
    return _hash_prefix(path, path.stat().st_size).hexdigest()


def _last_newline_offset(path: Path, start: int, size: int) -> int:
    """[start, size) 안에서 마지막 개행 바로 뒤의 오프셋. 개행이 없으면 start.

    쓰이는 도중의 마지막 줄(개행 없음)은 다음 sync로 미룬다.
    """
    position = size
    with path.open("rb") as f:
        while position > start:
            chunk_start = max(start, position - TAIL_SCAN_CHUNK_BYTES)
            f.seek(chunk_start)
            index = f.read(position - chunk_start).rfind(NEWLINE)
            if index >= 0:
                return chunk_start + index + 1
            position = chunk_start
    return start


def _iter_source_lines(f: BinaryIO, end: int, hasher: "hashlib._Hash") -> Iterator[bytes]:
    """현재 위치부터 end까지 줄 단위로 읽으며 원본 지문을 갱신한다"""
    remaining = end - f.tell()
    for line in f:
        if len(line) > remaining:
            break
        remaining -= len(line)
        hasher.update(line)
        yield line


def _copy_range(
    source: Path,
    target: Path,
    start: int,
    end: int,
    hasher: "hashlib._Hash",
    policy: CollectionPolicy,
    append: bool,
) -> int:
    """원본의 [start, end)를 보관함 파일에 쓴다. 쓴 바이트 수를 돌려준다."""
    written = 0
    with source.open("rb") as src_file, target.open("ab" if append else "wb") as dst_file:
        src_file.seek(start)
        lines = _iter_source_lines(src_file, end, hasher)
        if policy.pauses:
            lines = filter_paused(lines, policy.pauses)
        for line in lines:
            dst_file.write(line)
            written += len(line)
    target.chmod(VAULT_FILE_MODE)
    return written
