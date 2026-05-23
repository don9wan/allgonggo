import logging
from datetime import datetime, timezone
from typing import List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from app.models.job import Job, JobSource
from app.crawlers.base import RawJob

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.8

# 페이지 내 URL 중 이 비율 이상이 이미 DB에 있으면 페이지네이션 조기 종료
# (이전 크롤링 시점까지 따라잡았다는 신호)
CATCHUP_RATIO = 0.70


async def already_seen_ratio(session: AsyncSession, urls: List[str]) -> float:
    """
    주어진 URL 목록 중 몇 %가 이미 job_sources에 있는지 반환.
    크롤러가 이전 크롤링 시점까지 따라잡았는지 판단하는 데 사용.
    """
    if not urls:
        return 0.0
    result = await session.execute(
        select(func.count())
        .select_from(JobSource)
        .where(JobSource.url.in_(urls))
    )
    known = result.scalar_one()
    return known / len(urls)


async def is_caught_up(session: AsyncSession, page_jobs: List[RawJob]) -> bool:
    """
    한 페이지 분량의 공고 URL 중 CATCHUP_RATIO 이상이 기존 DB에 있으면 True.
    True이면 이후 페이지는 가져오지 않아도 됨.
    """
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
    공고 목록을 DB에 upsert.
    - URL 중복이면 스킵
    - 회사명 일치 + 제목 유사도 80% 이상이면 job_sources에 링크 추가
    - 그 외 신규 INSERT
    Returns: (inserted, linked)
    """
    inserted = 0
    linked = 0

    for raw in raw_jobs:
        if not raw.title or not raw.company:
            continue

        try:
            url_result = await session.execute(
                select(JobSource.id).where(JobSource.url == raw.url)
            )
            if url_result.scalar_one_or_none():
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
                    text("SELECT similarity(:a, :b)"),
                    {"a": raw.title, "b": candidate.title},
                )
                sim = sim_result.scalar()
                if sim and sim >= SIMILARITY_THRESHOLD:
                    matched_job = candidate
                    break

            if matched_job:
                # 같은 소스가 이미 이 job에 연결돼 있으면 스킵 (아이콘 중복 방지)
                dup_result = await session.execute(
                    select(JobSource.id).where(
                        JobSource.job_id == matched_job.id,
                        JobSource.source == raw.source,
                    )
                )
                if dup_result.scalar_one_or_none():
                    continue
                session.add(JobSource(
                    job_id=matched_job.id,
                    source=raw.source,
                    url=raw.url,
                ))
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
                session.add(JobSource(
                    job_id=new_job.id,
                    source=raw.source,
                    url=raw.url,
                ))
                inserted += 1

        except Exception as e:
            logger.error(f"DB 저장 오류 [{raw.company} / {raw.title}]: {e}")
            await session.rollback()
            continue

    await session.commit()
    logger.info(f"신규 공고: {inserted}건, 소스 추가: {linked}건")
    return inserted, linked
