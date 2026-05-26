import asyncio
import logging
import os
import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text

from app.crawlers import wanted, catch, linkareer, groupby, jasoseol
from app.db.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

_RETRYABLE_DB_ERRORS = ("starting up", "connection refused", "the database system", "cannot connect now")


async def _wait_for_db(timeout: int = 300) -> bool:
    """DB가 응답할 때까지 최대 timeout초 대기. 성공하면 True, 시간 초과면 False."""
    deadline = time.monotonic() + timeout
    attempt = 0
    while time.monotonic() < deadline:
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
            if attempt > 0:
                logger.info(f"[DB] {attempt}회 재시도 후 연결 성공")
            return True
        except Exception as e:
            attempt += 1
            wait = min(10, 2 * attempt)
            logger.warning(f"[DB] 연결 대기 중 ({attempt}회, {wait}초 후 재시도): {e}")
            await asyncio.sleep(wait)
    logger.error(f"[DB] {timeout}초 내 연결 실패 — 크롤링 중단")
    return False


async def _db_keepalive():
    """Railway PostgreSQL 슬립 방지용 주기적 ping."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        logger.warning(f"[keepalive] DB ping 실패: {e}")


async def _self_ping():
    """Railway 컨테이너 슬립 방지용 자가 HTTP ping."""
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

_CRAWLERS = [
    ("wanted", wanted.crawl_wanted),
    ("catch", catch.crawl_catch),
    ("linkareer", linkareer.crawl_linkareer),
    ("groupby", groupby.crawl_groupby),
    ("jasoseol", jasoseol.crawl_jasoseol),
]

_MAX_CRAWLER_RETRIES = 2
_CRAWLER_RETRY_DELAY = 60


async def run_all_crawlers():
    """5개 크롤러 순차 실행.
    크롤러 시작 전 DB 연결을 먼저 확인하여 브라우저 낭비를 방지.
    """
    run_start = time.monotonic()
    logger.info("=" * 60)
    logger.info("크롤링 전체 시작 — DB 연결 확인 중...")
    logger.info("=" * 60)

    if not await _wait_for_db(timeout=300):
        logger.error("크롤링 취소: DB 연결 불가")
        return

    logger.info("DB 연결 확인 완료 — 크롤링 시작")

    results = {}

    for name, fn in _CRAWLERS:
        for attempt in range(1, _MAX_CRAWLER_RETRIES + 2):
            try:
                logger.info(f"┌─ [{name}] 시작" + (f" (재시도 {attempt}/{_MAX_CRAWLER_RETRIES + 1})" if attempt > 1 else ""))
                t0 = time.monotonic()
                await fn()
                elapsed = time.monotonic() - t0
                logger.info(f"└─ [{name}] 완료 ({elapsed:.0f}초)")
                results[name] = "✓"
                break
            except Exception as e:
                elapsed = time.monotonic() - (t0 if 't0' in dir() else run_start)
                err = str(e).lower()
                is_db_err = any(msg in err for msg in _RETRYABLE_DB_ERRORS)

                if is_db_err:
                    # DB 오류는 브라우저 재시작 없이 DB 복구 대기 후 재시도
                    logger.warning(f"└─ [{name}] DB 오류 — 복구 대기: {e}")
                    if await _wait_for_db(timeout=300):
                        logger.info(f"[{name}] DB 복구 확인 — 재시도")
                        continue
                    else:
                        logger.error(f"└─ [{name}] DB 복구 실패 — 건너뜀")
                        results[name] = "✗(DB)"
                        break
                elif attempt <= _MAX_CRAWLER_RETRIES:
                    logger.warning(
                        f"└─ [{name}] 실패 (시도 {attempt}/{_MAX_CRAWLER_RETRIES + 1}), "
                        f"{_CRAWLER_RETRY_DELAY}초 후 재시도: {type(e).__name__}: {e}"
                    )
                    await asyncio.sleep(_CRAWLER_RETRY_DELAY)
                else:
                    logger.error(f"└─ [{name}] 최종 실패: {type(e).__name__}: {e}")
                    results[name] = "✗"
                    break

    total_elapsed = time.monotonic() - run_start
    logger.info("=" * 60)
    status_str = "  ".join(f"{n}:{s}" for n, s in results.items())
    logger.info(f"크롤링 전체 완료 ({total_elapsed:.0f}초)  {status_str}")
    logger.info("=" * 60)


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

    scheduler.add_job(
        _db_keepalive,
        "interval",
        minutes=5,
        id="db_keepalive",
        max_instances=1,
    )

    scheduler.add_job(
        _self_ping,
        "interval",
        minutes=4,
        id="self_ping",
        max_instances=1,
    )

    scheduler.add_job(
        run_all_crawlers,
        CronTrigger(day_of_week="mon-fri", hour="10,12,14,16,18,20", minute=0),
        id="all_crawlers",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )

    scheduler.add_job(
        run_cleanup,
        CronTrigger(day_of_week="mon", hour=9, minute=0),
        id="cleanup_stale",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    logger.info(
        "스케줄러 시작됨 | 크롤링: 평일 10/12/14/16/18/20시 | "
        "정리: 매주 월 09:00 | self-ping: 4분 | DB ping: 5분"
    )
    return scheduler
