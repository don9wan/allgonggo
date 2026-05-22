import logging
from typing import List
from app.crawlers.base import RawJob

logger = logging.getLogger(__name__)

# groupby.kr/api/v1/jobs redirects (308) then returns HTML (Next.js SSR).
# There is no public JSON API endpoint accessible without a browser session.


async def crawl_groupby() -> List[RawJob]:
    logger.warning("그룹바이 크롤러 비활성화: 공개 JSON API가 없음 (Next.js SSR 전용)")
    return []
