"""pithub 작업 보고(report_start/report_commit)를 독립 근거로 검증한다.

보고는 에이전트의 주장이다. 여기서 대조하는 것:
- 누락: 커밋은 있는데 보고가 없다
- 주장 대 판정: 원자성·메시지 적절성을 diff 정보(메시지·파일·줄 수)로 따로 판정해 어긋나면 표시
- 예상 대 실제: report_start 의 사전 예상(수작업 환산)과 판정한 규모가 두 배 넘게 다르면 표시
- 전체 그림: 보고가 실행했다는 결정·목표 아래로 묶는다
"""

import json
import logging
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

import httpx
from pydantic import BaseModel, ValidationError

from git_watcher.gitlab import Account, Commit
from git_watcher.summarize import Summarizer

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SEC = 30.0
# 사전 예상과 판정 규모가 이 배수보다 벌어지면 어긋남으로 본다
SIZE_MISMATCH_RATIO = 2.0
NO_DECISION = "(연결된 결정 없음)"
MAX_TITLE_CHARS = 80

JUDGE_PROMPT = """당신은 커밋 심사관이다. 커밋 하나의 메시지, 바뀐 파일 목록, 증감 줄 수가 주어진다.
반드시 아래 JSON 하나만 출력하라:
{"atomic": true|false, "message_ok": true|false,
 "manual_low": 숫자, "manual_high": 숫자, "reason": "판정 근거 한 문장"}
- atomic: 논리적 변경 하나인가 (서로 무관한 변경이 섞이면 false)
- message_ok: 메시지가 무엇을·왜 바꿨는지 말하는가
- manual_low~manual_high: AI 없이 숙련 개발자가 손으로 만들었다면 걸렸을 시간 범위(0.5시간 단위)"""


class Judgment(BaseModel):
    atomic: bool
    message_ok: bool
    manual_low: float
    manual_high: float
    reason: str = ""


@dataclass
class CheckedCommit:
    commit: Commit
    report: dict | None = None
    start: dict | None = None
    judgment: Judgment | None = None
    flags: list[str] = field(default_factory=list)


@dataclass
class PersonWork:
    who: str
    checked: list[CheckedCommit] = field(default_factory=list)

    @property
    def missing(self) -> int:
        return sum(1 for c in self.checked if c.report is None)


class PithubClient:
    """pithub(Supabase PostgREST) 읽기 전용 클라이언트. 서버 키로 팀 보고를 읽는다."""

    def __init__(self, url: str, key: str) -> None:
        self._http = httpx.Client(base_url=url.rstrip("/") + "/rest/v1", timeout=REQUEST_TIMEOUT_SEC,
                                  headers={"apikey": key, "Authorization": f"Bearer {key}"})

    def __enter__(self) -> "PithubClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self._http.close()

    def _get(self, path: str, params: dict[str, str]) -> list[dict]:
        resp = self._http.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    def reports(self, since: datetime, until: datetime) -> list[dict]:
        return self._get("/work_reports", {"select": "*", "and": f"(reported_at.gte.{since.isoformat()},"
                                           f"reported_at.lt.{until.isoformat()})", "order": "reported_at"})

    def logins(self, github_ids: list[int]) -> dict[int, str]:
        if not github_ids:
            return {}
        rows = self._get("/accounts", {"select": "github_id,github_login",
                                       "github_id": f"in.({','.join(map(str, github_ids))})"})
        return {r["github_id"]: r["github_login"] for r in rows}

    def decision_titles(self, ids: list[str]) -> dict[str, str]:
        if not ids:
            return {}
        rows = self._get("/decisions", {"select": "id,proposal", "id": f"in.({','.join(ids)})"})
        return {r["id"]: (r.get("proposal") or r["id"])[:MAX_TITLE_CHARS] for r in rows}


def judge(summarizer: Summarizer, c: Commit) -> Judgment | None:
    text = f"메시지:\n{c.message}\n\n파일: {', '.join(c.files)}\n증감: +{c.additions}/-{c.deletions}"
    try:
        out = summarizer.ask(JUDGE_PROMPT, text)
        return Judgment.model_validate(json.loads(out[out.find("{"): out.rfind("}") + 1]))
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, ValidationError) as e:
        logger.error("커밋 판정 실패 sha=%s: %s", c.sha, e)
        return None


def matches(report_sha: str, commit_sha: str) -> bool:
    """보고는 전체 해시, 수집한 커밋은 짧은 해시일 수 있다."""
    a, b = report_sha.lower(), commit_sha.lower()
    return a.startswith(b) or b.startswith(a)


def compare(checked: CheckedCommit) -> list[str]:
    """보고의 주장과 독립 판정이 어긋나는 곳."""
    report, j, flags = checked.report, checked.judgment, []
    if report is None or j is None:
        return flags
    if report.get("atomic") and not j.atomic:
        flags.append(f"원자적이라 보고했지만 판정은 섞인 변경 ({j.reason})")
    if report.get("message_ok") and not j.message_ok:
        flags.append("메시지가 충분하다 보고했지만 판정은 부족")
    expected = (checked.start or {}).get("expected_manual_hours") or report.get("expected_manual_hours")
    mid = (j.manual_low + j.manual_high) / 2
    if expected and mid and max(expected, mid) / max(min(expected, mid), 0.1) > SIZE_MISMATCH_RATIO:
        flags.append(f"예상 {expected:g}시간 대 판정 {j.manual_low:g}~{j.manual_high:g}시간")
    return flags


def verify(accounts: dict[str, Account], reports: list[dict], who_of: dict[int, str],
           summarizer: Summarizer | None) -> list[PersonWork]:
    """사람(계정 키)별로 커밋마다 보고를 찾고, 보고된 커밋은 판정해 어긋남을 표시한다."""
    starts = {r["id"]: r for r in reports if r["kind"] == "start"}
    commit_reports = [r for r in reports if r["kind"] == "commit"]
    people: list[PersonWork] = []
    for key, account in accounts.items():
        mine = [r for r in commit_reports if who_of.get(r["owner_github_id"]) == key]
        work = PersonWork(key)
        for c in account.commits:
            report = next((r for r in mine if r.get("commit_sha") and matches(r["commit_sha"], c.sha)), None)
            checked = CheckedCommit(c, report, starts.get((report or {}).get("start_id") or ""))
            if report is not None and summarizer is not None:
                checked.judgment = judge(summarizer, c)
            checked.flags = compare(checked)
            work.checked.append(checked)
        people.append(work)
    return people


def by_decision(people: list[PersonWork], titles: dict[str, str]) -> dict[str, list[CheckedCommit]]:
    """결정·목표 → 그것을 실행했다고 보고된 커밋들 (전체 업무 속의 자리)."""
    groups: dict[str, list[CheckedCommit]] = defaultdict(list)
    for person in people:
        for c in person.checked:
            if c.report is None:
                continue
            ids = c.report.get("implements") or (c.start or {}).get("implements") or []
            for decision_id in ids or [None]:
                groups[titles.get(decision_id, decision_id) if decision_id else NO_DECISION].append(c)
    return dict(groups)


def render_text(people: list[PersonWork], groups: dict[str, list[CheckedCommit]], names: dict[str, str]) -> str:
    """대표용 평문: 전체 그림(결정별) → 사람별 보고율·어긋남."""
    lines = ["[전체 업무 속 작업]"]
    for title, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"■ {title} — 커밋 {len(items)}건")
        lines += [f"  - {c.commit.title} ({c.commit.sha})" for c in items]
    lines += ["", "[사람별 보고 검증]"]
    for p in people:
        total = len(p.checked)
        if not total:
            continue
        lines.append(f"■ {names.get(p.who, p.who)} — 커밋 {total}건 중 보고 {total - p.missing}건 (누락 {p.missing})")
        lines += [f"  ! {c.commit.sha} {flag}" for c in p.checked for flag in c.flags]
    return "\n".join(lines)
