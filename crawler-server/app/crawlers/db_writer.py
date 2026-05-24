import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

from sqlalchemy import select, func, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawlers.base import RawJob
from app.models.job import Job, JobSource

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.8
CATCHUP_RATIO = 0.70


async def already_seen_ratio(session: AsyncSession, urls: List[str]) -> float:
    if not urls:
        return 0.0
    result = await session.execute(
        select(func.count()).select_from(JobSource).where(JobSource.url.in_(urls))
    )
    known = result.scalar_one()
    return known / len(urls)


async def is_caught_up(session: AsyncSession, page_jobs: List[RawJob]) -> bool:
    if not page_jobs:
        return False
    urls = [j.url for j in page_jobs]
    ratio = await already_seen_ratio(session, urls)
    if ratio >= CATCHUP_RATIO:
        logger.info(f"기존 URL 비율 {ratio:.0%} ≥ {CATCHUP_RATIO:.0%} → 페이지네이션 조기 종료")
        return True
    return False


async def deactivate_stale_jobs(session: AsyncSession, source: str, days: int = 30) -> int:
    """
    특정 소스에서 days일 이상 확인되지 않은 공고를 비활성화.
    다른 소스에서 여전히 최근에 확인된 공고는 제외.
    """
    threshold = datetime.now(timezone.utc) - timedelta(days=days)

    stale_result = await session.execute(
        select(JobSource.job_id)
        .where(JobSource.source == source)
        .where(JobSource.crawled_at < threshold)
    )
    stale_job_ids = [row[0] for row in stale_result]

    if not stale_job_ids:
        return 0

    # 다른 소스에서 여전히 fresh한 job은 제외
    fresh_result = await session.execute(
        select(JobSource.job_id.distinct())
        .where(JobSource.job_id.in_(stale_job_ids))
        .where(JobSource.crawled_at >= threshold)
    )
    fresh_job_ids = {row[0] for row in fresh_result}

    to_deactivate = [jid for jid in stale_job_ids if jid not in fresh_job_ids]
    if not to_deactivate:
        return 0

    await session.execute(
        update(Job)
        .where(Job.id.in_(to_deactivate))
        .where(Job.is_active == True)
        .values(is_active=False, updated_at=datetime.now(timezone.utc))
    )
    await session.commit()
    logger.info(f"[{source}] 마감 공고 비활성화: {len(to_deactivate)}건 ({days}일 미확인)")
    return len(to_deactivate)


async def upsert_jobs(session: AsyncSession, raw_jobs: List[RawJob]) -> Tuple[int, int]:
    """
    공고 목록을 DB에 upsert.

    메모리 최적화: existing_urls와 source_keys를 호출 소스 단위로만 로드.
    staleness 추적: 기존 URL은 crawled_at을 갱신하여 마지막 확인일 기록.
    중복 감지: pg_trgm similarity(≥0.8)로 동일 공고의 교차 소스 링크.
    """
    if not raw_jobs:
        return 0, 0

    source = raw_jobs[0].source

    # ── 1. 기존 데이터 메모리 로드 (소스 단위 필터링으로 메모리 절약) ──
    existing_urls: set[str] = {
        row[0]
        for row in (await session.execute(
            select(JobSource.url).where(JobSource.source == source)
        )).all()
    }

    existing_jobs_list = (
        await session.execute(select(Job).where(Job.is_active == True))
    ).scalars().all()

    jobs_by_company: dict[str, list] = {}
    for job in existing_jobs_list:
        jobs_by_company.setdefault(job.company.lower(), []).append(job)

    existing_source_keys: set[tuple] = {
        (str(row[0]), row[1])
        for row in (await session.execute(
            select(JobSource.job_id, JobSource.source).where(JobSource.source == source)
        )).all()
    }
    # ─────────────────────────────────────────────────────────────────────

    inserted = linked = 0
    seen_existing_urls: list[str] = []
    BATCH_SIZE = 200

    for i, raw in enumerate(raw_jobs):
        if not raw.title or not raw.company:
            continue
        if raw.url in existing_urls:
            # 이미 알고 있는 URL → crawled_at 갱신 대상으로만 기록
            seen_existing_urls.append(raw.url)
            continue

        existing_urls.add(raw.url)

        candidates = jobs_by_company.get(raw.company.lower(), [])

        matched_job = None
        for candidate in candidates:
            sim = (await session.execute(
                text("SELECT similarity(:a, :b)"),
                {"a": raw.title, "b": candidate.title},
            )).scalar()
            if sim and sim >= SIMILARITY_THRESHOLD:
                matched_job = candidate
                break

        if matched_job:
            key = (str(matched_job.id), raw.source)
            if key not in existing_source_keys:
                session.add(JobSource(
                    job_id=matched_job.id,
                    source=raw.source,
                    url=raw.url,
                ))
                existing_source_keys.add(key)
                linked += 1
        else:
            new_id = uuid.uuid4()
            new_job = Job(
                id=new_id,
                title=raw.title,
                company=raw.company,
                location=raw.location,
                experience=raw.experience,
                employment_type=raw.employment_type,
                raw_text=raw.raw_text,
                is_active=True,
                crawled_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(new_job)
            session.add(JobSource(job_id=new_id, source=raw.source, url=raw.url))
            jobs_by_company.setdefault(raw.company.lower(), []).append(new_job)
            inserted += 1

        if (i + 1) % BATCH_SIZE == 0:
            await session.commit()
            logger.info(f"  중간 저장: {inserted}건 신규, {linked}건 링크 (진행 {i+1}/{len(raw_jobs)})")

    await session.commit()

    # 기존 URL crawled_at 일괄 갱신 (마지막 확인일 추적)
    if seen_existing_urls:
        await session.execute(
            update(JobSource)
            .where(JobSource.url.in_(seen_existing_urls))
            .values(crawled_at=datetime.now(timezone.utc))
        )
        await session.commit()
        logger.info(f"  기존 URL {len(seen_existing_urls)}건 갱신")

    logger.info(f"신규 공고: {inserted}건, 소스 추가: {linked}건")
    return inserted, linked
