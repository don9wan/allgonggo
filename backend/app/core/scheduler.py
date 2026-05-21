import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="Asia/Seoul")


async def run_all_crawlers():
    logger.info("전체 크롤링 시작")

    crawlers = [
        ("원티드", "app.crawlers.wanted", "crawl_wanted"),
        ("점핏", "app.crawlers.jumpit", "crawl_jumpit"),
        ("프로그래머스", "app.crawlers.programmers", "crawl_programmers"),
        ("캐치", "app.crawlers.catch", "crawl_catch"),
        ("그룹바이", "app.crawlers.groupby", "crawl_groupby"),
    ]

    for name, module_path, func_name in crawlers:
        try:
            import importlib
            module = importlib.import_module(module_path)
            func = getattr(module, func_name)
            await func()
            logger.info(f"{name} 크롤링 완료")
        except Exception as e:
            logger.error(f"{name} 크롤링 실패: {e}")


def start_scheduler():
    for hour in [10, 12, 14, 16, 18]:
        scheduler.add_job(
            run_all_crawlers,
            trigger=CronTrigger(hour=hour, minute=0, timezone="Asia/Seoul"),
            id=f"crawl_{hour}",
            replace_existing=True,
        )
    scheduler.start()
    logger.info("스케줄러 시작됨 (10:00 / 12:00 / 14:00 / 16:00 / 18:00 KST)")


def stop_scheduler():
    scheduler.shutdown()
