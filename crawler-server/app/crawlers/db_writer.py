import logging
import uuid
from datetime import datetime, timezone
from typing import List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from app.models.job import Job, JobSource
from app.crawlers.base import RawJob

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


async def upsert_jobs(session: AsyncSession, raw_jobs: List[RawJob]) -> Tuple[int, int]:
    """
    공고 목록을 DB에 upsert. 배치 최적화:
    - 시작 시 딱 3번 쿼리로 기존 데이터를 메모리에 로드
    - 이후 공고마다 DB 왕복 없이 in-memory로 중복 판단
    - pg_trgm similarity는 같은 회사가 이미 있을 때만 호출
    """
    if not raw_jobs:
        return 0, 0

    # ── 1. 기존 데이터 메모리 로드 (쿼리 3번) ──────────────────────────
    existing_urls: set[str] = {
        row[0]
        for row in (await session.execute(select(JobSource.url))).all()
    }

    existing_jobs_list = (
        await session.execute(select(Job).where(Job.is_active == True))
    ).scalars().all()

    # 회사명(소문자) → Job 목록 딕셔너리
    jobs_by_company: dict[str, list] = {}
    for job in existing_jobs_list:
        jobs_by_company.setdefault(job.company.lower(), []).append(job)

    # (job_id, source) 중복 링크 방지용 세트
    existing_source_keys: set[tuple] = {
        (str(row[0]), row[1])
        for row in (await session.execute(select(JobSource.job_id, JobSource.source))).all()
    }
    # ────────────────────────────────────────────────────────────────────

    inserted = linked = 0
    BATCH_SIZE = 200  # 200건마다 commit하여 메모리/타임아웃 방지

    for i, raw in enumerate(raw_jobs):
        if not raw.title or not raw.company:
            continue
        if raw.url in existing_urls:
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

        # 200건마다 중간 commit
        if (i + 1) % BATCH_SIZE == 0:
            await session.commit()
            logger.info(f"  중간 저장: {inserted}건 신규, {linked}건 링크 (진행 {i+1}/{len(raw_jobs)})")

    await session.commit()
    logger.info(f"신규 공고: {inserted}건, 소스 추가: {linked}건")
    return inserted, linked
