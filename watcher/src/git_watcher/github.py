"""GitHub REST API에서 기간 내 커밋을 모아 GitLab과 같은 Commit 형태로 만든다.

GitHub는 인증된 이메일의 커밋에 계정(author.login)을 붙여 주므로 사람 식별이 GitLab보다 쉽다.
"""

import logging
from collections.abc import Iterator
from datetime import datetime

import httpx

from git_watcher.gitlab import Account, Commit

logger = logging.getLogger(__name__)

PER_PAGE = 100
REQUEST_TIMEOUT_SEC = 30.0
MAX_FILES_PER_COMMIT = 20
HTTP_CONFLICT = 409  # 빈 저장소
HTTP_NOT_FOUND = 404  # 조직이 아니라 개인 계정
SOURCE = "github"


class GitHubClient:
    def __init__(self, api_url: str, token: str) -> None:
        self._http = httpx.Client(
            base_url=api_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            timeout=REQUEST_TIMEOUT_SEC,
        )

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self._http.close()

    def _paginate(self, path: str, params: dict[str, str]) -> Iterator[dict]:
        """Link 헤더의 next를 따라 모든 페이지를 순회한다."""
        url: str | None = path
        query: dict[str, str] | None = {**params, "per_page": str(PER_PAGE)}
        while url:
            resp = self._http.get(url, params=query)
            if resp.status_code == HTTP_CONFLICT:
                return
            resp.raise_for_status()
            yield from resp.json()
            url = resp.links.get("next", {}).get("url")
            query = None  # next URL에 쿼리가 이미 들어 있다

    def active_repos(self, owners: list[str], since: datetime) -> list[dict]:
        """토큰이 볼 수 있는 저장소 중 지정한 계정·조직 소유이고 기간 안에 push된 것."""
        wanted = {o.lower() for o in owners}
        repos = self._paginate("/user/repos", {"affiliation": "owner,collaborator,organization_member"})
        return [r for r in repos if r["owner"]["login"].lower() in wanted
                and r.get("pushed_at") and datetime.fromisoformat(r["pushed_at"]) >= since]

    def org_members(self, owners: list[str]) -> set[str]:
        """조직 멤버 계정(소문자). 개인 계정 소유자는 조직이 아니므로 건너뛴다."""
        members: set[str] = set()
        for owner in owners:
            resp = self._http.get(f"/orgs/{owner}/members", params={"per_page": str(PER_PAGE)})
            if resp.status_code == HTTP_NOT_FOUND:
                continue
            resp.raise_for_status()
            members |= {m["login"].lower() for m in self._paginate(f"/orgs/{owner}/members", {})}
        return members

    def branches(self, repo: str) -> list[str]:
        return [b["name"] for b in self._paginate(f"/repos/{repo}/branches", {})]

    def commits(self, repo: str, branch: str, since: datetime, until: datetime) -> list[dict]:
        params = {"sha": branch, "since": since.isoformat(), "until": until.isoformat()}
        return list(self._paginate(f"/repos/{repo}/commits", params))

    def commit(self, repo: str, sha: str) -> dict:
        resp = self._http.get(f"/repos/{repo}/commits/{sha}")
        resp.raise_for_status()
        return resp.json()

    def commit_diff(self, repo: str, sha: str) -> list[dict]:
        """GitLab commit_diff 와 같은 모양(new_path·diff·deleted_file)으로 돌려준다."""
        files = self.commit(repo, sha).get("files", [])
        return [{"new_path": f["filename"], "diff": f.get("patch", ""), "deleted_file": f["status"] == "removed"}
                for f in files]


def account_for(detail: dict, login_map: dict[str, str], email_index: dict[str, dict]) -> tuple[str, str]:
    """GitHub 커밋 → (계정 키, 표시 이름). 계정 매핑 > 이메일 > GitHub 계정 순."""
    login = (detail.get("author") or {}).get("login") or ""
    if login.lower() in login_map:
        user = login_map[login.lower()]
        return user, user
    email = (detail["commit"]["author"].get("email") or "").strip().lower()
    if email in email_index:
        user = email_index[email]
        return user["username"], f"{user['name']} (@{user['username']})"
    if login:
        return f"github:{login}", f"{login} (GitHub 계정, 사람 매핑 없음)"
    return f"email:{email}", f"{detail['commit']['author'].get('name', '?')} <{email}> (GitHub, 계정 없음)"


def to_commit(repo: str, detail: dict) -> Commit:
    message = detail["commit"]["message"].strip()
    stats = detail.get("stats") or {}
    return Commit(
        sha=detail["sha"][:8],
        project=repo,
        title=message.splitlines()[0] if message else "",
        message=message,
        authored_at=detail["commit"]["author"]["date"],
        additions=stats.get("additions", 0),
        deletions=stats.get("deletions", 0),
        files=[f["filename"] for f in detail.get("files", [])][:MAX_FILES_PER_COMMIT],
        url=detail.get("html_url", ""),
        source=SOURCE,
    )


def collect(
    client: GitHubClient, owners: list[str], since: datetime, until: datetime,
    login_map: dict[str, str], email_index: dict[str, dict], excluded: frozenset[str] = frozenset(),
) -> dict[str, Account]:
    """모든 브랜치의 기간 내 커밋을 계정별로 모은다. 브랜치 간 중복·머지 커밋은 뺀다."""
    accounts: dict[str, Account] = {}
    seen: set[str] = set()
    for repo in client.active_repos(owners, since):
        name = repo["full_name"]
        for branch in client.branches(name):
            for raw in client.commits(name, branch, since, until):
                if raw["sha"] in seen or len(raw.get("parents", [])) > 1:
                    continue
                seen.add(raw["sha"])
                detail = client.commit(name, raw["sha"])  # 줄 수·파일은 단건 조회에만 있다
                key, display = account_for(detail, login_map, email_index)
                accounts.setdefault(key, Account(key=key, display=display)).commits.append(to_commit(name, detail))
    # 공개 저장소의 외부 기여자는 직원이 아니다 — 사람 매핑도 없고 조직 멤버도 아니면 뺀다
    members = client.org_members(owners)
    # 퇴사자 등 people.json github_exclude 계정도 뺀다 (조직에 아직 남아 있어도)
    outsiders = [k for k in accounts if k.startswith("github:")
                 and (k.removeprefix("github:").lower() not in members or k.removeprefix("github:").lower() in excluded)]
    for key in outsiders:
        del accounts[key]
    logger.info("GitHub 수집 완료: 계정 %d, 커밋 %d (외부 기여자·제외 계정 %d개 제외)", len(accounts), len(seen), len(outsiders))
    return accounts
