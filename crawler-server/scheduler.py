import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.crawlers import wanted, catch, linkareer, groupby, jasoseol

logger = logging.getLogger(__name__)


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
            await fn()
            logger.info(f"[{name}] 완료")
        except Exception as e:
            logger.exception(f"[{name}] 실패: {e}")
            continue


def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
    # 평일(월-금) 10/12/14/16/18/20시
    scheduler.add_job(
        run_all_crawlers,
        CronTrigger(day_of_week="mon-fri", hour="10,12,14,16,18,20", minute=0),
        id="all_crawlers",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("스케줄러 시작됨 (평일 10/12/14/16/18/20시 KST)")
    return scheduler
