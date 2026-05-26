import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.crawlers import wanted, catch, linkareer, groupby, jasoseol

logger = logging.getLogger(__name__)


async def _run_with_retry(name: str, fn, retries: int = 2, delay: int = 15):
    """DB 시작 중 오류 시 재시도."""
    for attempt in range(retries + 1):
        try:
            await fn()
            return
        except Exception as e:
            if attempt < retries and "starting up" in str(e).lower():
                logger.warning(f"[{name}] DB 시작 중, {delay}초 후 재시도 ({attempt + 1}/{retries})")
                await asyncio.sleep(delay)
            else:
                raise


SOURCES = ["wanted", "linkareer", "jasoseol", "catch", "groupby"]


async def run_all_crawlers():
    """5개 크롤러 순차 실행. 한 사이트 실패해도 다른 사이트 계속 진행."""
    crawlers = [
        ("wanted", wanted.crawl_wanted),
        ("catch", catch.crawl_catch),
        ("linkareer", linkareer.crawl_linkareer),
        ("groupby", groupby.crawl_groupby),
        ("jasoseol", jasoseol.crawl_jasoseol),
    ]
    for name, fn in crawlers:
        try:
            logger.info(f"[{name}] 시작")
            await _run_with_retry(name, fn)
            logger.info(f"[{name}] 완료")
        except Exception as e:
            logger.exception(f"[{name}] 실패: {e}")
            continue


async def run_cleanup():
    """마감 공고 비활성화. 30일 이상 확인되지 않은 공고를 is_active=False 처리."""
    from app.crawlers.db_writer import deactivate_stale_jobs
    from app.db.database import AsyncSessionLocal

    total = 0
    for source in SOURCES:
        try:
            async with AsyncSessionLocal() as session:
                n = await deactivate_stale_jobs(session, source, days=30)
                total += n
        except Exception as e:
            logger.exception(f"[cleanup/{source}] 실패: {e}")

    logger.info(f"마감 공고 정리 완료: 총 {total}건 비활성화")


def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Seoul")

    # 평일(월-금) 10/12/14/16/18/20시 크롤링
    scheduler.add_job(
        run_all_crawlers,
        CronTrigger(day_of_week="mon-fri", hour="10,12,14,16,18,20", minute=0),
        id="all_crawlers",
        max_instances=1,
        coalesce=True,
    )

    # 매주 월요일 09:00 KST 마감 공고 정리
    scheduler.add_job(
        run_cleanup,
        CronTrigger(day_of_week="mon", hour=9, minute=0),
        id="cleanup_stale",
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    logger.info("스케줄러 시작됨 (평일 10/12/14/16/18/20시 크롤링 / 매주 월 09:00 정리)")
    return scheduler
