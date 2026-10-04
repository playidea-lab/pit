"""AI 시대 작업 방식 평가 v1 — 회사 규칙 하나 + git에 남은 증거 하나로 채점한다.

모든 항목은 PI Lab 규칙 파일(~/.claude/rules)의 문장에서 왔고, 점수마다 근거 커밋이 붙는다.
git만으로 검증할 수 없는 것(프롬프트·세션에서의 지시, 리뷰의 질)은 아직 재지 않는다.
"""

import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from git_watcher.gitlab import Commit

# 총점을 내기 위한 최소 커밋 수 (이보다 적으면 표본 부족)
MIN_COMMITS_FOR_SCORE = 10
# 작은 단위 변경으로 보는 커밋당 변경 줄 수 상한
SMALL_COMMIT_LINES = 400
# 커밋 제목 길이 상한 (git-workflow.md)
MAX_SUBJECT_CHARS = 50
# 본문에 '왜'를 적었다고 보는 최소 글자 수 (제목 제외)
MIN_BODY_CHARS = 20
# 항목별로 보고서에 싣는 위반 근거 최대 개수
MAX_EVIDENCE = 5
PERCENT = 100

CONVENTIONAL = re.compile(r"^(feat|fix|docs|refactor|test|chore|perf|ci|build|style|revert)(\([^)]*\))?!?: ")
AGENT_TRAILER = re.compile(
    r"co-authored-by:.*(claude|anthropic|codex|copilot|cursor|openai)|generated with \[?claude", re.I
)
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]+$|_test\.\w+$|\.(test|spec)\.\w+$")
CODE_EXT = re.compile(r"\.(py|ts|tsx|js|jsx|go|dart|kt|swift|java|rs|vue|c|cc|cpp|h)$")
# 내용을 열어 볼 후보 파일. 이름만으로는 판정하지 않는다 (공개 설정만 든 .env가 흔하다)
SECRET_PATH = re.compile(r"(^|/)(\.env(\.[^/]*)?|credentials\.json|id_rsa)$|\.(pem|key)$")
SECRET_ALLOWED = re.compile(r"\.(example|sample|template)$")
# 값이 들어가면 비밀로 보는 변수 이름 (VITE_API_BASE_URL 같은 공개 설정은 해당 없음)
SECRET_KEY_NAME = re.compile(r"(PASS(WORD)?|SECRET|TOKEN|API_?KEY|PRIVATE|CREDENTIAL)", re.I)
ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z0-9_]+)\s*[=:]\s*(.*)$")
PRIVATE_KEY_BLOCK = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
# 심각도 판정 (대표 결정 2026-10-03: 한 건이면 0점 대신 심각도별 감점)
CRITICAL_PATH = re.compile(r"(^|[/.])(prod|production|live)([/.]|$)", re.I)
CRITICAL_KEY = re.compile(r"(PROD|AWS|GCP|AZURE|DB_|DATABASE|POSTGRES|MYSQL|PRIVATE|SERVICE_ACCOUNT)", re.I)
TEST_PATH_SECRET = re.compile(r"(^|[/.])(test|testing|e2e|ci)([/.]|$)", re.I)
TEST_KEY = re.compile(r"(TEST|PLAYWRIGHT|E2E|CYPRESS|DUMMY|SAMPLE)", re.I)
SEVERITY_PENALTY = {"치명": 100, "높음": 50, "낮음": 20}


@dataclass(frozen=True)
class Criterion:
    key: str
    category: str
    title: str
    rule: str  # 근거가 된 회사 규칙 문장
    weight: int
    how: str  # git에서 무엇을 세는가
    caveat: str  # 이 항목의 한계


RUBRIC: tuple[Criterion, ...] = (
    Criterion("agent", "에이전트 활용", "에이전트 표기 비율 (참고, 점수 미반영)",
              "CLAUDE.md — 작업은 에이전트와 함께",
              0, "커밋에 에이전트 공동작성자 표기가 있는 비율",
              "Claude Code만 표기를 남기고 Codex는 남기지 않아 도구에 따라 점수가 갈린다 "
              "(대표 결정 2026-10-03: 점수에서 제외). 세션 기록 연결 후 다시 채점"),
    Criterion("tests", "품질", "코드 변경에 테스트 동반", "soul.md — 테스트 없는 병합은 원칙적으로 금지",
              20, "같은 날·같은 프로젝트의 코드 변경 묶음 중 테스트 파일도 바뀐 비율",
              "연구 저장소는 면제. 커밋당 파일 20개까지만 확인. 테스트가 필요 없는 변경도 분모에 들어간다"),
    Criterion("via_mr", "프로세스", "기본 브랜치 직접 push 회피", "git-workflow.md — main 직접 push 금지, MR로 병합",
              15, "push 중 기본 브랜치로 직접 들어간 것(MR 병합 제외)을 뺀 비율",
              "연구 저장소는 면제"),
    Criterion("why", "기록", "커밋 본문에 이유 기록", "git-workflow.md — body는 '왜' 변경했는지 설명",
              10, f"제목 외 본문이 {MIN_BODY_CHARS}자 이상인 커밋 비율", "길이만 본다. 내용이 '왜'인지는 v1에서 판정"),
    Criterion("conventional", "기록", "Conventional Commits 형식", "git-workflow.md — Conventional Commits",
              10, "제목이 feat:/fix: 등 형식을 따르는 비율", ""),
    Criterion("small", "품질", "작은 단위 변경", "soul.md — 큰 PR은 비용을 숨긴다, 작게 쪼개기가 기본",
              10, f"변경 {SMALL_COMMIT_LINES}줄 이하 커밋 비율", "자동 생성·lock 파일 변경도 줄 수에 들어간다"),
    Criterion("subject", "기록", f"커밋 제목 {MAX_SUBJECT_CHARS}자 이내", "git-workflow.md — subject는 50자 이내",
              5, f"제목이 {MAX_SUBJECT_CHARS}자 이하인 비율", "한글은 영문보다 글자당 정보가 많다"),
    Criterion("secrets", "보안", "시크릿 커밋 없음", "security.md — 시크릿은 코드에 없다",
              10, ".env·*.pem 등에 새로 넣은 비밀값마다 감점: 치명(개인키·운영·DB/클라우드) -100, "
              "높음(그 외 비밀번호·토큰) -50, 낮음(테스트 전용) -20. 같은 파일·변수는 한 건",
              "env류 파일만 연다. 일반 코드 안에 박힌 키는 v1에서"),
)


@dataclass
class ItemResult:
    passed: int
    total: int
    violations: list[str] = field(default_factory=list)  # "MM-DD [프로젝트] 제목 URL"
    # 비율이 아니라 감점식으로 매기는 항목(시크릿)의 점수
    fixed_score: float | None = None

    @property
    def rate(self) -> float | None:
        return self.passed / self.total if self.total else None

    @property
    def score(self) -> float | None:
        if self.fixed_score is not None:
            return self.fixed_score
        return None if self.rate is None else round(self.rate * PERCENT, 1)


def evidence(c: Commit) -> str:
    return f"{c.authored_at[5:10]} [{c.project.rsplit('/', 1)[-1]}] {c.title} {c.url}".strip()


def ratio_item(commits: list[Commit], ok: Callable[[Commit], bool]) -> ItemResult:
    bad = [c for c in commits if not ok(c)]
    return ItemResult(len(commits) - len(bad), len(commits), [evidence(c) for c in bad[:MAX_EVIDENCE]])


def body_chars(c: Commit) -> int:
    return len(c.message[len(c.title):].strip())


def is_exempt(project_path: str, research_namespaces: tuple[str, ...]) -> bool:
    """연구 저장소(대표 결정 2026-10-03)는 직접 push·테스트 동반 규칙에서 뺀다."""
    return project_path.split("/", 1)[0] in research_namespaces


def measure_tests(commits: list[Commit], research_namespaces: tuple[str, ...] = ()) -> ItemResult:
    """같은 날·같은 프로젝트를 한 작업 묶음으로 보고, 코드가 바뀐 묶음에 테스트도 바뀌었는지 본다."""
    groups: dict[tuple[str, str], list[Commit]] = defaultdict(list)
    for c in commits:
        if not is_exempt(c.project, research_namespaces):
            groups[(c.authored_at[:10], c.project)].append(c)
    total, bad = 0, []
    for group in groups.values():
        files = [f for c in group for f in c.files]
        if not any(CODE_EXT.search(f) and not TEST_PATH.search(f) for f in files):
            continue
        total += 1
        if not any(TEST_PATH.search(f) for f in files):
            bad.append(group[0])
    return ItemResult(total - len(bad), total, [evidence(c) for c in bad[:MAX_EVIDENCE]])


@dataclass(frozen=True)
class SecretFinding:
    """새로 커밋된 비밀값 한 건. 값은 담지 않는다."""

    path: str
    key: str
    severity: str  # 치명 / 높음 / 낮음

    def __str__(self) -> str:
        return f"[{self.severity}] {self.path}: {self.key}"


def secret_severity(path: str, key: str) -> str:
    if key == "개인키 블록" or CRITICAL_PATH.search(path) or CRITICAL_KEY.search(key):
        return "치명"
    if TEST_PATH_SECRET.search(path) or TEST_KEY.search(key):
        return "낮음"
    return "높음"


def secret_findings(path: str, diff: str, deleted: bool) -> list[SecretFinding]:
    """한 파일 변경에서 새로 들어간 비밀값의 '변수 이름'만 돌려준다. 값은 절대 담지 않는다."""
    if deleted or not SECRET_PATH.search(path) or SECRET_ALLOWED.search(path):
        return []
    keys = []
    for line in diff.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        if PRIVATE_KEY_BLOCK.search(line):
            keys.append("개인키 블록")
            continue
        m = ASSIGNMENT.match(line[1:])
        if m and SECRET_KEY_NAME.search(m.group(1)) and m.group(2).strip().strip("'\""):
            keys.append(m.group(1))
    return [SecretFinding(path, k, secret_severity(path, k)) for k in keys]


def measure_secrets(commits: list[Commit], findings: dict[str, list[SecretFinding]]) -> ItemResult:
    """100점에서 심각도별로 감점한다. 같은 파일·같은 변수를 다시 고친 것은 한 건으로 센다."""
    unique: dict[tuple[str, str], tuple[SecretFinding, Commit]] = {}
    for c in commits:
        for f in findings.get(c.sha, []):
            unique.setdefault((f.path, f.key), (f, c))
    penalty = sum(SEVERITY_PENALTY[f.severity] for f, _ in unique.values())
    evidence_lines = [f"{evidence(c)} ← {f}" for f, c in list(unique.values())[:MAX_EVIDENCE]]
    return ItemResult(0, len(unique), evidence_lines, fixed_score=max(0, PERCENT - penalty))


def measure_via_mr(
    pushes: list[dict], projects: dict[int, dict], research_namespaces: tuple[str, ...] = ()
) -> ItemResult:
    """push 이벤트 중 기본 브랜치에 MR 없이 직접 들어간 것을 위반으로 센다.

    projects: 프로젝트 id → {"default_branch", "path"}.
    """
    bad = []
    counted = [p for p in pushes
               if not is_exempt(projects.get(p["project_id"], {}).get("path", ""), research_namespaces)]
    for push in counted:
        data = push.get("push_data") or {}
        title = data.get("commit_title") or ""
        project = projects.get(push["project_id"], {})
        direct = (data.get("ref") == project.get("default_branch")
                  and data.get("ref_type") == "branch" and not title.startswith("Merge "))
        if direct:
            name = project.get("path", f"#{push['project_id']}").rsplit("/", 1)[-1]
            bad.append(f"{push['created_at'][5:10]} [{name}] {data.get('ref')} ← {title}")
    return ItemResult(len(counted) - len(bad), len(counted), bad[:MAX_EVIDENCE])


def measure_all(
    commits: list[Commit], pushes: list[dict], projects: dict[int, dict],
    secrets: dict[str, list[SecretFinding]] | None = None, research_namespaces: tuple[str, ...] = (),
) -> dict[str, ItemResult]:
    return {
        "agent": ratio_item(commits, lambda c: bool(AGENT_TRAILER.search(c.message))),
        "tests": measure_tests(commits, research_namespaces),
        "via_mr": measure_via_mr(pushes, projects, research_namespaces),
        "why": ratio_item(commits, lambda c: body_chars(c) >= MIN_BODY_CHARS),
        "conventional": ratio_item(commits, lambda c: bool(CONVENTIONAL.match(c.title))),
        "small": ratio_item(commits, lambda c: c.additions + c.deletions <= SMALL_COMMIT_LINES),
        "subject": ratio_item(commits, lambda c: len(c.title) <= MAX_SUBJECT_CHARS),
        "secrets": measure_secrets(commits, secrets or {}),
    }


def total_score(items: dict[str, ItemResult], commit_count: int) -> float | None:
    """가중 평균 (0~100). 표본이 부족하면 None. 분모가 0인 항목은 가중치에서 뺀다."""
    if commit_count < MIN_COMMITS_FOR_SCORE:
        return None
    scored = [(c.weight, items[c.key].score) for c in RUBRIC if items[c.key].score is not None]
    weight = sum(w for w, _ in scored)
    return round(sum(w * s for w, s in scored) / weight, 1) if weight else None


def scored_weight(items: dict[str, ItemResult]) -> tuple[int, int]:
    """(실제로 채점된 항목의 가중치 합, 전체 가중치 합). 면제·대상 없음 항목이 많으면 총점의 근거가 좁다."""
    return (sum(c.weight for c in RUBRIC if items[c.key].score is not None), sum(c.weight for c in RUBRIC))
