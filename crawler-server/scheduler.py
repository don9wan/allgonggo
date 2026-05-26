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


async def _run_with_db_retry(name: str, fn, retries: int = 5, base_delay: int = 15):
    """DB 연결 실패 시 지수 백오프로 재시도 (15→30→60→120→240초)."""
    for attempt in range(retries + 1):
        try:
            await fn()
            return
        except Exception as e:
            err = str(e).lower()
            is_db_err = any(msg in err for msg in _RETRYABLE_DB_ERRORS)
            if attempt < retries and is_db_err:
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
    RAILWAY_PUBLIC_DOMAIN 환경변수가 없는 로컬 환경에서는 무시.
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

_CRAWLERS = [
    ("wanted", wanted.crawl_wanted),
    ("catch", catch.crawl_catch),
    ("linkareer", linkareer.crawl_linkareer),
    ("groupby", groupby.crawl_groupby),
    ("jasoseol", jasoseol.crawl_jasoseol),
]

_MAX_CRAWLER_RETRIES = 2   # 크롤러 실패 시 최대 재시도 횟수
_CRAWLER_RETRY_DELAY = 60  # 재시도 간격(초) — 브라우저 재기동 여유


async def run_all_crawlers():
    """5개 크롤러 순차 실행.
    - DB 연결 오류: 지수 백오프 재시도 (최대 5회)
    - 브라우저/네트워크 오류: 60초 간격 재시도 (최대 2회)
    - 한 사이트 최종 실패해도 다른 사이트 계속 진행
    """
    run_start = time.monotonic()
    logger.info("=" * 60)
    logger.info("크롤링 전체 시작")
    logger.info("=" * 60)

    results = {}

    for name, fn in _CRAWLERS:
        for attempt in range(1, _MAX_CRAWLER_RETRIES + 2):  # 1, 2, 3
            try:
                logger.info(f"┌─ [{name}] 시작" + (f" (재시도 {attempt}/{_MAX_CRAWLER_RETRIES + 1})" if attempt > 1 else ""))
                t0 = time.monotonic()
                await _run_with_db_retry(name, fn)
                elapsed = time.monotonic() - t0
                logger.info(f"└─ [{name}] 완료 ({elapsed:.0f}초)")
                results[name] = "✓"
                break
            except Exception as e:
                elapsed = time.monotonic() - t0 if 'T0' in dir() else 0
                if attempt <= _MAX_CRAWLER_RETRIES:
                    logger.warning(
                        f"└─ [{name}] 실패 (시도 {attempt}/{_MAX_CRAWLER_RETRIES + 1}), "
                        f"{_CRAWLER_RETRY_DELAY}초 후 재시도: {type(e).__name__}: {e}"
                    )
                    await asyncio.sleep(_CRAWLER_RETRY_DELAY)
                else:
                    logger.error(f"└─ [{name}] 최종 실패 ({attempt}회 모두 실패): {type(e).__name__}: {e}")
                    results[name] = "✗"

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
    # misfire_grace_time=3600: 컨테이너 재시작 등으로 놓친 실행을 1시간 내에 보정 실행
    scheduler.add_job(
        run_all_crawlers,
        CronTrigger(day_of_week="mon-fri", hour="10,12,14,16,18,20", minute=0),
        id="all_crawlers",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )

    # 매주 월요일 09:00 KST 마감 공고 정리
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
        "스케줄러 시작됨 | 크롤링: 평일 10/12/14/16/18/20시 (misfire 1h 보정) | "
        "정리: 매주 월 09:00 | self-ping: 4분 | DB ping: 5분"
    )
    return scheduler
