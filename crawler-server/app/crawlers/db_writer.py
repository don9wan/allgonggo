import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawlers.base import RawJob
from app.models.job import Job, JobSource

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.75
CATCHUP_RATIO = 0.70
_URL_CHUNK = 500

# 플랫폼별 제목 노이즈 패턴: [회사명], [신입], [정규직], 연도, 상/하반기 등
_RE_BRACKET = re.compile(r'\[.*?\]')
_RE_YEAR = re.compile(r'20\d{2}년도?')
_RE_HALF = re.compile(r'[상하]반기')
_RE_WS = re.compile(r'\s+')

# 이 단어들만 남은 경우 cross-source merge 신뢰 불가
_GENERIC_TITLES = {
    '집중채용', '수시채용', '공개채용', '공채', '채용', '채용공고',
    '신입채용', '경력채용', '신입/경력채용', '신입/경력 채용',
}
_MIN_NORM_LEN = 5  # 정규화 후 이 길이 미만이면 merge 대상에서 제외


def _normalize_title(title: str) -> str:
    """플랫폼별 접두사·연도·채용시즌 표현 제거 후 소문자 정규화."""
    t = _RE_BRACKET.sub(' ', title)
    t = _RE_YEAR.sub(' ', t)
    t = _RE_HALF.sub(' ', t)
    t = _RE_WS.sub(' ', t)
    return t.strip().lower()


def _is_matchable(norm: str) -> bool:
    """정규화된 타이틀이 cross-source 매칭에 충분히 구체적인지 판단."""
    if len(norm) < _MIN_NORM_LEN:
        return False
    return norm not in _GENERIC_TITLES


def _trigram_sim(a: str, b: str) -> float:
    """PostgreSQL pg_trgm similarity 동일 알고리즘을 Python으로 구현. DB round-trip 없이 계산."""
    def trigrams(s: str) -> set:
        s = f"  {s}  "
        return {s[i:i+3] for i in range(len(s) - 2)}
    ta, tb = trigrams(a), trigrams(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return 2 * len(ta & tb) / (len(ta) + len(tb))


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

    # ── 1. 기존 데이터 메모리 로드 (소스 단위 필터링, 필요 컬럼만) ──
    existing_urls: set[str] = {
        row[0]
        for row in (await session.execute(
            select(JobSource.url).where(JobSource.source == source)
        )).all()
    }

    existing_jobs_rows = (
        await session.execute(
            select(Job.id, Job.title, Job.company).where(Job.is_active == True)
        )
    ).all()

    jobs_by_company: dict[str, list] = {}
    for row in existing_jobs_rows:
        jobs_by_company.setdefault(row.company.lower(), []).append(
            (row, _normalize_title(row.title))
        )

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
        norm_raw = _normalize_title(raw.title)

        matched_job = None
        if _is_matchable(norm_raw):
            for candidate_row, norm_candidate in candidates:
                if _is_matchable(norm_candidate) and _trigram_sim(norm_raw, norm_candidate) >= SIMILARITY_THRESHOLD:
                    matched_job = candidate_row
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
            jobs_by_company.setdefault(raw.company.lower(), []).append(
                (new_job, norm_raw)
            )
            inserted += 1

        if (i + 1) % BATCH_SIZE == 0:
            await session.commit()
            logger.info(f"  중간 저장: {inserted}건 신규, {linked}건 링크 (진행 {i+1}/{len(raw_jobs)})")

    await session.commit()

    # 기존 URL crawled_at 청크 단위 갱신 (대량 IN절 방지)
    if seen_existing_urls:
        now = datetime.now(timezone.utc)
        for i in range(0, len(seen_existing_urls), _URL_CHUNK):
            chunk = seen_existing_urls[i:i + _URL_CHUNK]
            await session.execute(
                update(JobSource)
                .where(JobSource.url.in_(chunk))
                .values(crawled_at=now)
            )
        await session.commit()
        logger.info(f"  기존 URL {len(seen_existing_urls)}건 갱신")

    logger.info(f"신규 공고: {inserted}건, 소스 추가: {linked}건")
    return inserted, linked
