"""GitHub API 연동 서비스

GitHub repo에서 .pit/ 폴더 내용을 읽어옴
"""

import base64
import os
from typing import Optional

import httpx
import yaml

GITHUB_API_BASE = "https://api.github.com"


class GitHubService:
    """GitHub API를 통해 .pit/ 폴더 읽기"""

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"

    async def _get(self, url: str) -> Optional[dict]:
        """GitHub API GET 요청"""
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code == 200:
                return response.json()
            return None

    async def _get_file_content(
        self, owner: str, repo: str, path: str, branch: str = "main"
    ) -> Optional[str]:
        """파일 내용 읽기 (base64 디코딩)"""
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{path}?ref={branch}"
        data = await self._get(url)
        if not data or "content" not in data:
            return None

        # base64 디코딩
        content = base64.b64decode(data["content"]).decode("utf-8")
        return content

    async def _list_directory(
        self, owner: str, repo: str, path: str, branch: str = "main"
    ) -> list[dict]:
        """디렉토리 내 파일 목록"""
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{path}?ref={branch}"
        data = await self._get(url)
        if not data or not isinstance(data, list):
            return []
        return data

    async def get_pit_config(self, owner: str, repo: str) -> Optional[dict]:
        """
        .pit/config.yaml 읽기

        Returns:
            프로젝트 설정 dict 또는 None
        """
        content = await self._get_file_content(owner, repo, ".pit/config.yaml")
        if not content:
            return None
        return yaml.safe_load(content)

    async def list_features(self, owner: str, repo: str) -> list[dict]:
        """
        .pit/features/ 내 모든 Feature 목록

        Returns:
            Feature 정보 리스트 (id, title, status, priority)
        """
        files = await self._list_directory(owner, repo, ".pit/features")
        features = []

        for file in files:
            if file["name"].endswith(".yaml"):
                content = await self._get_file_content(
                    owner, repo, f".pit/features/{file['name']}"
                )
                if content:
                    feature = yaml.safe_load(content)
                    features.append({
                        "id": feature.get("id"),
                        "title": feature.get("title"),
                        "status": feature.get("status"),
                        "priority": feature.get("priority"),
                        "progress": self._calc_progress(feature.get("checklist", [])),
                    })

        return features

    async def get_feature(
        self, owner: str, repo: str, feature_id: str
    ) -> Optional[dict]:
        """
        특정 Feature 상세 정보

        feature_id 또는 파일명으로 검색
        """
        files = await self._list_directory(owner, repo, ".pit/features")

        for file in files:
            if file["name"].endswith(".yaml"):
                # F-0001 또는 F-0001-xxx.yaml 형식 매칭
                if file["name"].startswith(feature_id):
                    content = await self._get_file_content(
                        owner, repo, f".pit/features/{file['name']}"
                    )
                    if content:
                        return yaml.safe_load(content)
        return None

    async def list_decisions(self, owner: str, repo: str) -> list[dict]:
        """
        .pit/decisions/ 내 모든 Decision 목록

        Returns:
            Decision 정보 리스트 (id, title)
        """
        files = await self._list_directory(owner, repo, ".pit/decisions")
        decisions = []

        for file in files:
            if file["name"].endswith(".md"):
                # frontmatter에서 메타데이터 추출
                content = await self._get_file_content(
                    owner, repo, f".pit/decisions/{file['name']}"
                )
                if content:
                    meta = self._parse_frontmatter(content)
                    decisions.append({
                        "id": meta.get("id"),
                        "title": meta.get("title"),
                        "status": meta.get("status"),
                    })

        return decisions

    async def get_decision(
        self, owner: str, repo: str, decision_id: str
    ) -> Optional[dict]:
        """특정 Decision 상세 (frontmatter + content)"""
        files = await self._list_directory(owner, repo, ".pit/decisions")

        for file in files:
            if file["name"].endswith(".md") and file["name"].startswith(decision_id):
                content = await self._get_file_content(
                    owner, repo, f".pit/decisions/{file['name']}"
                )
                if content:
                    meta = self._parse_frontmatter(content)
                    body = self._extract_body(content)
                    return {**meta, "content": body}
        return None

    def _calc_progress(self, checklist: list) -> str:
        """체크리스트 진행률 계산"""
        if not checklist:
            return "0/0"
        done = sum(1 for item in checklist if item.get("done"))
        return f"{done}/{len(checklist)}"

    def _parse_frontmatter(self, content: str) -> dict:
        """마크다운 frontmatter 파싱"""
        if not content.startswith("---"):
            return {}

        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}

        return yaml.safe_load(parts[1]) or {}

    def _extract_body(self, content: str) -> str:
        """frontmatter 이후 본문 추출"""
        if not content.startswith("---"):
            return content

        parts = content.split("---", 2)
        if len(parts) < 3:
            return content

        return parts[2].strip()
