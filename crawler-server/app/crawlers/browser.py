import asyncio
import logging
import random
from contextlib import asynccontextmanager

from cloakbrowser import launch_async, launch_context_async

logger = logging.getLogger(__name__)


@asynccontextmanager
async def new_context():
    """CloakBrowser BrowserContext를 열고 닫는 공통 헬퍼."""
    context = await launch_context_async(headless=True, humanize=True)
    try:
        yield context
    finally:
        await context.close()


async def random_delay():
    """요청 간 랜덤 딜레이 (2~5초)."""
    await asyncio.sleep(random.uniform(2, 5))
