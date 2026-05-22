import asyncio
import logging
import httpx
from fastapi import APIRouter, Header, HTTPException

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


def _check_key(key: str):
    from app.core.config import settings
    if key != settings.ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/crawl")
async def trigger_crawl(x_admin_key: str = Header(...)):
    _check_key(x_admin_key)

    async def run():
        from app.crawlers.wanted import crawl_wanted
        from app.crawlers.jumpit import crawl_jumpit
        from app.crawlers.programmers import crawl_programmers
        from app.crawlers.catch import crawl_catch
        from app.crawlers.groupby import crawl_groupby
        for name, fn in [
            ("wanted", crawl_wanted),
            ("jumpit", crawl_jumpit),
            ("programmers", crawl_programmers),
            ("catch", crawl_catch),
            ("groupby", crawl_groupby),
        ]:
            try:
                await fn()
                logger.info(f"{name} 완료")
            except Exception as e:
                logger.error(f"{name} 실패: {e}")

    asyncio.create_task(run())
    return {"status": "started"}


@router.get("/debug/wanted")
async def debug_wanted(x_admin_key: str = Header(...)):
    """원티드 API 1페이지 원본 응답 확인용."""
    _check_key(x_admin_key)

    url = "https://www.wanted.co.kr/api/chaos/jobs/v1/wanted"
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://www.wanted.co.kr/",
        "Wanted-User-Agent": "user-web",
    }
    params = {
        "country": "kr",
        "tag_type_ids": "518,655,660",
        "limit": 5,
        "offset": 0,
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, headers=headers, timeout=15)
            return {
                "status_code": resp.status_code,
                "content_type": resp.headers.get("content-type"),
                "body_preview": resp.text[:2000],
            }
    except Exception as e:
        return {"error": str(e)}


@router.get("/debug/db")
async def debug_db(x_admin_key: str = Header(...)):
    """DB 공고 수 확인용."""
    _check_key(x_admin_key)
    from sqlalchemy import text, select, func
    from app.db.database import AsyncSessionLocal
    from app.models.job import Job, JobSource
    async with AsyncSessionLocal() as session:
        job_count = (await session.execute(select(func.count()).select_from(Job))).scalar()
        source_count = (await session.execute(select(func.count()).select_from(JobSource))).scalar()
        return {"jobs": job_count, "job_sources": source_count}
