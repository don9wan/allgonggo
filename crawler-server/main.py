import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, BackgroundTasks

from scheduler import start_scheduler, run_all_crawlers
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = start_scheduler()
    yield
    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/trigger")
async def trigger_crawl(
    background_tasks: BackgroundTasks,
    x_trigger_token: str = Header(None),
):
    """GitHub Actions 등 외부 스케줄러에서 크롤링을 직접 트리거하는 엔드포인트.
    CRAWL_SECRET 환경변수가 설정된 경우 토큰 검증 필수.
    """
    if settings.CRAWL_SECRET and x_trigger_token != settings.CRAWL_SECRET:
        raise HTTPException(status_code=403, detail="Invalid trigger token")

    background_tasks.add_task(run_all_crawlers)
    return {"status": "started", "message": "크롤링이 백그라운드에서 시작됩니다"}
