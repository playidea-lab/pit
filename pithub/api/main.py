"""pithub API - GitHub repo의 .pit/ 폴더를 웹으로 제공하는 FastAPI 서버"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pithub.api.routers import decisions, features, repos

app = FastAPI(
    title="pithub API",
    description="GitHub repo의 .pit/ 폴더를 웹으로 시각화",
    version="0.1.0",
)

# CORS 설정 (Next.js 프론트엔드 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # 로컬 개발
        "https://pithub.io",      # 프로덕션
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(repos.router, prefix="/api/repos", tags=["repos"])
app.include_router(features.router, prefix="/api/features", tags=["features"])
app.include_router(decisions.router, prefix="/api/decisions", tags=["decisions"])


@app.get("/")
async def root():
    """API 상태 확인"""
    return {
        "service": "pithub",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    """헬스체크 엔드포인트"""
    return {"status": "healthy"}
