import logging
from datetime import datetime, timezone
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from app.models.job import Job, JobSource
from app.crawlers.base import RawJob

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.8


async def upsert_jobs(session: AsyncSession, raw_jobs: List[RawJob]) -> None:
    inserted = 0
    linked = 0

    for raw in raw_jobs:
        if not raw.title or not raw.company:
            continue

        try:
            url_result = await session.execute(
                select(JobSource).where(JobSource.url == raw.url)
            )
            existing_source = url_result.scalar_one_or_none()
            if existing_source:
                continue

            company_result = await session.execute(
                select(Job).where(
                    func.lower(Job.company) == func.lower(raw.company),
                    Job.is_active == True,
                )
            )
            company_jobs = company_result.scalars().all()

            matched_job = None
            for candidate in company_jobs:
                sim_result = await session.execute(
                    text(
                        "SELECT similarity(:a, :b)"
                    ),
                    {"a": raw.title, "b": candidate.title},
                )
                sim = sim_result.scalar()
                if sim and sim >= SIMILARITY_THRESHOLD:
                    matched_job = candidate
                    break

            if matched_job:
                new_source = JobSource(
                    job_id=matched_job.id,
                    source=raw.source,
                    url=raw.url,
                )
                session.add(new_source)
                linked += 1
            else:
                new_job = Job(
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
                await session.flush()

                new_source = JobSource(
                    job_id=new_job.id,
                    source=raw.source,
                    url=raw.url,
                )
                session.add(new_source)
                inserted += 1

        except Exception as e:
            logger.error(f"DB 저장 오류 [{raw.company} / {raw.title}]: {e}")
            await session.rollback()
            continue

    await session.commit()
    logger.info(f"신규 공고: {inserted}건, 소스 추가: {linked}건")
