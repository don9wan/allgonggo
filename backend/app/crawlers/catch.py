import logging
from typing import List
from app.crawlers.base import RawJob

logger = logging.getLogger(__name__)

# catch.co.kr/api/* returns HTTP 403 via Cloudflare WAF for all non-browser clients.
# Bypassing Cloudflare requires a headless browser with JS challenge solving.


async def crawl_catch() -> List[RawJob]:
    logger.warning("캐치 크롤러 비활성화: Cloudflare WAF가 모든 비-브라우저 요청을 403으로 차단함")
    return []
