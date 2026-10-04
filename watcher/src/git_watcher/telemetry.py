"""에이전트 텔레메트리 수집기 — OTLP/HTTP(JSON) 로그를 받아 요약 필드만 남긴다.

Claude Code·Codex가 보내는 이벤트에서 시각·길이·도구·토큰·비용 같은 요약만 저장한다.
프롬프트·응답·도구 출력처럼 글이 담길 수 있는 값은 허용 목록에 없으므로 저장하지 않는다
(대표 결정 2026-10-04: 원문은 받지 않고 요약만).
"""

import json
import logging
import re
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

logger = logging.getLogger(__name__)

NANOS_PER_SECOND = 1_000_000_000
MAX_BODY_BYTES = 10 * 1024 * 1024
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_TOO_LARGE = 413

# 저장해도 되는 속성 이름 (값까지 저장). 글이 담길 수 있는 키는 넣지 않는다
ALLOWED_KEY = re.compile(
    r"(^|\.)(event\.name|event\.timestamp|event\.sequence|session\.id|conversation\.id|user\.email|user\.id|"
    r"user\.account_uuid|user\.account_id|auth_mode|originator|repo\.name|organization\.id|terminal\.type|model|tool_name|tool\.name|decision|source|success|"
    r"duration_ms|duration|status|status_code|error_type|cost_usd|input_tokens|output_tokens|"
    r"cache_read_tokens|cache_creation_tokens|reasoning_token_count|token_count|output_token_count|"
    r"prompt_length|initial_user_message_chars|"
    r"service\.name|service\.version|app\.version|attempt|speed|effort)$"
)
# 글 자체가 담기는 속성 이름 — 허용 목록과 상관없이 버린다 (방어선 두 겹). 길이·개수 필드는 해당 없음
FORBIDDEN_KEY = re.compile(r"(^|\.)(prompt|prompt_text|output|arguments|content|body|message|text|input|query)$", re.I)


def _value(v: dict) -> str | int | float | bool | None:
    """OTLP AnyValue → 파이썬 값. 배열·맵은 저장하지 않는다."""
    for kind in ("stringValue", "boolValue", "doubleValue"):
        if kind in v:
            return v[kind]
    if "intValue" in v:
        return int(v["intValue"])
    return None


def _attrs(items: list[dict]) -> dict[str, object]:
    return {a["key"]: _value(a.get("value", {})) for a in items or []}


def summarize_record(resource: dict[str, object], record: dict) -> tuple[dict[str, object], list[str]]:
    """로그 한 건 → (저장할 요약, 받은 속성 이름 목록)."""
    attrs = {**resource, **_attrs(record.get("attributes", []))}
    kept = {k: v for k, v in attrs.items()
            if v is not None and ALLOWED_KEY.search(k) and not FORBIDDEN_KEY.search(k)}
    nanos = int(record.get("timeUnixNano") or record.get("observedTimeUnixNano") or 0)
    if nanos:
        kept["ts"] = datetime.fromtimestamp(nanos / NANOS_PER_SECOND, UTC).isoformat()
    elif attrs.get("event.timestamp"):
        # Codex는 OTLP 시각 필드를 비워 보내고 시각을 속성으로만 싣는다
        kept["ts"] = datetime.fromisoformat(str(attrs["event.timestamp"]).replace("Z", "+00:00")).isoformat()
    return kept, sorted(attrs)


def summarize_logs(payload: dict) -> tuple[list[dict[str, object]], set[str]]:
    events: list[dict[str, object]] = []
    seen_keys: set[str] = set()
    for rl in payload.get("resourceLogs", []):
        resource = _attrs(rl.get("resource", {}).get("attributes", []))
        for sl in rl.get("scopeLogs", []):
            for record in sl.get("logRecords", []):
                event, keys = summarize_record(resource, record)
                events.append(event)
                seen_keys.update(keys)
    return events, seen_keys


class TelemetryStore:
    """날짜별 JSONL로 요약 이벤트를, 별도 파일로 지금까지 본 속성 '이름'을 쌓는다."""

    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self._keys_file = root / "seen_keys.json"

    def append(self, events: list[dict[str, object]], keys: set[str]) -> None:
        day = datetime.now(UTC).date().isoformat()
        with (self.root / f"{day}.jsonl").open("a") as f:
            for e in events:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        known = set(json.loads(self._keys_file.read_text())) if self._keys_file.exists() else set()
        if not keys <= known:
            self._keys_file.write_text(json.dumps(sorted(known | keys), ensure_ascii=False, indent=2))


def make_handler(store: TelemetryStore) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 — http.server 규약
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY_BYTES:
                return self._reply(HTTP_TOO_LARGE)
            if self.path.rstrip("/") == "/v1/metrics":
                self.rfile.read(length)  # 메트릭은 지금 쓰지 않는다 — 읽고 버림
                return self._reply(HTTP_OK)
            if self.path.rstrip("/") != "/v1/logs":
                return self._reply(HTTP_NOT_FOUND)
            try:
                payload = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                logger.warning("JSON이 아닌 OTLP 요청 (protocol=json 설정 확인)")
                return self._reply(HTTP_BAD_REQUEST)
            events, keys = summarize_logs(payload)
            store.append(events, keys)
            self._reply(HTTP_OK)

        def _reply(self, code: int) -> None:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, fmt: str, *args: object) -> None:
            logger.debug(fmt, *args)

    return Handler


def serve(host: str, port: int, root: Path) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(TelemetryStore(root)))
    logger.info("텔레메트리 수집기 시작: http://%s:%d → %s", host, port, root)
    server.serve_forever()
