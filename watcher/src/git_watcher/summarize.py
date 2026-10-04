"""계정별 커밋 묶음을 Claude Code 헤드리스(`claude -p`)로 평가·요약한다.

API 키 대신 이 Mac에 로그인된 Claude 구독 한도를 쓴다.
"""

import json
import logging
import os
import subprocess
import tempfile
from collections import defaultdict
from datetime import datetime

from pydantic import BaseModel, ValidationError

from git_watcher.gitlab import Account

logger = logging.getLogger(__name__)

# 사람 한 명 요약에 허용하는 최대 시간
CLAUDE_TIMEOUT_SEC = 300
# 커밋 본문이 지나치게 길 때 LLM 입력에서 자르는 길이 (제목은 항상 전체 포함)
MAX_MESSAGE_CHARS = 1500
# 이 변수가 남아 있으면 claude가 구독 대신 API 계정으로 과금한다 (claude-code#37686)
BILLING_ENV_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")

UNRATED = "추정 불가"
# 하루 근무 시간. 수작업 환산 작업량을 이 값에 대한 비율로도 보여 준다
WORKDAY_HOURS = 8
# 추정 범위로 받아들이는 상한 (이보다 크면 모델 출력 오류로 본다)
MAX_ESTIMATE_HOURS = 24

SYSTEM_PROMPT = """당신은 개발을 모르는 관리자에게 팀원의 하루 작업을 보고하는 비서다.
한 사람의 GitLab 커밋 목록과 활동 지표가 주어진다.

반드시 아래 JSON 하나만 출력하라 (코드블록·설명 없이):
{"hours_low": 숫자, "hours_high": 숫자,
 "reason": "그 시간으로 추정한 근거 한 문장",
 "headline": "오늘 한 일을 비개발자도 이해하는 한 문장",
 "items": ["쉬운 말로 쓴 작업 항목", "..."]}

수작업 환산 작업량 (hours_low~hours_high):
- 숙련 개발자가 AI 도구 없이 손으로 이 커밋들의 결과물을 만들었다면 걸렸을
  순수 작업 시간을 0.5시간 단위 범위로 추정한다. 실제로 걸린 시간이 아니라 결과물의 크기다.
- 설계·디버깅·테스트·검증 시간은 포함하고, 회의·휴식은 제외한다.
- 줄 수가 아니라 결과물의 난이도와 범위로 판단한다. 자동 생성 파일·데이터·가중치·잠금 파일(lock)
  변경, 같은 내용의 반복 배포·버전 올림은 시간을 거의 주지 않는다.
- 범위 폭은 불확실성만큼 잡되 hours_high는 hours_low의 2배를 넘기지 않는다.

items 작성 규칙:
- 최대 5개. 같은 목적의 커밋은 하나로 묶는다.
- "무엇을 할 수 있게 됐는지/무엇이 고쳐졌는지" 결과 중심으로 쓴다. 파일명·함수명·영문 약어는 꼭 필요할 때만.
- 각 항목 앞에 [서비스 이름]을 붙인다 (프로젝트 경로의 마지막 부분).
- 커밋에 근거가 있는 것만 쓴다. 근무 태도·능력은 평가하지 않는다.
- 주어진 커밋은 모두 이 사람의 작업이다. 이 사람을 3인칭이나 '다른 팀원'으로 부르지 않는다.
- 모든 문장은 '~했다' 체로 끝낸다."""


class Assessment(BaseModel):
    hours_low: float | None
    hours_high: float | None
    reason: str
    headline: str
    items: list[str]

    @property
    def midpoint(self) -> float | None:
        if self.hours_low is None or self.hours_high is None:
            return None
        return (self.hours_low + self.hours_high) / 2

    @property
    def label(self) -> str:
        """예: '약 4~6시간 (50~75%)'."""
        if self.hours_low is None or self.hours_high is None:
            return UNRATED
        low, high = self.hours_low, self.hours_high
        pct = f"{low / WORKDAY_HOURS:.0%}~{high / WORKDAY_HOURS:.0%}"
        return f"약 {low:g}~{high:g}시간 ({pct})"


def activity_span(account: Account) -> str:
    """하루치면 첫~마지막 커밋 시각, 여러 날이면 커밋한 날 수 (작성자 로컬 시각 기준)."""
    times = sorted(datetime.fromisoformat(c.authored_at) for c in account.commits)
    days = {t.date() for t in times}
    if len(days) > 1:
        return f"{len(days)}일간"
    return f"{times[0]:%H:%M}~{times[-1]:%H:%M}"


def metrics_line(account: Account) -> str:
    adds = sum(c.additions for c in account.commits)
    dels = sum(c.deletions for c in account.commits)
    projects = len({c.project for c in account.commits})
    return (f"커밋 {len(account.commits)}건 · 프로젝트 {projects}개 · "
            f"+{adds}/-{dels}줄 · 활동 {activity_span(account)}")


def render_commits(account: Account) -> str:
    """LLM 입력용으로 지표와 커밋을 프로젝트별로 정리한다."""
    by_project: dict[str, list[str]] = defaultdict(list)
    for c in sorted(account.commits, key=lambda c: c.authored_at):
        body = c.message[len(c.title):].strip()[:MAX_MESSAGE_CHARS]
        lines = [f"* {c.authored_at[11:16]} {c.title} (+{c.additions}/-{c.deletions})"]
        if body:
            lines.append(f"  본문: {body}")
        if c.files:
            lines.append(f"  파일: {', '.join(c.files)}")
        by_project[c.project].extend(lines)
    commits = "\n\n".join(f"## {p}\n" + "\n".join(ls) for p, ls in by_project.items())
    return f"지표: {metrics_line(account)}\n\n{commits}"


def parse_assessment(text: str) -> Assessment:
    """모델 출력에서 JSON 객체를 꺼내 검증한다. 앞뒤 군더더기는 무시한다."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("JSON 객체가 없음")
    assessment = Assessment.model_validate(json.loads(text[start:end + 1]))
    low, high = assessment.hours_low, assessment.hours_high
    # 사소한 변경만 있는 날은 0~0.5시간처럼 하한 0이 정상이다
    if low is None or high is None or not (0 <= low <= high <= MAX_ESTIMATE_HOURS and high > 0):
        raise ValueError(f"추정 시간 범위가 이상함: {low}~{high}")
    return assessment


def subscription_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in BILLING_ENV_VARS}


class Summarizer:
    def __init__(self, claude_bin: str, model: str) -> None:
        self._base = [
            claude_bin, "-p",
            "--model", model,
            "--tools", "",  # 요약만 한다 — 파일·셸 도구 없음
            "--strict-mcp-config",  # MCP 서버도 띄우지 않는다
            "--no-session-persistence",
            "--output-format", "text",
        ]

    def ask(self, system_prompt: str, text: str) -> str:
        """claude -p 한 번 호출. 실패하면 CalledProcessError/TimeoutExpired를 그대로 올린다."""
        # 홈 아래에서 돌리면 상위 CLAUDE.md가 섞이므로 빈 임시 디렉터리에서 실행
        with tempfile.TemporaryDirectory() as workdir:
            result = subprocess.run(
                [*self._base, "--system-prompt", system_prompt], input=text, capture_output=True,
                text=True, cwd=workdir, env=subscription_env(), timeout=CLAUDE_TIMEOUT_SEC, check=True,
            )
        return result.stdout

    def assess(self, account: Account) -> Assessment:
        try:
            return parse_assessment(self.ask(SYSTEM_PROMPT, render_commits(account)))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            stderr = getattr(e, "stderr", "") or ""
            logger.error("claude 호출 실패 account=%s: %s %s", account.key, e, stderr[-500:])
        except (ValueError, ValidationError) as e:
            logger.error("claude 출력 해석 실패 account=%s: %s", account.key, e)
        return fallback_assessment(account)


def fallback_assessment(account: Account) -> Assessment:
    """LLM을 쓰지 않거나 실패했을 때: 커밋 제목을 그대로 나열한다."""
    items = [f"[{c.project.rsplit('/', 1)[-1]}] {c.title}"
             for c in sorted(account.commits, key=lambda c: c.authored_at)]
    return Assessment(hours_low=None, hours_high=None, reason="자동 평가 없음",
                      headline=f"커밋 {len(items)}건", items=items)
