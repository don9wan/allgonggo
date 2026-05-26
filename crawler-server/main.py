import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, BackgroundTasks

from scheduler import start_scheduler, run_all_crawlers
from app.core.config import settings
from app.state import get_status

_crawl_lock = asyncio.Lock()

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


@app.get("/status")
async def status():
    """현재 크롤 상태 조회 — Railway 로그 없이도 상태 파악 가능."""
    return get_status()


@app.post("/trigger")
async def trigger_crawl(
    background_tasks: BackgroundTasks,
    x_trigger_token: str = Header(None),
):
    """GitHub Actions 등 외부 스케줄러에서 크롤링을 직접 트리거하는 엔드포인트."""
    valid_tokens = {t for t in [settings.CRAWL_SECRET, settings.ADMIN_KEY] if t}
    if valid_tokens and x_trigger_token not in valid_tokens:
        raise HTTPException(status_code=403, detail="Invalid trigger token")

    if _crawl_lock.locked():
        return {"status": "skipped", "message": "이미 크롤링이 진행 중입니다"}

    async def _locked_crawl():
        async with _crawl_lock:
            await run_all_crawlers()

    background_tasks.add_task(_locked_crawl)
    return {"status": "started", "message": "크롤링이 백그라운드에서 시작됩니다"}
