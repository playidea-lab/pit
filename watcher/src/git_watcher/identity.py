"""커밋 작성자 이메일 → GitLab 계정 매핑 (등록 이메일 + 학습한 별칭)."""

import json
import logging
from datetime import datetime
from pathlib import Path

from git_watcher.gitlab import GitLabClient, build_email_index, learn_aliases

logger = logging.getLogger(__name__)

# 커밋 이메일 → GitLab username. 자동 학습되며 손으로 고쳐도 된다
ALIASES_FILE = "aliases.json"


def load_aliases(state_dir: Path) -> dict[str, str]:
    path = state_dir / ALIASES_FILE
    return json.loads(path.read_text()) if path.exists() else {}


def save_aliases(state_dir: Path, aliases: dict[str, str]) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(dict(sorted(aliases.items())), ensure_ascii=False, indent=2)
    (state_dir / ALIASES_FILE).write_text(text + "\n")


def build_index(gl: GitLabClient, users: list[dict], since: datetime, state_dir: Path) -> dict[str, dict]:
    """등록 이메일 + 저장된 별칭 + 이번 기간 push에서 새로 배운 별칭을 합친다."""
    index = build_email_index(users)
    by_username = {u["username"]: u for u in users}
    aliases = load_aliases(state_dir)
    # 등록된 이메일이 학습한 별칭보다 항상 우선한다
    known = {**{e: by_username[n] for e, n in aliases.items() if n in by_username}, **index}
    learned = learn_aliases(gl, users, since, known)
    if learned:
        logger.info("새 이메일 별칭 학습: %s", learned)
        aliases.update(learned)
        save_aliases(state_dir, aliases)
    return {**known, **{e: by_username[n] for e, n in learned.items()}}
