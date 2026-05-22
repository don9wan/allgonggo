import logging
from typing import List
from app.crawlers.base import RawJob

logger = logging.getLogger(__name__)

# career.programmers.co.kr is NXDOMAIN (globally, as of 2026-05).
# Programmers appears to have shut down or migrated their job board.


async def crawl_programmers() -> List[RawJob]:
    logger.warning("프로그래머스 크롤러 비활성화: career.programmers.co.kr 도메인이 존재하지 않음 (NXDOMAIN)")
    return []
