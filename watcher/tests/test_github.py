from datetime import datetime, timedelta, timezone

from git_watcher import github
from git_watcher.gitlab import Account
from git_watcher.sources import merge

SINCE = datetime(2026, 10, 1, tzinfo=timezone.utc)
UNTIL = SINCE + timedelta(days=1)
EMAIL_INDEX = {"bob@corp.com": {"username": "bob", "name": "Bob"}}


def detail(sha: str, login: str | None, email: str, parents: int = 1) -> dict:
    return {"sha": sha * 8, "html_url": f"https://example.test/{sha}", "parents": [{}] * parents,
            "author": {"login": login} if login else None,
            "commit": {"message": f"feat: {sha}\n\n본문", "author": {"email": email, "name": "n",
                                                                    "date": "2026-10-01T03:00:00Z"}},
            "stats": {"additions": 3, "deletions": 1}, "files": [{"filename": "src/a.py", "status": "modified"}]}


class FakeGitHub:
    def __init__(self, by_branch: dict[str, list[dict]]) -> None:
        self.by_branch = by_branch
        self.details = {d["sha"]: d for ds in by_branch.values() for d in ds}

    def active_repos(self, owners: list[str], since: datetime) -> list[dict]:
        return [{"full_name": "org/app"}]

    def branches(self, repo: str) -> list[str]:
        return list(self.by_branch)

    def org_members(self, owners: list[str]) -> set[str]:
        return {"teammate"}

    def commits(self, repo: str, branch: str, since: datetime, until: datetime) -> list[dict]:
        return self.by_branch[branch]

    def commit(self, repo: str, sha: str) -> dict:
        return self.details[sha]


def test_account_for_prefers_login_map_then_email_then_github_login() -> None:
    assert github.account_for(detail("a", "Carol-GH", "x@mail.example"), {"carol-gh": "carol"}, {})[0] == "carol"
    assert github.account_for(detail("b", "someone", "bob@corp.com"), {}, EMAIL_INDEX)[0] == "bob"
    assert github.account_for(detail("c", "ghost99", "z@z.com"), {}, EMAIL_INDEX)[0] == "github:ghost99"


def test_collect_dedupes_across_branches_and_skips_merges() -> None:
    shared = detail("a", "carol-gh", "x@mail.example")
    client = FakeGitHub({"main": [shared, detail("m", "carol-gh", "x@mail.example", parents=2)],
                         "feature": [shared, detail("b", "someone", "bob@corp.com")]})
    accounts = github.collect(client, ["org"], SINCE, UNTIL, {"carol-gh": "carol"}, EMAIL_INDEX)
    assert {k: len(a.commits) for k, a in accounts.items()} == {"carol": 1, "bob": 1}
    c = accounts["bob"].commits[0]
    assert (c.source, c.project, c.additions, c.files) == ("github", "org/app", 3, ["src/a.py"])


def test_merge_combines_same_person_across_hosts() -> None:
    gitlab = {"bob": Account("bob", "Bob (@bob)", [object()])}  # type: ignore[list-item]
    gh = {"bob": Account("bob", "bob", [object(), object()])}  # type: ignore[list-item]
    merged = merge(gitlab, gh)
    assert len(merged["bob"].commits) == 3 and merged["bob"].display == "Bob (@bob)"


def test_collect_drops_outside_contributors_but_keeps_unmapped_org_members() -> None:
    client = FakeGitHub({"main": [detail("a", "stranger", "s@x.com"), detail("b", "Teammate", "t@x.com")]})
    accounts = github.collect(client, ["org"], SINCE, UNTIL, {}, {})
    assert list(accounts) == ["github:Teammate"]


def test_collect_drops_excluded_former_members_even_if_still_in_org() -> None:
    client = FakeGitHub({"main": [detail("a", "Teammate", "t@x.com")]})
    assert github.collect(client, ["org"], SINCE, UNTIL, {}, {}, frozenset({"teammate"})) == {}
