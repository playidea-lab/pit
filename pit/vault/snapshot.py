"""통제군 입력(CLAUDE.md · rules · memory)의 시점별 스냅샷

트윈은 "지금의 memory + rules만 준 LLM"과 비교된다. 그런데 이 파일들은 git으로
추적되지 않아 과거 시점의 상태를 복원할 수 없다. 그래서 sync할 때마다 내용을
지문으로 저장해, 적어도 오늘부터는 "그 시점에 무엇이 있었나"를 답할 수 있게 한다.
"""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = Path("snapshots")
BLOBS_DIRNAME = "blobs"
INDEX_FILENAME = "index.jsonl"
SNAPSHOT_FILE_MODE = 0o600


class SnapshotRef(BaseModel):
    """한 시점의 통제군 입력 목록"""

    taken_at: datetime
    # claude_home 기준 상대 경로 → 내용의 sha256
    files: dict[str, str]


def snapshot_control_inputs(
    claude_home: Path, home: Path, globs: list[str], now: datetime
) -> SnapshotRef | None:
    """통제군 입력을 내용 주소로 저장한다

    직전 스냅샷과 내용이 같으면 아무것도 쓰지 않고 None을 돌려준다.
    """
    files = _collect(claude_home, home, globs)
    last = load_latest_snapshot(home)
    if last is not None and last.files == files:
        return None

    ref = SnapshotRef(taken_at=now, files=files)
    index = home / SNAPSHOT_DIR / INDEX_FILENAME
    with index.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ref.model_dump(mode="json"), ensure_ascii=False) + "\n")
    index.chmod(SNAPSHOT_FILE_MODE)
    return ref


def load_latest_snapshot(home: Path) -> SnapshotRef | None:
    index = home / SNAPSHOT_DIR / INDEX_FILENAME
    if not index.exists():
        return None
    lines = [line for line in index.read_text(encoding="utf-8").splitlines() if line.strip()]
    return SnapshotRef.model_validate_json(lines[-1]) if lines else None


def _collect(claude_home: Path, home: Path, globs: list[str]) -> dict[str, str]:
    blobs = home / SNAPSHOT_DIR / BLOBS_DIRNAME
    blobs.mkdir(parents=True, exist_ok=True)

    files: dict[str, str] = {}
    for pattern in globs:
        for path in sorted(claude_home.glob(pattern)):
            if not path.is_file():
                continue
            try:
                content = path.read_bytes()
            except OSError as e:
                logger.warning(
                    "통제군 입력을 읽지 못해 건너뜀",
                    extra={"path": str(path), "error": type(e).__name__},
                )
                continue
            digest = hashlib.sha256(content).hexdigest()
            blob = blobs / digest
            if not blob.exists():
                blob.write_bytes(content)
                blob.chmod(SNAPSHOT_FILE_MODE)
            files[str(path.relative_to(claude_home))] = digest
    return files
