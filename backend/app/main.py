import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.scheduler import start_scheduler, stop_scheduler
from app.api import jobs

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        start_scheduler()
    except Exception as e:
        logger.error(f"스케줄러 시작 실패: {e}")
    yield
    try:
        stop_scheduler()
    except Exception:
        pass


app = FastAPI(
    title="올공고 API",
    description="IT 채용공고 통합 탐색 서비스 API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/db")
async def health_db():
    """DB 연결 상태 확인 (디버깅용)."""
    from sqlalchemy import text
    from app.db.database import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return {"status": "error", "db": str(e)}
