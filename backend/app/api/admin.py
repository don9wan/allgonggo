import asyncio
import logging
from fastapi import APIRouter, Header, HTTPException

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


@router.post("/crawl")
async def trigger_crawl(x_admin_key: str = Header(...)):
    from app.core.config import settings
    if x_admin_key != settings.ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")

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
