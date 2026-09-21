"""합성 세션 레코드 빌더

테스트는 실제 세션 기록을 쓰지 않는다. 실세션에는 시크릿과 고객 데이터가 섞여 있다.
여기서 만드는 레코드는 실측한 Claude Code JSONL 구조를 흉내 낸 가짜다.
"""

import json
import os
from pathlib import Path

DEFAULT_CWD = "/work/demo"
DEFAULT_SESSION_ID = "11111111-1111-4111-8111-111111111111"


def timestamp(minute: int, hour: int = 10, day: int = 1) -> str:
    return f"2026-09-{day:02d}T{hour:02d}:{minute:02d}:00.000Z"


def human_record(text: str, minute: int = 0, cwd: str = DEFAULT_CWD, **extra: object) -> dict:
    """사람이 직접 친 메시지"""
    return {
        "type": "user",
        "uuid": f"u-{minute}",
        "timestamp": timestamp(minute),
        "cwd": cwd,
        "sessionId": DEFAULT_SESSION_ID,
        "isSidechain": False,
        "version": "2.1.270",
        "message": {"role": "user", "content": text},
        **extra,
    }


def assistant_record(text: str, minute: int = 0, message_id: str = "msg-1") -> dict:
    return {
        "type": "assistant",
        "uuid": f"a-{minute}-{message_id}",
        "timestamp": timestamp(minute),
        "cwd": DEFAULT_CWD,
        "sessionId": DEFAULT_SESSION_ID,
        "isSidechain": False,
        "message": {"id": message_id, "role": "assistant", "content": [{"type": "text", "text": text}]},
    }


def undated_record(record_type: str = "last-prompt", **fields: object) -> dict:
    """timestamp가 없는 UI 상태 레코드"""
    return {"type": record_type, "sessionId": DEFAULT_SESSION_ID, **fields}


def to_line(record: dict) -> bytes:
    return json.dumps(record, ensure_ascii=False).encode("utf-8") + b"\n"


def write_session(
    root: Path,
    records: list[dict],
    session_id: str = DEFAULT_SESSION_ID,
    project: str = "-work-demo",
    agent_name: str | None = None,
) -> Path:
    """소스 루트 아래에 세션 파일을 만든다 (agent_name을 주면 서브에이전트 파일)"""
    if agent_name is None:
        path = root / project / f"{session_id}.jsonl"
    else:
        path = root / project / session_id / "subagents" / f"{agent_name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(to_line(record) for record in records))
    return path


def append_records(path: Path, records: list[dict], raw_tail: bytes = b"") -> None:
    """세션 파일 끝에 레코드를 덧붙인다

    파일시스템의 mtime 해상도에 기대지 않도록 mtime을 명시적으로 1초 앞당긴다
    (테스트에서 sleep을 쓰지 않기 위함).
    """
    before = path.stat().st_mtime_ns
    with path.open("ab") as f:
        f.write(b"".join(to_line(record) for record in records) + raw_tail)
    bumped = before + 1_000_000_000
    os.utime(path, ns=(bumped, bumped))
