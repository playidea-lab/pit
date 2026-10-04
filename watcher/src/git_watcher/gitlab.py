"""GitLab REST API에서 기간 내 커밋을 계정별로 수집한다."""

import logging
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, tzinfo
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

PER_PAGE = 100
REQUEST_TIMEOUT_SEC = 30.0
# 커밋 하나당 LLM에 넘길 변경 파일 경로 최대 개수
MAX_FILES_PER_COMMIT = 20


@dataclass
class Commit:
    sha: str
    project: str
    title: str
    message: str
    authored_at: str
    additions: int
    deletions: int
    files: list[str] = field(default_factory=list)
    url: str = ""
    source: str = "gitlab"  # 커밋이 온 코드 호스트


@dataclass
class Account:
    """브리핑 단위. GitLab 사용자에 매칭되지 않은 커밋 작성자도 하나의 계정으로 본다."""

    key: str
    display: str
    commits: list[Commit] = field(default_factory=list)


class GitLabClient:
    def __init__(self, base_url: str, token: str) -> None:
        self._http = httpx.Client(
            base_url=base_url.rstrip("/") + "/api/v4",
            headers={"PRIVATE-TOKEN": token},
            timeout=REQUEST_TIMEOUT_SEC,
        )

    def __enter__(self) -> "GitLabClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self._http.close()

    def _paginate(self, path: str, params: dict[str, str]) -> Iterator[dict]:
        """X-Next-Page 헤더를 따라 모든 페이지를 순회한다."""
        page = "1"
        while page:
            resp = self._http.get(path, params={**params, "per_page": str(PER_PAGE), "page": page})
            resp.raise_for_status()
            yield from resp.json()
            page = resp.headers.get("X-Next-Page", "")

    def human_users(self) -> list[dict]:
        users = self._paginate("/users", {"active": "true", "humans": "true"})
        return [u for u in users if not u.get("bot")]

    def active_projects(self, since: datetime) -> list[dict]:
        params = {"last_activity_after": since.isoformat(), "archived": "false", "simple": "true"}
        return list(self._paginate("/projects", params))

    def commits(self, project: dict, since: datetime, until: datetime) -> list[dict]:
        params = {
            "since": since.isoformat(),
            "until": until.isoformat(),
            "all": "true",  # 기본 브랜치뿐 아니라 모든 브랜치
            "with_stats": "true",
        }
        return list(self._paginate(f"/projects/{project['id']}/repository/commits", params))

    def events(self, user_id: int, after: str, before: str) -> list[dict]:
        """사용자의 모든 이벤트. after/before는 날짜(YYYY-MM-DD)이며 둘 다 그 날짜를 포함하지 않는다."""
        return list(self._paginate(f"/users/{user_id}/events", {"after": after, "before": before}))

    def push_events(self, user_id: int, since: datetime) -> list[dict]:
        # events API의 after는 날짜 단위(해당 날짜 '이후')라 하루 앞당겨 조회한다
        after = (since - timedelta(days=1)).date().isoformat()
        params = {"action": "pushed", "after": after}
        return list(self._paginate(f"/users/{user_id}/events", params))

    def project(self, project_id: int) -> dict:
        resp = self._http.get(f"/projects/{project_id}", params={"simple": "true"})
        resp.raise_for_status()
        return resp.json()

    def commit(self, project_id: int, sha: str) -> dict:
        resp = self._http.get(f"/projects/{project_id}/repository/commits/{sha}")
        resp.raise_for_status()
        return resp.json()

    def commit_diff(self, project: str | int, sha: str) -> list[dict]:
        """커밋의 파일별 diff 전체. project는 id 또는 'group/name' 경로."""
        pid = quote(str(project), safe="")
        return list(self._paginate(f"/projects/{pid}/repository/commits/{sha}/diff", {}))

    def changed_files(self, project_id: int, sha: str) -> list[str]:
        resp = self._http.get(
            f"/projects/{project_id}/repository/commits/{sha}/diff",
            params={"per_page": str(MAX_FILES_PER_COMMIT)},
        )
        resp.raise_for_status()
        return [d["new_path"] for d in resp.json()][:MAX_FILES_PER_COMMIT]


def build_email_index(users: list[dict]) -> dict[str, dict]:
    """커밋 작성자 이메일 → GitLab 사용자. admin 토큰이어야 email 필드가 보인다."""
    index: dict[str, dict] = {}
    for user in users:
        for key in ("email", "commit_email", "public_email"):
            email = (user.get(key) or "").strip().lower()
            if email:
                index[email] = user
    return index


def learn_aliases(
    client: GitLabClient, users: list[dict], since: datetime, email_index: dict[str, dict]
) -> dict[str, str]:
    """push 이벤트로 '등록 안 된 커밋 이메일 → 그 커밋을 가장 많이 push한 사람'을 배운다.

    개인 메일(예: naver)로 커밋하는 사람은 이메일만으로는 계정에 연결되지 않는다.
    남의 커밋이 섞인 브랜치를 push하는 경우가 있어 첫 push가 아니라 다수결로 정한다.
    이미 어떤 계정에 등록된 이메일은 배우지 않는다.
    """
    votes: dict[str, Counter[str]] = defaultdict(Counter)
    for user in users:
        for event in client.push_events(user["id"], since):
            sha = (event.get("push_data") or {}).get("commit_to")
            if not sha:
                continue
            try:
                raw = client.commit(event["project_id"], sha)
            except httpx.HTTPStatusError as e:
                # 브랜치 삭제 등으로 사라진 커밋 — 학습만 건너뛴다
                logger.debug("커밋 조회 실패 %s: %s", sha, e)
                continue
            email = (raw.get("author_email") or "").strip().lower()
            if email and email not in email_index:
                votes[email][user["username"]] += 1
    return {email: counter.most_common(1)[0][0] for email, counter in votes.items()}


def is_merge_commit(raw: dict) -> bool:
    return len(raw.get("parent_ids") or []) > 1


def account_for(raw: dict, email_index: dict[str, dict]) -> tuple[str, str]:
    """커밋을 (계정 키, 표시 이름)으로 귀속한다."""
    email = (raw.get("author_email") or "").strip().lower()
    user = email_index.get(email)
    if user:
        return user["username"], f"{user['name']} (@{user['username']})"
    # GitLab 계정과 연결되지 않은 이메일 — 이름+이메일로 따로 묶는다
    return f"email:{email}", f"{raw.get('author_name', '?')} <{email}> (GitLab 계정 미연결)"


def collect(
    client: GitLabClient, since: datetime, until: datetime, email_index: dict[str, dict],
    with_files: bool = True,
) -> dict[str, Account]:
    """기간 내 모든 활성 프로젝트의 커밋을 계정별로 모은다. 브랜치 간 중복 sha는 한 번만 센다."""
    accounts: dict[str, Account] = {}
    seen: set[str] = set()
    seen_work: set[tuple[str, str, str, str]] = set()
    for project in client.active_projects(since):
        for raw in client.commits(project, since, until):
            work = (project["path_with_namespace"], raw.get("author_email", ""),
                    raw["title"], raw["authored_date"])
            if raw["id"] in seen or work in seen_work or is_merge_commit(raw):
                continue
            seen.add(raw["id"])
            seen_work.add(work)
            key, display = account_for(raw, email_index)
            account = accounts.setdefault(key, Account(key=key, display=display))
            account.commits.append(_to_commit(client, project, raw, with_files))
    logger.info("수집 완료: 계정 %d, 커밋 %d", len(accounts), len(seen))
    return accounts


def _to_commit(client: GitLabClient, project: dict, raw: dict, with_files: bool) -> Commit:
    stats = raw.get("stats") or {}
    return Commit(
        sha=raw["short_id"],
        project=project["path_with_namespace"],
        title=raw["title"],
        message=raw.get("message", "").strip(),
        authored_at=raw["authored_date"],
        additions=stats.get("additions", 0),
        deletions=stats.get("deletions", 0),
        url=raw.get("web_url", ""),
        files=client.changed_files(project["id"], raw["id"]) if with_files else [],
    )


def split_by_day(accounts: dict[str, Account], tz: tzinfo) -> dict[date, dict[str, Account]]:
    """계정별 커밋을 커밋한 날짜(tz 기준)별로 나눈다."""
    days: dict[date, dict[str, Account]] = defaultdict(dict)
    for key, account in accounts.items():
        for commit in account.commits:
            day = datetime.fromisoformat(commit.authored_at).astimezone(tz).date()
            bucket = days[day].setdefault(key, replace(account, commits=[]))
            bucket.commits.append(commit)
    return days
