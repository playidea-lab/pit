"""Decision 관련 엔드포인트"""

from fastapi import APIRouter, HTTPException

from pithub.api.services.github import GitHubService

router = APIRouter()


@router.get("/{owner}/{repo}")
async def list_decisions(owner: str, repo: str):
    """
    GitHub repo의 Decision 목록 조회

    예: GET /api/decisions/changmin/pit
    """
    github = GitHubService()

    decisions = await github.list_decisions(owner, repo)
    return {
        "owner": owner,
        "repo": repo,
        "decisions": decisions,
    }


@router.get("/{owner}/{repo}/{decision_id}")
async def get_decision(owner: str, repo: str, decision_id: str):
    """
    특정 Decision 상세 조회

    예: GET /api/decisions/changmin/pit/D-0001
    """
    github = GitHubService()

    decision = await github.get_decision(owner, repo, decision_id)
    if not decision:
        raise HTTPException(
            status_code=404,
            detail=f"Decision을 찾을 수 없습니다: {decision_id}"
        )

    return {
        "owner": owner,
        "repo": repo,
        "decision": decision,
    }
