"""FastAPI 애플리케이션 진입점"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.logging import api_logger
from app.api.routers import generation_router, retrieval_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 생명주기 관리"""
    # 시작
    api_logger.info("API 서버 시작")
    api_logger.info(f"Ollama: {settings.OLLAMA_BASE_URL}")
    api_logger.info(f"ChromaDB: {settings.CHROMA_DB_PATH}")
    yield
    # 종료
    api_logger.info("API 서버 종료")


# FastAPI 애플리케이션 생성
app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.API_VERSION,
    lifespan=lifespan,
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터 등록
app.include_router(retrieval_router)
app.include_router(generation_router)


# 헬스 체크 엔드포인트
@app.get("/health")
async def health_check():
    """API 상태 확인"""
    return {
        "status": "ok",
        "service": settings.API_TITLE,
        "version": settings.API_VERSION,
    }


# 버전 헬스 체크 엔드포인트 (contract alias)
@app.get("/api/v1/health")
async def health_check_v1():
    """API v1 상태 확인"""
    return await health_check()


# 루트 엔드포인트
@app.get("/")
async def root():
    """API 정보"""
    return {
        "title": settings.API_TITLE,
        "description": settings.API_DESCRIPTION,
        "version": settings.API_VERSION,
        "docs_url": "/docs",
        "endpoints": {
            "health": "/api/v1/health",
            "health_legacy": "/health",
            "ingest": "/api/v1/ingest",
            "structure": "/api/v1/structure",
            "index": "/api/v1/index",
            "search": "/api/v1/search",
            "qa": "/api/v1/qa",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )
