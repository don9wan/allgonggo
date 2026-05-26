import re
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, case
from typing import Optional
from app.db.database import get_db
from app.models.job import Job, JobSource
from app.schemas.job import JobOut, JobListResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])

# 1~3글자 순수 영문: 단어 경계 regex 적용 대상
_SHORT_ENG = re.compile(r'^[A-Za-z]{1,3}$')


def _token_filter(token: str):
    """단일 검색 토큰에 대한 필터 조건.
    짧은 영문(≤3자)은 PostgreSQL word boundary regex로 노이즈 차단.
    예: 'PM' → \yPM\y (SPAM, PMO 등 미매칭), '백엔드' → ILIKE '%백엔드%'
    """
    if _SHORT_ENG.match(token):
        return Job.raw_text.op('~*')(f'\\y{re.escape(token)}\\y')
    return Job.raw_text.ilike(f'%{token}%')


def _token_title_match(token: str):
    """관련도 정렬용 title 매칭 조건."""
    if _SHORT_ENG.match(token):
        return Job.title.op('~*')(f'\\y{re.escape(token)}\\y')
    return Job.title.ilike(f'%{token}%')


@router.get("", response_model=JobListResponse)
async def list_jobs(
    q: Optional[str] = Query(None, description="키워드 검색 (공백 분리 시 AND 조건)"),
    location: Optional[str] = Query(None, description="근무지역 (콤마 구분 복수 가능)"),
    experience: Optional[str] = Query(None, description="경력 조건 (콤마 구분 복수 가능)"),
    employment_type: Optional[str] = Query(None, description="고용형태 (콤마 구분 복수 가능)"),
    source: Optional[str] = Query(None, description="공고 출처 (콤마 구분 복수 가능)"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    filters = [Job.is_active == True]
    tokens: list[str] = []

    if q:
        tokens = [t for t in q.split() if t.strip()]
        for token in tokens:
            filters.append(_token_filter(token))

    if location:
        locs = [l.strip() for l in location.split(",") if l.strip()]
        if locs:
            filters.append(or_(*[Job.location.ilike(f"%{loc}%") for loc in locs]))

    if experience:
        exps = [e.strip() for e in experience.split(",") if e.strip()]
        if exps:
            filters.append(or_(*[Job.experience.ilike(f"%{exp}%") for exp in exps]))

    if employment_type:
        types = [t.strip() for t in employment_type.split(",") if t.strip()]
        if types:
            filters.append(or_(*[Job.employment_type.ilike(f"%{t}%") for t in types]))

    base_query = select(Job).where(and_(*filters))

    if source:
        sources = [s.strip() for s in source.split(",") if s.strip()]
        if sources:
            subq = select(JobSource.job_id).where(JobSource.source.in_(sources)).distinct()
            base_query = base_query.where(Job.id.in_(subq))

    offset = (page - 1) * size

    if page == 1:
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await db.execute(count_query)
        total: int | None = total_result.scalar_one()
    else:
        total = None

    # 검색어 있을 때: title 직접 매칭 공고 우선 → 그 안에서 최신순
    if tokens:
        title_match = _token_title_match(tokens[0])
        order = [case((title_match, 0), else_=1), Job.crawled_at.desc()]
    else:
        order = [Job.crawled_at.desc()]

    from sqlalchemy.orm import selectinload
    jobs_query = (
        base_query
        .order_by(*order)
        .offset(offset)
        .limit(size)
        .options(selectinload(Job.sources))
    )

    result = await db.execute(jobs_query)
    jobs = result.scalars().all()

    return JobListResponse(
        jobs=list(jobs),
        total=total,
        page=page,
        size=size,
        has_next=len(jobs) == size,
    )


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    from sqlalchemy.orm import selectinload
    from fastapi import HTTPException
    result = await db.execute(
        select(Job)
        .where(Job.id == job_id)
        .options(selectinload(Job.sources))
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다")
    return job
