"""Claude Code 세션 파일 탐색

레이아웃:
    <root>/<encoded-cwd>/<sessionId>.jsonl                          메인 세션
    <root>/<encoded-cwd>/<sessionId>/subagents/agent-<id>.jsonl     서브에이전트

폴더 이름은 경로를 비가역으로 뭉갠 것이라 해석하지 않는다. 작업 디렉터리는
레코드의 cwd 필드에서만 읽는다.
"""

import json
import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

CLAUDE_PROJECTS_ENV = "PIT_CLAUDE_PROJECTS_DIR"
CLAUDE_HOME_ENV = "PIT_CLAUDE_HOME"
SOURCE_TOOL = "claude-code"
SUBAGENTS_DIRNAME = "subagents"
SESSION_SUFFIX = ".jsonl"

# cwd는 대화 레코드에만 있고 파일 앞쪽은 UI 상태 레코드가 차지한다.
# 그래도 수백 줄 안에는 나오므로 큰 파일 전체를 읽지 않도록 상한을 둔다.
META_SCAN_MAX_LINES = 2000


@dataclass(frozen=True)
class SessionFile:
    """보관 대상 세션 파일 하나"""

    path: Path
    session_id: str
    # 서브에이전트 파일이면 파일 이름(확장자 제외), 메인 세션이면 None
    agent_name: str | None = None

    @property
    def key(self) -> str:
        """manifest에서 이 파일을 가리키는 키 (기기 안에서 유일)"""
        if self.agent_name is None:
            return self.session_id
        return f"{self.session_id}/{self.agent_name}"


@dataclass(frozen=True)
class SessionMeta:
    """세션 파일 앞부분에서 읽은 출처 정보"""

    cwd: str | None
    version: str | None


def resolve_claude_home() -> Path:
    """Claude Code 설정 폴더 (기본 ~/.claude)"""
    from_env = os.environ.get(CLAUDE_HOME_ENV)
    return Path(from_env).expanduser() if from_env else Path.home() / ".claude"


def resolve_source_root() -> Path:
    """세션 기록 루트 (기본 ~/.claude/projects)"""
    from_env = os.environ.get(CLAUDE_PROJECTS_ENV)
    return Path(from_env).expanduser() if from_env else resolve_claude_home() / "projects"


def discover_sessions(source_root: Path) -> Iterator[SessionFile]:
    """루트 아래의 메인 세션과 서브에이전트 파일을 모두 찾는다 (경로 순)"""
    if not source_root.is_dir():
        return

    for project_dir in sorted(p for p in source_root.iterdir() if p.is_dir()):
        for main in sorted(project_dir.glob(f"*{SESSION_SUFFIX}")):
            yield SessionFile(path=main, session_id=main.stem)

        for sub in sorted(project_dir.glob(f"*/{SUBAGENTS_DIRNAME}/*{SESSION_SUFFIX}")):
            yield SessionFile(
                path=sub, session_id=sub.parent.parent.name, agent_name=sub.stem
            )


def peek_session_meta(path: Path) -> SessionMeta:
    """파일 앞부분에서 cwd와 도구 버전을 읽는다. 못 찾으면 None으로 채운다."""
    with path.open("rb") as f:
        for _, line in zip(range(META_SCAN_MAX_LINES), f):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and record.get("cwd"):
                return SessionMeta(cwd=record["cwd"], version=record.get("version"))

    logger.debug("cwd를 찾지 못함", extra={"path": str(path)})
    return SessionMeta(cwd=None, version=None)


class UnknownSourceError(Exception):
    """등록되지 않은 도구 이름"""


class SourceAdapter(Protocol):
    """LLM 도구 하나의 세션 기록을 찾는 방법

    새 도구(Codex, claude.ai 내보내기 등)를 지원하려면 이 규약을 구현해 SOURCES에
    등록하고, 같은 이름으로 pit.transcripts.events.EVENT_BUILDERS 에 파서를 등록한다.
    보관·정책·캐시·추출·검토는 도구와 무관하게 그대로 동작한다.
    """

    tool: str

    def default_root(self) -> Path: ...

    def discover(self, root: Path) -> Iterator[SessionFile]: ...

    def peek_meta(self, path: Path) -> SessionMeta: ...


class ClaudeCodeSource:
    tool = SOURCE_TOOL

    def default_root(self) -> Path:
        return resolve_source_root()

    def discover(self, root: Path) -> Iterator[SessionFile]:
        return discover_sessions(root)

    def peek_meta(self, path: Path) -> SessionMeta:
        return peek_session_meta(path)


SOURCES: dict[str, SourceAdapter] = {SOURCE_TOOL: ClaudeCodeSource()}


def get_source(tool: str = SOURCE_TOOL) -> SourceAdapter:
    """도구 이름으로 어댑터를 찾는다

    Raises:
        UnknownSourceError: 등록되지 않은 도구일 때
    """
    try:
        return SOURCES[tool]
    except KeyError:
        raise UnknownSourceError(f"지원하지 않는 도구입니다: {tool} (지원: {', '.join(sorted(SOURCES))})") from None
