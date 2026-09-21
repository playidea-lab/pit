"""개인 보관함의 git 이력

결정을 확정·수정·대체할 때마다 commit이 남는다. 원문(vault/)과 캐시는
.gitignore로 빠져 있어 추적되지 않는다. git이 실패해도 검토 결과 자체는
이미 파일로 저장돼 있으므로 경고만 남긴다.
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

GIT_TIMEOUT_SECONDS = 30
COMMIT_AUTHOR_NAME = "pit"
COMMIT_AUTHOR_EMAIL = "pit@localhost"


def _git(home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(home), *args],
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
        check=True,
    )


def ensure_repo(home: Path) -> bool:
    """보관함을 git repo로 만든다 (이미 repo면 그대로 둔다). 실패하면 False."""
    if (home / ".git").exists():
        return True
    try:
        _git(home, "init", "--quiet")
        return True
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("개인 보관함 git 초기화 실패", extra={"error": type(e).__name__})
        return False


def commit_paths(home: Path, paths: list[Path], message: str) -> bool:
    """지정한 경로의 변경을 commit한다. 바뀐 것이 없거나 실패하면 False."""
    if not paths or not ensure_repo(home):
        return False
    # 없는 경로를 넘기면 git add가 실패한다. 디렉터리를 넘기면 그 안의 삭제도 -A로 반영된다.
    relative = [str(path.relative_to(home)) for path in paths if path.exists()]
    if not relative:
        return False
    try:
        _git(home, "add", "-A", "--", *relative)
        staged = _git(home, "diff", "--cached", "--name-only").stdout.strip()
        if not staged:
            return False
        _git(
            home,
            "-c", f"user.name={COMMIT_AUTHOR_NAME}",
            "-c", f"user.email={COMMIT_AUTHOR_EMAIL}",
            "commit", "--quiet", "-m", message,
        )  # fmt: skip
        return True
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("개인 보관함 commit 실패", extra={"error": type(e).__name__})
        return False
