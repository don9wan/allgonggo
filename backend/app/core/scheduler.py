import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="Asia/Seoul")


async def run_all_crawlers():
    logger.info("크롤링 시작")
    try:
        from app.crawlers.wanted import crawl_wanted
        await crawl_wanted()
        logger.info("원티드 크롤링 완료")
    except Exception as e:
        logger.error(f"크롤링 오류: {e}")


def start_scheduler():
    for hour in [10, 12, 14, 16, 18]:
        scheduler.add_job(
            run_all_crawlers,
            trigger=CronTrigger(hour=hour, minute=0, timezone="Asia/Seoul"),
            id=f"crawl_{hour}",
            replace_existing=True,
        )
    scheduler.start()
    logger.info("스케줄러 시작됨 (10:00, 12:00, 14:00, 16:00, 18:00 KST)")


def stop_scheduler():
    scheduler.shutdown()
