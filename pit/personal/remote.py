"""pithub 서버와의 통신 (로컬 pit 전용 HTTP API)

주소와 토큰은 코드에 없다. 주소는 PITHUB_URL 환경변수 → 저장된 설정, 토큰은 $PIT_HOME/remote.json(0600).
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

import httpx
from pydantic import BaseModel

from pit.decisions.models import Decision, DecisionKind

logger = logging.getLogger(__name__)

PITHUB_URL_ENV = "PITHUB_URL"
REMOTE_FILENAME = "remote.json"
REMOTE_FILE_MODE = 0o600
HTTP_TIMEOUT_SECONDS = 30.0
PUSH_BATCH_SIZE = 200


class RemoteError(Exception):
    """서버에 닿지 못했거나 거부됨"""


class RemoteConfig(BaseModel):
    url: str
    token: str
    github_login: str | None = None


def load_remote(home: Path) -> RemoteConfig | None:
    path = home / REMOTE_FILENAME
    if not path.exists():
        return None
    return RemoteConfig.model_validate_json(path.read_text(encoding="utf-8"))


def save_remote(home: Path, config: RemoteConfig) -> None:
    path = home / REMOTE_FILENAME
    path.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    path.chmod(REMOTE_FILE_MODE)


def resolve_url(explicit: str | None, saved: RemoteConfig | None) -> str:
    url = explicit or os.environ.get(PITHUB_URL_ENV) or (saved.url if saved else None)
    if not url:
        raise RemoteError(f"pithub 주소가 없습니다. {PITHUB_URL_ENV} 환경변수나 'pit login --url' 로 지정하세요.")
    return url.rstrip("/")


# 주제가 아니라 표지인 태그
NON_TOPIC_TAGS = frozenset({"principle"})
MAX_PUSH_TOPICS = 6


def to_wire(decision: Decision) -> dict[str, object]:
    """로컬 Decision → 서버의 StoredDecision 모양. 소유자는 서버가 토큰으로 정하므로 0을 보낸다."""
    return {
        "id": decision.id,
        "owner_github_id": 0,
        "kind": decision.kind.value,
        "verdict": decision.verdict.value if decision.verdict else None,
        "reject_kind": decision.reject_kind.value if decision.reject_kind else None,
        "situation": decision.situation,
        "proposal": decision.proposal,
        "options": decision.options,
        "chosen": decision.chosen if decision.kind is DecisionKind.CHOICE else None,
        "rationale": decision.rationale,
        "human_quote": decision.human_quote,
        "tags": decision.tags,
        "supersedes": decision.supersedes,
        "decided_at": decision.decided_at.isoformat(),
        "source": {
            "tool": decision.source.tool,
            "device": decision.source.device,
            "session_id": decision.source.session_id,
            "project": decision.project or "",
        },
        "dedupe_key": decision.id,
        # 그래프 규약(G2): 로컬 태그를 주제 노드로 올린다. 프로젝트는 source.project 로 서버가 노드로 만든다.
        "about": [{"kind": "topic", "name": tag} for tag in decision.tags if tag and tag not in NON_TOPIC_TAGS][:MAX_PUSH_TOPICS],
    }


class RemoteClient:
    def __init__(self, url: str, token: str, client: httpx.Client | None = None) -> None:
        self._url = url
        self._client = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
        self._headers = {"Authorization": f"Bearer {token}"}

    def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        try:
            response = self._client.request(method, f"{self._url}{path}", headers=self._headers, **kwargs)
        except httpx.HTTPError as e:
            raise RemoteError(f"pithub에 닿지 못했습니다: {type(e).__name__}") from e
        if response.status_code >= 400:
            detail = ""
            try:
                detail = str(response.json().get("error", ""))
            except (ValueError, AttributeError):
                pass
            raise RemoteError(f"pithub가 거부했습니다 ({response.status_code}) {detail}".rstrip())
        return response

    def whoami(self) -> dict[str, object]:
        return self._request("GET", "/api/v1/me").json()

    def push(self, decisions: list[Decision]) -> int:
        total = 0
        for start in range(0, len(decisions), PUSH_BATCH_SIZE):
            batch = [to_wire(d) for d in decisions[start : start + PUSH_BATCH_SIZE]]
            total += int(self._request("POST", "/api/v1/decisions", json={"decisions": batch}).json()["upserted"])
        return total

    def pull(self, since: datetime | None = None, origin: str | None = None) -> list[dict[str, object]]:
        params: dict[str, str] = {}
        if since:
            params["since"] = since.isoformat()
        if origin:
            params["origin"] = origin
        return list(self._request("GET", "/api/v1/decisions", params=params).json()["decisions"])


def save_pulled(home: Path, rows: list[dict[str, object]]) -> Path:
    """내려받은 결정을 $PIT_HOME/remote/pulled.jsonl 에 둔다 (감사의 재료, git 미추적)"""
    path = home / "remote" / "pulled.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    path.chmod(REMOTE_FILE_MODE)
    return path


def load_pulled(home: Path) -> list[dict[str, object]]:
    path = home / "remote" / "pulled.jsonl"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
