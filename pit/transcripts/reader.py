"""세션 JSONL 스트리밍 리더

파일 하나가 수백 MB일 수 있어 줄 단위로만 읽는다. 같은 uuid가 두 번 나오는 경우가
실제로 있어 첫 등장만 채택한다. 순서의 기준은 timestamp가 아니라 줄 순서다
(timestamp 역전과 timestamp 없는 레코드가 존재한다).
"""

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from pit.transcripts.records import RawRecord

logger = logging.getLogger(__name__)


@dataclass
class ReadStats:
    """읽는 동안 버린 줄의 수 (리더를 다 소비한 뒤에 확정된다)"""

    malformed: int = 0
    duplicate_uuid: int = 0


def iter_records(path: Path, stats: ReadStats | None = None) -> Iterator[RawRecord]:
    """세션 파일의 레코드를 줄 순서대로 돌려준다

    Args:
        path: 세션 JSONL 경로
        stats: 버린 줄 수를 받을 객체 (선택)
    """
    stats = stats if stats is not None else ReadStats()
    seen: set[str] = set()

    with path.open("rb") as f:
        for line_no, line in enumerate(f, start=1):
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                stats.malformed += 1
                continue
            if not isinstance(data, dict):
                stats.malformed += 1
                continue

            record = RawRecord(line_no=line_no, data=data)
            if record.uuid is not None:
                if record.uuid in seen:
                    stats.duplicate_uuid += 1
                    continue
                seen.add(record.uuid)
            yield record

    if stats.malformed:
        logger.warning(
            "해석할 수 없는 줄을 건너뜀", extra={"path": path.name, "count": stats.malformed}
        )
