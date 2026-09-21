"""보관함 manifest — 각 사본의 출처와 어디까지 복사했는지

manifest.jsonl 한 줄이 파일 하나다. 다음 sync가 이어서 복사할 위치(source_bytes)와,
원본이 append가 아니라 다시 쓰였는지 판별할 지문(source_prefix_sha256)을 담는다.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

MANIFEST_RELPATH = Path("vault") / "manifest.jsonl"
MANIFEST_FILE_MODE = 0o600


class ManifestEntry(BaseModel):
    """보관된 세션 파일 하나의 출처 기록"""

    key: str
    tool: str
    device: str
    session_id: str
    agent_name: str | None = None
    cwd: str | None = None
    tool_version: str | None = None

    source_path: str
    # 원본에서 소비한 바이트 수 (마지막 개행까지)
    source_bytes: int
    # 원본의 [0, source_bytes) 구간 sha256 — 다르면 append가 아니라 다시 쓰인 것
    source_prefix_sha256: str
    source_mtime_ns: int

    vault_relpath: str
    vault_bytes: int
    vault_sha256: str
    # 원본이 다시 쓰일 때마다 1씩 늘고, 이전 세대 파일은 따로 남는다
    generation: int = 0
    synced_at: datetime

    @property
    def manifest_key(self) -> str:
        return f"{self.device}/{self.key}"


def load_manifest(home: Path) -> dict[str, ManifestEntry]:
    """manifest를 읽어 'device/key' → entry 로 돌려준다. 깨진 줄은 건너뛴다."""
    path = home / MANIFEST_RELPATH
    if not path.exists():
        return {}

    entries: dict[str, ManifestEntry] = {}
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                entry = ManifestEntry.model_validate_json(line)
            except ValidationError as e:
                logger.warning(
                    "manifest 줄을 읽을 수 없어 건너뜀",
                    extra={"line_no": line_no, "error_count": e.error_count()},
                )
                continue
            entries[entry.manifest_key] = entry
    return entries


def write_manifest(home: Path, entries: dict[str, ManifestEntry]) -> None:
    """manifest 전체를 원자적으로 다시 쓴다

    임시 파일에 다 쓴 뒤 rename한다. 쓰는 도중 죽어도 이전 manifest가 그대로 남는다.
    """
    path = home / MANIFEST_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".jsonl.tmp")

    with tmp_path.open("w", encoding="utf-8") as f:
        for manifest_key in sorted(entries):
            f.write(json.dumps(entries[manifest_key].model_dump(mode="json"), ensure_ascii=False))
            f.write("\n")
        f.flush()
        os.fsync(f.fileno())

    tmp_path.chmod(MANIFEST_FILE_MODE)
    tmp_path.replace(path)
