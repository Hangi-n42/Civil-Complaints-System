"""라우터 패키지"""

from app.api.routers.admin import router as admin_router
from app.api.routers.chroma_debug import router as chroma_debug_router
from app.api.routers.complaint_intelligence import router as complaint_intelligence_router
from app.api.routers.generation import router as generation_router
from app.api.routers.retrieval import router as retrieval_router
from app.api.routers.structuring import router as structuring_router
from app.api.routers.ui import router as ui_router

__all__ = [
    "admin_router",
    "chroma_debug_router",
    "complaint_intelligence_router",
    "generation_router",
    "retrieval_router",
    "structuring_router",
    "ui_router",
]
