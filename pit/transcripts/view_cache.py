"""가린 이벤트의 캐시 (views/)

원문은 세션 하나가 수백 MB라 매번 읽을 수 없다. 보관함 사본의 지문이 바뀐
세션만 다시 파싱해 views/ 에 떨어뜨리고, 이후 단계는 이 캐시만 읽는다.
캐시에 쓰는 시점에 이미 가림 처리가 끝나 있으므로 추출·트윈은 가리지 않은
글을 볼 방법이 없다.
"""

import logging
from collections import Counter
from fnmatch import fnmatch
from pathlib import Path

from pydantic import BaseModel, Field

from pit.personal.config import TwinConfig
from pit.transcripts.events import EVENT_BUILDERS
from pit.transcripts.reader import ReadStats
from pit.transcripts.records import Event
from pit.transcripts.redact import RedactionRules, redact
from pit.vault.manifest import ManifestEntry, load_manifest

logger = logging.getLogger(__name__)

# 이벤트 구조나 가림 규칙이 바뀌면 올린다 → 모든 캐시가 다시 만들어진다
VIEW_SCHEMA_VERSION = 1
VIEWS_DIR = Path("views")
VIEW_FILE_MODE = 0o600


class ViewMeta(BaseModel):
    schema_version: int
    vault_sha256: str
    session_id: str
    device: str
    cwd: str | None
    events: int
    # 고객 데이터가 섞이는 프로젝트라 뷰를 만들지 않았다
    restricted: bool = False
    # 이 도구의 파서가 아직 없다 (보관은 되어 있다)
    unsupported: bool = False
    redactions: dict[str, int] = Field(default_factory=dict)
    malformed_lines: int = 0
    duplicate_uuids: int = 0


def view_paths(home: Path, entry: ManifestEntry) -> tuple[Path, Path]:
    base = home / VIEWS_DIR / entry.device
    return base / f"{entry.session_id}.jsonl", base / f"{entry.session_id}.meta.json"


def is_restricted(cwd: str | None, config: TwinConfig) -> bool:
    return cwd is not None and any(fnmatch(cwd, glob) for glob in config.restricted_cwd_globs)


def refresh_view(home: Path, entry: ManifestEntry, config: TwinConfig) -> ViewMeta:
    """세션 하나의 캐시를 최신으로 만든다 (지문이 같으면 그대로 둔다)"""
    events_path, meta_path = view_paths(home, entry)
    if meta_path.exists():
        cached = ViewMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))
        current = cached.schema_version == VIEW_SCHEMA_VERSION
        if current and cached.vault_sha256 == entry.vault_sha256 and events_path.exists():
            return cached

    events_path.parent.mkdir(parents=True, exist_ok=True)
    restricted = is_restricted(entry.cwd, config)
    stats = ReadStats()
    builder = EVENT_BUILDERS.get(entry.tool)
    if builder is None:
        logger.warning("파서가 없는 도구라 뷰를 만들지 않음", extra={"tool": entry.tool})
    events = [] if restricted or builder is None else builder(home / entry.vault_relpath, stats)

    rules = RedactionRules(customer_terms=tuple(config.customer_terms))
    redactions: dict[str, int] = {}
    with events_path.open("w", encoding="utf-8") as f:
        for event in events:
            for rule, count in _redact_event(event, rules).items():
                redactions[rule] = redactions.get(rule, 0) + count
            f.write(event.model_dump_json(exclude_defaults=True) + "\n")
    events_path.chmod(VIEW_FILE_MODE)

    meta = ViewMeta(
        schema_version=VIEW_SCHEMA_VERSION,
        vault_sha256=entry.vault_sha256,
        session_id=entry.session_id,
        device=entry.device,
        cwd=entry.cwd,
        events=len(events),
        restricted=restricted,
        unsupported=builder is None,
        redactions=redactions,
        malformed_lines=stats.malformed,
        duplicate_uuids=stats.duplicate_uuid,
    )
    meta_path.write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    meta_path.chmod(VIEW_FILE_MODE)
    return meta


def _redact_event(event: Event, rules: RedactionRules) -> Counter[str]:
    """이벤트의 모든 글 필드를 가린다. 질문과 답은 같은 함수로 가려 짝이 유지된다."""
    counts: Counter[str] = Counter()

    def apply(value: str) -> str:
        result = redact(value, rules)
        counts.update(result.counts)
        return result.text

    event.text = apply(event.text)
    for question in event.questions:
        question.question = apply(question.question)
        for option in question.options:
            option.label = apply(option.label)
            option.description = apply(option.description)
    event.answers = {apply(q): apply(a) for q, a in event.answers.items()}
    return counts


def refresh_all_views(home: Path, config: TwinConfig) -> list[ViewMeta]:
    """메인 세션 전부의 캐시를 최신으로 만든다 (서브에이전트 파일은 보관만 한다)"""
    metas = []
    for entry in load_manifest(home).values():
        if entry.agent_name is not None:
            continue
        try:
            metas.append(refresh_view(home, entry, config))
        except OSError as e:
            logger.warning(
                "뷰를 만들지 못해 건너뜀",
                extra={"session_id": entry.session_id, "error": type(e).__name__},
            )
    return metas


def load_view_events(home: Path, entry: ManifestEntry) -> list[Event]:
    events_path, _ = view_paths(home, entry)
    if not events_path.exists():
        return []
    with events_path.open(encoding="utf-8") as f:
        return [Event.model_validate_json(line) for line in f if line.strip()]
