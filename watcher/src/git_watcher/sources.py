"""코드 호스트(GitLab·GitHub)별 수집 결과를 사람 단위로 합친다."""

from datetime import datetime

from git_watcher import github
from git_watcher.config import Settings
from git_watcher.gitlab import Account, GitLabClient, collect
from git_watcher.people import load_github_exclude, load_github_logins


def merge(*sources: dict[str, Account]) -> dict[str, Account]:
    """같은 계정 키의 커밋을 한 Account로 합친다 (GitLab 표시 이름 우선)."""
    merged: dict[str, Account] = {}
    for accounts in sources:
        for key, account in accounts.items():
            if key in merged:
                merged[key].commits.extend(account.commits)
            else:
                merged[key] = Account(key=key, display=account.display, commits=list(account.commits))
    return merged


def github_enabled(settings: Settings) -> bool:
    return settings.github_token is not None and bool(settings.github_owners)


def collect_all(
    settings: Settings, gl: GitLabClient, since: datetime, until: datetime,
    email_index: dict[str, dict], with_files: bool = True,
) -> dict[str, Account]:
    gitlab_accounts = collect(gl, since, until, email_index, with_files)
    if not github_enabled(settings):
        return gitlab_accounts
    assert settings.github_token is not None
    with github.GitHubClient(settings.github_api_url, settings.github_token.get_secret_value()) as gh:
        github_accounts = github.collect(gh, settings.github_owners, since, until, load_github_logins(), email_index,
                                         frozenset(load_github_exclude()))
    return merge(gitlab_accounts, github_accounts)


def commit_diff(settings: Settings, gl: GitLabClient, project: str, sha: str, source: str) -> list[dict]:
    """커밋이 온 호스트에서 diff를 가져온다 (시크릿 검사용)."""
    if source == github.SOURCE and settings.github_token is not None:
        with github.GitHubClient(settings.github_api_url, settings.github_token.get_secret_value()) as gh:
            return gh.commit_diff(project, sha)
    return gl.commit_diff(project, sha)
