"""Claude Code 대화 기록(JSONL)에서 텔레메트리와 같은 요약 이벤트를 뽑는다 (원문은 뽑지 않는다).

텔레메트리를 켜기 전의 대화나, 켜기 전에 시작해 아직 열려 있는 대화를 소급 기록하는 데 쓴다.
"""

import json
import subprocess
from pathlib import Path

# 사람이 직접 입력한 메시지의 promptSource. system(백그라운드 알림)·isMeta는 사람 입력이 아니다
HUMAN_SOURCES = ("typed", "queued", "suggestion_accepted")
# promptSource가 비어 있어도 사람이 시작한 입력 (! 명령, 슬래시 명령)
HUMAN_PREFIXES = ("<bash-input>", "<command-message>")
SERVICE = "claude-code"
SOURCE = "transcript-backfill"


def message_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(x.get("text", "") for x in content if isinstance(x, dict) and x.get("type") == "text")
    return ""


def is_human_prompt(entry: dict) -> bool:
    if entry.get("type") != "user" or entry.get("isMeta"):
        return False
    text = message_text(entry.get("message", {}).get("content")).lstrip()
    if not text:
        return False
    return entry.get("promptSource") in HUMAN_SOURCES or text.startswith(HUMAN_PREFIXES)


def repo_name(cwd: str, cache: dict[str, str | None]) -> str | None:
    """작업 폴더 → 'group/name'. 원격이 있으면 원격 경로, 없으면 로컬 저장소 폴더 이름."""
    if cwd in cache:
        return cache[cwd]
    name = None
    top = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top.returncode == 0:
        url = subprocess.run(["git", "-C", cwd, "remote", "get-url", "origin"], capture_output=True, text=True)
        path = url.stdout.strip().removesuffix(".git")
        name = "/".join(path.replace(":", "/").split("/")[-2:]) if url.returncode == 0 and path else \
            f"local/{Path(top.stdout.strip()).name}"
    cache[cwd] = name
    return name


def _base(entry: dict, who: str, repos: dict[str, str | None]) -> dict[str, object]:
    event: dict[str, object] = {"service.name": SERVICE, "source": SOURCE, "user.email": who,
                                "session.id": entry.get("sessionId"), "ts": entry.get("timestamp")}
    repo = repo_name(entry["cwd"], repos) if entry.get("cwd") else None
    if repo:
        event["repo.name"] = repo
    return event


def transcript_events(lines: list[str], who: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    repos: dict[str, str | None] = {}
    seen_requests: set[str] = set()
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not entry.get("timestamp"):
            continue
        if is_human_prompt(entry):
            text = message_text(entry["message"]["content"])
            events.append({**_base(entry, who, repos), "event.name": "user_prompt", "prompt_length": len(text)})
        elif entry.get("type") == "assistant":
            events.extend(_assistant_events(entry, who, repos, seen_requests))
    return events


def _assistant_events(entry: dict, who: str, repos: dict[str, str | None], seen: set[str]) -> list[dict[str, object]]:
    msg = entry.get("message", {})
    out = [{**_base(entry, who, repos), "event.name": "tool_result", "tool_name": x.get("name")}
           for x in msg.get("content", []) if isinstance(x, dict) and x.get("type") == "tool_use"]
    usage, request = msg.get("usage"), entry.get("requestId")
    # 한 API 요청이 블록마다 여러 줄로 기록된다 — 요청당 한 번만 센다
    if usage and request and request not in seen:
        seen.add(request)
        out.append({**_base(entry, who, repos), "event.name": "api_request", "model": msg.get("model"),
                    "input_tokens": usage.get("input_tokens", 0), "output_tokens": usage.get("output_tokens", 0),
                    "cache_read_tokens": usage.get("cache_read_input_tokens", 0)})
    return out


def backfill(transcript: Path, who: str, out_dir: Path) -> Path:
    """대화 하나를 요약 이벤트 파일로 쓴다. 같은 대화를 다시 돌리면 덮어쓴다(중복 없음)."""
    events = transcript_events(transcript.read_text().splitlines(), who)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{transcript.stem}.jsonl"
    out.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events))
    return out
