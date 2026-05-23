from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from typing import List, Optional
from app.db.database import get_db
from app.models.job import Job, JobSource
from app.schemas.job import JobOut, JobListResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobListResponse)
async def list_jobs(
    q: Optional[str] = Query(None, description="키워드 검색 (제목, 회사명, raw_text)"),
    location: Optional[str] = Query(None, description="근무지역 (콤마 구분 복수 가능)"),
    experience: Optional[str] = Query(None, description="경력 조건 (콤마 구분 복수 가능)"),
    employment_type: Optional[str] = Query(None, description="고용형태 (콤마 구분 복수 가능)"),
    source: Optional[str] = Query(None, description="공고 출처 (콤마 구분 복수 가능)"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    filters = [Job.is_active == True]

    if q:
        search_term = f"%{q}%"
        filters.append(
            or_(
                Job.title.ilike(search_term),
                Job.company.ilike(search_term),
                Job.raw_text.ilike(search_term),
            )
        )

    if location:
        locs = [l.strip() for l in location.split(",") if l.strip()]
        if locs:
            loc_filters = [Job.location.ilike(f"%{loc}%") for loc in locs]
            filters.append(or_(*loc_filters))

    if experience:
        exps = [e.strip() for e in experience.split(",") if e.strip()]
        if exps:
            exp_filters = [Job.experience.ilike(f"%{exp}%") for exp in exps]
            filters.append(or_(*exp_filters))

    if employment_type:
        types = [t.strip() for t in employment_type.split(",") if t.strip()]
        if types:
            type_filters = [Job.employment_type.ilike(f"%{t}%") for t in types]
            filters.append(or_(*type_filters))

    base_query = select(Job).where(and_(*filters))

    if source:
        sources = [s.strip() for s in source.split(",") if s.strip()]
        if sources:
            subq = select(JobSource.job_id).where(JobSource.source.in_(sources)).distinct()
            base_query = base_query.where(Job.id.in_(subq))

    offset = (page - 1) * size

    # COUNT는 첫 페이지에만 실행 (이후 페이지는 불필요)
    if page == 1:
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await db.execute(count_query)
        total: int | None = total_result.scalar_one()
    else:
        total = None
    jobs_query = (
        base_query
        .order_by(Job.crawled_at.desc())
        .offset(offset)
        .limit(size)
    )

    from sqlalchemy.orm import selectinload
    jobs_query = jobs_query.options(selectinload(Job.sources))

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
