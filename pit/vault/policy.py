"""수집 정책 — 무엇을 보관함에 넣지 않을지

되돌릴 수 없는 것(개인적인 일)은 입력 단계에서 뺀다. 보관함에 들어온 뒤에 가리는
방식은 한 번 새면 끝이기 때문이다.
"""

import json
import logging
from collections.abc import Iterable, Iterator
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

PAUSES_FILENAME = "pauses.json"


class PauseInterval(BaseModel):
    """기록 일시정지 구간. end가 None이면 아직 정지 중."""

    start: datetime
    end: datetime | None = None

    def contains(self, at: datetime) -> bool:
        return self.start <= at and (self.end is None or at < self.end)


class CollectionPolicy(BaseModel):
    """한 번의 sync에 적용할 수집 정책"""

    private_cwd_globs: list[str] = Field(default_factory=list)
    pauses: list[PauseInterval] = Field(default_factory=list)


def is_collectable(cwd: str | None, policy: CollectionPolicy) -> bool:
    """이 작업 디렉터리의 세션을 수집해도 되는가

    cwd를 모르면 수집하지 않는다. 개인 프로젝트인지 판단할 수 없고, cwd가 없는
    파일에는 대화 레코드도 없어서 잃는 것이 없다. 다음 sync에서 다시 본다.
    """
    if cwd is None:
        return False
    return not any(fnmatch(cwd, pattern) for pattern in policy.private_cwd_globs)


def filter_paused(lines: Iterable[bytes], pauses: list[PauseInterval]) -> Iterator[bytes]:
    """일시정지 구간에 속한 레코드를 뺀다

    timestamp가 없는 레코드에도 사람의 프롬프트 원문이 들어 있다(last-prompt 등).
    그래서 앞뒤의 timestamp 있는 레코드 중 하나라도 정지 구간이면 함께 뺀다.
    해석할 수 없는 줄도 같은 규칙을 따른다.
    """
    previous_dropped = False
    undated: list[bytes] = []
    for line in lines:
        at = _record_time(line)
        if at is None:
            undated.append(line)
            continue
        dropped = any(pause.contains(at) for pause in pauses)
        if not (previous_dropped or dropped):
            yield from undated
        undated = []
        if not dropped:
            yield line
        previous_dropped = dropped

    if not previous_dropped:
        yield from undated


def _record_time(line: bytes) -> datetime | None:
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None
    raw = record.get("timestamp") if isinstance(record, dict) else None
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_pauses(home: Path) -> list[PauseInterval]:
    """저장된 일시정지 구간을 읽는다. 파일이 없으면 빈 목록."""
    path = home / PAUSES_FILENAME
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [PauseInterval.model_validate(item) for item in raw]


def save_pauses(home: Path, pauses: list[PauseInterval]) -> None:
    path = home / PAUSES_FILENAME
    payload = [pause.model_dump(mode="json") for pause in pauses]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def start_pause(home: Path, now: datetime) -> bool:
    """일시정지를 시작한다. 이미 정지 중이면 False."""
    pauses = load_pauses(home)
    if any(pause.end is None for pause in pauses):
        return False
    pauses.append(PauseInterval(start=now))
    save_pauses(home, pauses)
    return True


def end_pause(home: Path, now: datetime) -> bool:
    """열려 있는 일시정지를 닫는다. 정지 중이 아니면 False."""
    pauses = load_pauses(home)
    open_pauses = [pause for pause in pauses if pause.end is None]
    if not open_pauses:
        return False
    for pause in open_pauses:
        pause.end = now
    save_pauses(home, pauses)
    return True
