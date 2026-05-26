import asyncio
import logging
import random
from contextlib import asynccontextmanager

from cloakbrowser import launch_async, launch_context_async

logger = logging.getLogger(__name__)

# Docker 컨테이너에서 /dev/shm이 64MB로 제한됨 → /tmp로 우회
_EXTRA_ARGS = ["--disable-dev-shm-usage"]


async def launch_browser():
    """크롤러 공통 브라우저 실행. Docker 환경 호환 플래그 포함."""
    return await launch_async(headless=True, humanize=True, args=_EXTRA_ARGS)


@asynccontextmanager
async def new_context():
    """CloakBrowser BrowserContext를 열고 닫는 공통 헬퍼."""
    context = await launch_context_async(headless=True, humanize=True, args=_EXTRA_ARGS)
    try:
        yield context
    finally:
        await context.close()


async def random_delay():
    """요청 간 랜덤 딜레이 (2~5초)."""
    await asyncio.sleep(random.uniform(2, 5))
