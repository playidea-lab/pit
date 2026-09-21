"""보관함 → 결정 후보

세션마다 (1) 구조에서 바로 읽히는 결정을 만들고 (2) 나머지 사람 발화를 LLM에게
보여 라벨을 받는다. 이미 후보이거나 확정됐거나 버려진 결정은 다시 만들지 않는다.
"""

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from pit.decisions.ids import make_decision_id
from pit.decisions.models import (
    Decision,
    DecisionKind,
    DecisionSource,
    ExtractionMethod,
    ExtractorInfo,
)
from pit.decisions.store import CANDIDATES_DIR, known_ids, save_candidate
from pit.extract.anchors import RawPairLabel, resolve_anchor
from pit.extract.llm_extract import (
    compact_for_extraction,
    extract_with_llm,
    load_extract_prompt,
    split_windows,
)
from pit.extract.structured import SourceContext, extract_structured
from pit.llm.client import LLMClient, LLMError
from pit.personal.config import TwinConfig
from pit.transcripts.events import split_segments
from pit.transcripts.records import Event, EventKind
from pit.transcripts.view import render_view
from pit.transcripts.view_cache import load_view_events, refresh_all_views
from pit.vault.manifest import ManifestEntry, load_manifest

logger = logging.getLogger(__name__)

IDLE_GAP_HOURS = 4
STATE_FILENAME = "_llm_state.json"


@dataclass(frozen=True)
class ExtractionLimits:
    max_calls: int | None = None
    dry_run: bool = False


@dataclass
class ExtractionReport:
    sessions: int = 0
    structured: int = 0
    llm: int = 0
    calls: int = 0
    planned_calls: int = 0
    planned_chars: int = 0
    already_known: int = 0
    errors: Counter[str] = field(default_factory=Counter)


def _load_state(home: Path) -> dict[str, int]:
    path = home / CANDIDATES_DIR / STATE_FILENAME
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save_state(home: Path, state: dict[str, int]) -> None:
    path = home / CANDIDATES_DIR / STATE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _to_decision(
    raw: RawPairLabel, proposal: Event, verdict: Event, ctx: SourceContext, extractor: ExtractorInfo
) -> Decision:
    decided_at = verdict.timestamp or ctx.now
    return Decision(
        id=make_decision_id(ctx.session_id, verdict.uuid, decided_at),
        person=ctx.person,
        project=ctx.cwd,
        kind=DecisionKind.VERDICT,
        decided_at=decided_at,
        created_at=ctx.now,
        source=DecisionSource(
            tool=ctx.tool,
            device=ctx.device,
            session_id=ctx.session_id,
            cwd=ctx.cwd,
            verdict_uuid=verdict.uuid,
            verdict_line_no=verdict.line_no,
            proposal_uuid=proposal.uuid,
            proposal_line_no=proposal.line_no,
        ),
        situation=raw.situation,
        proposal=raw.proposal,
        verdict=raw.verdict,
        reject_kind=raw.reject_kind,
        rationale=raw.rationale,
        human_quote=raw.human_quote,
        extractor=extractor,
    )


def _windows_after(events: list[Event], last_line_no: int) -> list[list[Event]]:
    """아직 LLM에게 보이지 않은 사람 발화가 든 윈도만 돌려준다"""
    windows: list[list[Event]] = []
    for segment in split_segments(events, timedelta(hours=IDLE_GAP_HOURS)):
        for window in split_windows(compact_for_extraction(segment)):
            fresh = any(e.kind is EventKind.HUMAN and e.line_no > last_line_no for e in window)
            if fresh:
                windows.append(window)
    return windows


class _Run:
    """한 번의 추출 실행이 공유하는 상태"""

    def __init__(self, home: Path, client: LLMClient | None, limits: ExtractionLimits) -> None:
        self.home = home
        self.client = client
        self.limits = limits
        self.report = ExtractionReport()
        self.known = known_ids(home)
        self.state = _load_state(home)

    def add(self, decision: Decision, method: ExtractionMethod) -> None:
        if decision.id in self.known:
            self.report.already_known += 1
            return
        self.known.add(decision.id)
        if not self.limits.dry_run:
            save_candidate(self.home, decision)
        if method is ExtractionMethod.STRUCTURED:
            self.report.structured += 1
        else:
            self.report.llm += 1

    def out_of_calls(self) -> bool:
        return self.limits.max_calls is not None and self.report.calls >= self.limits.max_calls


def run_extraction(
    home: Path,
    config: TwinConfig,
    client: LLMClient | None,
    model_id: str | None,
    limits: ExtractionLimits,
    now: datetime,
) -> ExtractionReport:
    """보관함의 모든 메인 세션에서 후보를 만든다

    client가 None이면 구조 신호만 추출한다.
    """
    refresh_all_views(home, config)
    run = _Run(home, client, limits)
    system_prompt, prompt_hash = load_extract_prompt(home)
    extractor = ExtractorInfo(method=ExtractionMethod.LLM, model=model_id, prompt_hash=prompt_hash)

    for key, entry in sorted(load_manifest(home).items()):
        if entry.agent_name is not None:
            continue
        events = load_view_events(home, entry)
        if not events:
            continue
        run.report.sessions += 1
        ctx = _context(entry, config, now)

        for decision in extract_structured(events, ctx):
            run.add(decision, ExtractionMethod.STRUCTURED)
        _extract_session_with_llm(run, key, events, ctx, system_prompt, model_id, extractor)

    if not limits.dry_run:
        _save_state(home, run.state)
    return run.report


def _context(entry: ManifestEntry, config: TwinConfig, now: datetime) -> SourceContext:
    return SourceContext(
        person=config.person_id,
        tool=entry.tool,
        device=entry.device,
        session_id=entry.session_id,
        cwd=entry.cwd,
        now=now,
    )


def _extract_session_with_llm(
    run: _Run,
    key: str,
    events: list[Event],
    ctx: SourceContext,
    system_prompt: str,
    model_id: str | None,
    extractor: ExtractorInfo,
) -> None:
    for window in _windows_after(events, run.state.get(key, 0)):
        view = render_view(window)
        run.report.planned_calls += 1
        run.report.planned_chars += len(view.text)
        if run.limits.dry_run or run.client is None or model_id is None or run.out_of_calls():
            continue

        run.report.calls += 1
        try:
            labels = extract_with_llm(view, run.client, system_prompt, model_id)
        except (LLMError, ValidationError) as e:
            logger.warning("윈도 추출 실패", extra={"session_id": ctx.session_id, "error": type(e).__name__})
            run.report.errors[type(e).__name__] += 1
            # 실패한 윈도부터는 다음 실행에서 다시 시도한다
            return

        for raw in labels:
            anchor = resolve_anchor(view, raw)
            if not anchor.ok or anchor.proposal is None or anchor.verdict is None:
                run.report.errors[anchor.error or "anchor"] += 1
                continue
            run.add(_to_decision(raw, anchor.proposal, anchor.verdict, ctx, extractor), ExtractionMethod.LLM)
        run.state[key] = max(e.line_no for e in window)
