import logging
from typing import List
from app.crawlers.base import RawJob

logger = logging.getLogger(__name__)

# jumpit.saramin.co.kr/api/positions returns HTTP 307 → / for all non-browser clients.
# The site uses Next.js RSC and requires a valid browser session to serve API data.
# Crawling is not feasible without a headless browser.


async def crawl_jumpit() -> List[RawJob]:
    logger.warning("점핏 크롤러 비활성화: API가 브라우저 세션 없이는 307 리다이렉트를 반환함")
    return []
