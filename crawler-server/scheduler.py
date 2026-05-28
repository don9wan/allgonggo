import asyncio
import logging
import os
import sys
import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text

from app.crawlers import wanted, catch, linkareer, groupby, jasoseol
from app.db.database import AsyncSessionLocal
from app.state import (
    get_status, mark_db_fail, mark_db_ok,
    mark_run_end, mark_run_start, mark_source_start,
)

logger = logging.getLogger(__name__)

_RETRYABLE_DB_ERRORS = ("starting up", "connection refused", "the database system", "cannot connect now")


def _masked_db_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if "://" in url and "@" in url:
        scheme_user, rest = url.split("@", 1)
        return f"{scheme_user.rsplit(':', 1)[0]}:***@{rest}"
    return url or "(DATABASE_URL 없음)"


def _log_startup_info() -> None:
    try:
        import psutil
        mem = psutil.Process().memory_info().rss // 1024 // 1024
        mem_str = f"{mem} MB"
    except ImportError:
        mem_str = "(psutil 없음)"

    logger.info("=" * 60)
    logger.info("[startup] Python %s", sys.version.split()[0])
    logger.info("[startup] DB URL: %s", _masked_db_url())
    logger.info("[startup] RAILWAY_ENVIRONMENT: %s", os.getenv("RAILWAY_ENVIRONMENT", "(없음)"))
    logger.info("[startup] RAILWAY_PUBLIC_DOMAIN: %s", os.getenv("RAILWAY_PUBLIC_DOMAIN", "(없음)"))
    logger.info("[startup] 메모리: %s", mem_str)
    logger.info("=" * 60)


async def _wait_for_db(timeout: int = 1200) -> bool:
    """DB가 응답할 때까지 최대 timeout초 대기. 10분마다 경과 로그."""
    deadline = time.monotonic() + timeout
    attempt = 0
    next_progress_log = time.monotonic() + 120  # 2분마다 진행상황 로그

    while time.monotonic() < deadline:
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
            mark_db_ok()
            if attempt > 0:
                waited = round(time.monotonic() - (deadline - timeout))
                logger.info("[DB] %d회 시도 / %d초 대기 후 연결 성공", attempt, waited)
            return True
        except Exception as e:
            mark_db_fail()
            attempt += 1
            wait = min(10, 2 * attempt)
            err_type = type(e).__name__
            logger.warning("[DB] 연결 대기 중 (%d회, %d초 후 재시도) [%s]: %s", attempt, wait, err_type, e)

            # 2분마다 "아직 기다리는 중" 요약 로그
            if time.monotonic() >= next_progress_log:
                elapsed = round(time.monotonic() - (deadline - timeout))
                remaining = round(deadline - time.monotonic())
                logger.info("[DB] 대기 경과 %d초, 남은 시간 %d초 (timeout=%d)", elapsed, remaining, timeout)
                next_progress_log = time.monotonic() + 120

            await asyncio.sleep(wait)

    logger.error("[DB] %d초 내 연결 실패 — 크롤링 중단 (총 %d회 시도)", timeout, attempt)
    return False


async def _db_keepalive():
    """Railway PostgreSQL 슬립 방지용 주기적 ping."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        mark_db_ok()
    except Exception as e:
        mark_db_fail()
        logger.warning("[keepalive] DB ping 실패 [%s]: %s", type(e).__name__, e)


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
        logger.warning("[self-ping] 실패 [%s]: %s", type(e).__name__, e)


async def _crawl_heartbeat(source: str, t0: float) -> None:
    """크롤러 실행 중 2분마다 생존 로그."""
    while True:
        await asyncio.sleep(120)
        elapsed = round(time.monotonic() - t0)
        try:
            import psutil
            mem = psutil.Process().memory_info().rss // 1024 // 1024
            mem_str = f" | 메모리 {mem} MB"
        except ImportError:
            mem_str = ""
        logger.info("[heartbeat] [%s] 실행 중 %d초 경과%s", source, elapsed, mem_str)


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


async def _count_source(source: str) -> int:
    try:
        async with AsyncSessionLocal() as session:
            r = await session.execute(
                text("SELECT COUNT(*) FROM job_sources WHERE source = :s"),
                {"s": source},
            )
            return r.scalar() or 0
    except Exception:
        return -1


async def run_all_crawlers():
    """5개 크롤러 순차 실행."""
    run_start = time.monotonic()
    mark_run_start()

    logger.info("=" * 60)
    logger.info("크롤링 전체 시작 — DB 연결 확인 중...")
    logger.info("=" * 60)

    if not await _wait_for_db():
        logger.error("크롤링 취소: DB 연결 불가")
        mark_run_end({})
        return

    logger.info("DB 연결 확인 완료 — 크롤링 시작")

    results = {}

    for name, fn in _CRAWLERS:
        mark_source_start(name)
        count_before = await _count_source(name)

        for attempt in range(1, _MAX_CRAWLER_RETRIES + 2):
            t0 = time.monotonic()
            heartbeat = asyncio.create_task(_crawl_heartbeat(name, t0))
            try:
                logger.info("┌─ [%s] 시작%s", name,
                            f" (재시도 {attempt}/{_MAX_CRAWLER_RETRIES + 1})" if attempt > 1 else "")
                await fn()
                elapsed = time.monotonic() - t0
                heartbeat.cancel()

                # 실제 수집 건수 비교
                count_after = await _count_source(name)
                delta = count_after - count_before if count_before >= 0 else "?"
                if count_after == count_before and count_before >= 0:
                    logger.warning("└─ [%s] 완료 (%.0f초) — 신규 공고 0건 (사이트 변경/차단 의심)", name, elapsed)
                else:
                    logger.info("└─ [%s] 완료 (%.0f초) — DB %d → %d (+%s건)", name, elapsed, count_before, count_after, delta)

                results[name] = {"status": "✓", "delta": delta, "elapsed_s": round(elapsed)}
                break

            except Exception as e:
                elapsed = time.monotonic() - t0
                heartbeat.cancel()
                err = str(e).lower()
                is_db_err = any(msg in err for msg in _RETRYABLE_DB_ERRORS)

                if is_db_err:
                    logger.warning("└─ [%s] DB 오류 (%.0f초) — 복구 대기 [%s]: %s", name, elapsed, type(e).__name__, e)
                    if await _wait_for_db():
                        logger.info("[%s] DB 복구 확인 — 재시도", name)
                        continue
                    else:
                        logger.error("└─ [%s] DB 복구 실패 — 건너뜀", name)
                        results[name] = {"status": "✗(DB)", "error": str(e)}
                        break
                elif attempt <= _MAX_CRAWLER_RETRIES:
                    logger.warning(
                        "└─ [%s] 실패 (시도 %d/%d, %.0f초) — %ds 후 재시도 [%s]: %s",
                        name, attempt, _MAX_CRAWLER_RETRIES + 1, elapsed,
                        _CRAWLER_RETRY_DELAY, type(e).__name__, e,
                    )
                    await asyncio.sleep(_CRAWLER_RETRY_DELAY)
                else:
                    logger.error("└─ [%s] 최종 실패 (%.0f초) [%s]: %s", name, elapsed, type(e).__name__, e)
                    results[name] = {"status": "✗", "error": f"{type(e).__name__}: {e}"}
                    break

    total_elapsed = time.monotonic() - run_start
    mark_run_end(results)

    logger.info("=" * 60)
    summary = "  ".join(
        f"{n}:{r['status']}({r.get('delta', '?')}건)" if r.get("status") == "✓"
        else f"{n}:{r['status']}"
        for n, r in results.items()
    )
    logger.info("크롤링 전체 완료 (%.0f초)  %s", total_elapsed, summary)
    logger.info("=" * 60)


async def run_cleanup():
    """마감 공고 비활성화. 28일 이상 확인되지 않은 공고를 is_active=False 처리."""
    from app.crawlers.db_writer import deactivate_stale_jobs

    total = 0
    for source in SOURCES:
        try:
            async with AsyncSessionLocal() as session:
                n = await deactivate_stale_jobs(session, source, days=28)
                total += n
        except Exception as e:
            logger.exception("[cleanup/%s] 실패: %s", source, e)

    logger.info("마감 공고 정리 완료: 총 %d건 비활성화", total)


def start_scheduler() -> AsyncIOScheduler:
    _log_startup_info()

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
