import asyncio
import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text

from app.crawlers import wanted, catch, linkareer, groupby, jasoseol
from app.db.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

_RETRYABLE_ERRORS = ("starting up", "connection refused", "the database system", "cannot connect now")


async def _run_with_retry(name: str, fn, retries: int = 5, base_delay: int = 15):
    """DB 연결 실패 시 지수 백오프로 재시도 (15→30→60→120→240초)."""
    for attempt in range(retries + 1):
        try:
            await fn()
            return
        except Exception as e:
            err = str(e).lower()
            is_retryable = any(msg in err for msg in _RETRYABLE_ERRORS)
            if attempt < retries and is_retryable:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"[{name}] DB 연결 실패, {delay}초 후 재시도 ({attempt + 1}/{retries}): {e}")
                await asyncio.sleep(delay)
            else:
                raise


async def _db_keepalive():
    """Railway PostgreSQL 슬립 방지용 주기적 ping."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        logger.warning(f"[keepalive] DB ping 실패: {e}")


async def _self_ping():
    """Railway 컨테이너 슬립 방지용 자가 HTTP ping.
    RAILWAY_PUBLIC_DOMAIN 환경변수가 없으면(로컬 실행) 무시.
    외부 인바운드 요청처럼 처리되어 Railway가 서비스를 깨워 둠.
    """
    domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if not domain:
        return
    import aiohttp
    url = f"https://{domain}/health"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)):
                pass
    except Exception as e:
        logger.warning(f"[self-ping] 실패: {e}")


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

    # Railway PostgreSQL 슬립 방지 — 5분마다 ping
    scheduler.add_job(
        _db_keepalive,
        "interval",
        minutes=5,
        id="db_keepalive",
        max_instances=1,
    )

    # Railway 컨테이너 슬립 방지 — 4분마다 자가 HTTP ping
    scheduler.add_job(
        _self_ping,
        "interval",
        minutes=4,
        id="self_ping",
        max_instances=1,
    )

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
    logger.info("스케줄러 시작됨 (평일 10/12/14/16/18/20시 크롤링 / 매주 월 09:00 정리 / 4분마다 self-ping)")
    return scheduler
