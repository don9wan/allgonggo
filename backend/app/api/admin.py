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
    """원티드 API 후보 URL들을 모두 시도해서 작동하는 것 찾기."""
    _check_key(x_admin_key)

    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://www.wanted.co.kr/",
        "Wanted-User-Agent": "user-web",
    }
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(
            "https://www.wanted.co.kr/api/v4/jobs",
            params={"country": "kr", "job_sort": "job.latest_order", "years": -1, "locations": "all", "limit": 3},
            headers=headers,
            timeout=10,
        )
        data = resp.json()
        jobs = data.get("data", [])
        return {
            "status": resp.status_code,
            "total": data.get("total", "?"),
            "links": data.get("links"),
            "first_job_keys": list(jobs[0].keys()) if jobs else [],
            "first_job": jobs[0] if jobs else {},
        }


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
