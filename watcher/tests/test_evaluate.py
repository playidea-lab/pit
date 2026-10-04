from git_watcher.evaluate import (
    MIN_COMMITS_FOR_SCORE,
    SecretFinding,
    measure_all,
    measure_secrets,
    measure_tests,
    measure_via_mr,
    secret_findings,
    secret_severity,
    total_score,
)
from git_watcher.gitlab import Commit


def commit(title: str = "feat: x", files: tuple[str, ...] = (), day: str = "2026-09-01",
           project: str = "pi/app", lines: int = 10, message: str = "") -> Commit:
    return Commit(sha="s", project=project, title=title, message=message or title,
                  authored_at=f"{day}T10:00:00+09:00", additions=lines, deletions=0, files=list(files))


def test_measure_tests_counts_same_day_project_group_once() -> None:
    commits = [commit(files=("src/a.py",)), commit(files=("tests/test_a.py",)),  # 9/1: 코드+테스트
               commit(files=("src/b.py",), day="2026-09-02")]                     # 9/2: 코드만
    item = measure_tests(commits)
    assert (item.passed, item.total) == (1, 2)


def test_measure_tests_ignores_docs_only_groups() -> None:
    assert measure_tests([commit(files=("README.md",))]).total == 0


def test_secret_findings_ignores_public_config_and_deletions() -> None:
    diff = "+VITE_API_BASE_URL=https://api.example.com\n+PLAYWRIGHT_PASS=hunter2\n+API_TOKEN=\n"
    assert [str(f) for f in secret_findings("frontend/.env.test", diff, deleted=False)] == [
        "[낮음] frontend/.env.test: PLAYWRIGHT_PASS"]
    assert secret_findings("frontend/.env", diff, deleted=True) == []
    assert secret_findings("frontend/.env.example", diff, deleted=False) == []


def test_secret_findings_never_returns_the_value() -> None:
    found = secret_findings(".env", "+DB_PASSWORD=supersecretvalue\n", deleted=False)
    assert found and "supersecretvalue" not in " ".join(str(f) for f in found)


def test_secret_severity_levels() -> None:
    assert secret_severity("deploy/.env.prod", "API_TOKEN") == "치명"
    assert secret_severity(".env", "DB_PASSWORD") == "치명"
    assert secret_severity(".env", "SLACK_TOKEN") == "높음"
    assert secret_severity("frontend/.env.test", "PLAYWRIGHT_PASS") == "낮음"


def test_measure_secrets_deducts_by_severity_and_dedupes_same_key() -> None:
    a, b = commit(files=(".env.test",)), commit(files=(".env.test",))
    b = Commit(**{**b.__dict__, "sha": "s2"})
    low = SecretFinding(".env.test", "PLAYWRIGHT_PASS", "낮음")
    assert measure_secrets([a], {}).score == 100
    # 같은 테스트 비밀번호를 두 번 고쳐도 한 건(-20)
    assert measure_secrets([a, b], {a.sha: [low], b.sha: [low]}).score == 80
    high = SecretFinding(".env", "SLACK_TOKEN", "높음")
    crit = SecretFinding(".env", "DB_PASSWORD", "치명")
    assert measure_secrets([a], {a.sha: [low, high, crit]}).score == 0


def test_measure_via_mr_flags_direct_push_to_default_branch_only() -> None:
    def push(ref: str, title: str) -> dict:
        return {"project_id": 1, "created_at": "2026-09-01T00:00:00Z",
                "push_data": {"ref": ref, "ref_type": "branch", "commit_title": title}}
    pushes = [push("main", "fix: hot"), push("main", "Merge branch 'x'"), push("feature/a", "feat: a")]
    item = measure_via_mr(pushes, {1: {"default_branch": "main", "path": "pi/app"}})
    assert (item.passed, item.total) == (2, 3)
    assert item.violations[0].startswith("09-01 [app] main")


def test_total_score_withholds_when_sample_too_small() -> None:
    few = [commit()] * (MIN_COMMITS_FOR_SCORE - 1)
    assert total_score(measure_all(few, [], {}), len(few)) is None


def test_total_score_skips_items_without_denominator() -> None:
    # 테스트 대상 코드 변경·push가 없으면 그 항목은 가중치에서 빠지고 나머지로 평균한다
    many = [commit(title="feat: add thing", message="feat: add thing\n\n왜 바꿨는지 충분히 길게 적은 본문입니다")]
    many *= MIN_COMMITS_FOR_SCORE
    items = measure_all(many, [], {})
    assert items["tests"].score is None and items["via_mr"].score is None
    assert total_score(items, len(many)) is not None


def test_research_repos_are_exempt_from_tests_and_direct_push() -> None:
    research = commit(files=("train.py",), project="research/linea")
    assert measure_tests([research], ("research",)).total == 0
    push = {"project_id": 9, "created_at": "2026-09-01T00:00:00Z",
            "push_data": {"ref": "main", "ref_type": "branch", "commit_title": "updated weights"}}
    projects = {9: {"default_branch": "main", "path": "research/linea"}}
    assert measure_via_mr([push], projects, ("research",)).total == 0
    assert measure_via_mr([push], projects).total == 1  # 면제 설정이 없으면 위반으로 센다


def test_agent_trailer_is_reference_only_and_does_not_move_total() -> None:
    from git_watcher.evaluate import RUBRIC
    assert next(c for c in RUBRIC if c.key == "agent").weight == 0
    body = "feat: add thing\n\n왜 바꿨는지 충분히 길게 적은 본문입니다"
    plain = [commit(title="feat: add thing", message=body)] * MIN_COMMITS_FOR_SCORE
    tagged = [commit(title="feat: add thing", message=body + "\n\nCo-Authored-By: Claude <x@y>")]
    tagged *= MIN_COMMITS_FOR_SCORE
    # Codex처럼 표기가 없어도 총점은 같아야 한다
    assert total_score(measure_all(plain, [], {}), len(plain)) == total_score(measure_all(tagged, [], {}), len(tagged))
