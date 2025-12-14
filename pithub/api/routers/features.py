"""Feature 관련 엔드포인트"""

from fastapi import APIRouter, HTTPException

from pithub.api.services.github import GitHubService

router = APIRouter()


@router.get("/{owner}/{repo}")
async def list_features(owner: str, repo: str):
    """
    GitHub repo의 Feature 목록 조회

    예: GET /api/features/changmin/pit
    """
    github = GitHubService()

    features = await github.list_features(owner, repo)
    return {
        "owner": owner,
        "repo": repo,
        "features": features,
    }


@router.get("/{owner}/{repo}/{feature_id}")
async def get_feature(owner: str, repo: str, feature_id: str):
    """
    특정 Feature 상세 조회

    예: GET /api/features/changmin/pit/F-0001
    """
    github = GitHubService()

    feature = await github.get_feature(owner, repo, feature_id)
    if not feature:
        raise HTTPException(
            status_code=404,
            detail=f"Feature를 찾을 수 없습니다: {feature_id}"
        )

    return {
        "owner": owner,
        "repo": repo,
        "feature": feature,
    }
