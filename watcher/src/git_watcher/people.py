"""보고 대상 명단: 표시 이름(한글)과 제외 계정. people.json을 손으로 관리한다."""

import json

from git_watcher.config import PROJECT_ROOT

PEOPLE_FILE = PROJECT_ROOT / "people.json"
DEFAULT_EXCLUDE = ("root", "ghost")


def load_github_logins() -> dict[str, str]:
    """people.json 의 github: GitHub 계정(소문자) → GitLab username."""
    if not PEOPLE_FILE.exists():
        return {}
    data = json.loads(PEOPLE_FILE.read_text())
    return {login.lower(): user for login, user in data.get("github", {}).items()}


def load_github_exclude() -> set[str]:
    """people.json 의 github_exclude: 보고에서 뺄 GitHub 계정(소문자) — 퇴사자 등."""
    if not PEOPLE_FILE.exists():
        return set()
    return {login.lower() for login in json.loads(PEOPLE_FILE.read_text()).get("github_exclude", [])}


def load_people() -> tuple[dict[str, str], set[str]]:
    """people.json → (username → 표시 이름, 제외할 username)."""
    if not PEOPLE_FILE.exists():
        return {}, set(DEFAULT_EXCLUDE)
    data = json.loads(PEOPLE_FILE.read_text())
    return data.get("names", {}), set(data.get("exclude", DEFAULT_EXCLUDE))
