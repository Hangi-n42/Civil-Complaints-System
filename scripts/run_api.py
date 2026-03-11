"""
FastAPI 서버 실행 스크립트

Usage:
    python scripts/run_api.py
"""

import sys
import uvicorn
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.config import settings

if __name__ == "__main__":
    print(f"🚀 API 서버 시작...")
    print(f"   Host: {settings.API_HOST}")
    print(f"   Port: {settings.API_PORT}")
    print(f"   Model: {settings.OLLAMA_MODEL}")
    print(f"   ChromaDB: {settings.CHROMA_DB_PATH}")

    uvicorn.run(
        "app.api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
