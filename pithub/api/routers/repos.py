"""GitHub repo 관련 엔드포인트"""

from fastapi import APIRouter, HTTPException

from pithub.api.services.github import GitHubService

router = APIRouter()


@router.get("/{owner}/{repo}")
async def get_repo_info(owner: str, repo: str):
    """
    GitHub repo의 .pit/ 정보 조회

    예: GET /api/repos/changmin/pit
    """
    github = GitHubService()

    # .pit/config.yaml 읽기
    config = await github.get_pit_config(owner, repo)
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f".pit/ 폴더를 찾을 수 없습니다: {owner}/{repo}"
        )

    return {
        "owner": owner,
        "repo": repo,
        "config": config,
    }


@router.get("/{owner}/{repo}/summary")
async def get_repo_summary(owner: str, repo: str):
    """
    GitHub repo의 .pit/ 요약 정보

    - 프로젝트 정보
    - Feature 개수 및 상태별 분포
    - Decision 개수
    """
    github = GitHubService()

    config = await github.get_pit_config(owner, repo)
    if not config:
        raise HTTPException(status_code=404, detail=".pit/ 폴더를 찾을 수 없습니다")

    features = await github.list_features(owner, repo)
    decisions = await github.list_decisions(owner, repo)

    # 상태별 분류
    status_counts = {}
    for f in features:
        status = f.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "project": config,
        "features": {
            "total": len(features),
            "by_status": status_counts,
        },
        "decisions": {
            "total": len(decisions),
        },
    }
