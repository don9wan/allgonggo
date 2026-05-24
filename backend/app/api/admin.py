import asyncio
import logging
import httpx
from fastapi import APIRouter, Header, HTTPException

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)

CRAWLER_STATUS = {
    "wanted": {"active": True, "note": "API v4 정상 동작 (신입/IT 필터 적용)"},
    "linkareer": {"active": True, "note": "GraphQL API 직접 호출"},
    "jasoseol": {"active": True, "note": "API 직접 호출 (신입/IT 필터 적용)"},
    "catch": {"active": True, "note": "API 직접 호출 (Career=1 신입 필터)"},
    "groupby": {"active": True, "note": "API 직접 호출"},
}


def _check_key(key: str):
    from app.core.config import settings
    if key != settings.ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/status")
async def get_status(x_admin_key: str = Header(...)):
    """크롤러 상태 + DB 공고 수 조회."""
    _check_key(x_admin_key)
    from sqlalchemy import select, func
    from app.db.database import AsyncSessionLocal
    from app.models.job import Job, JobSource
    async with AsyncSessionLocal() as session:
        job_count = (await session.execute(select(func.count()).select_from(Job))).scalar()
        source_count = (await session.execute(select(func.count()).select_from(JobSource))).scalar()
        by_source = await session.execute(
            select(JobSource.source, func.count(JobSource.id)).group_by(JobSource.source)
        )
        sources = {row[0]: row[1] for row in by_source}
    return {
        "db": {"jobs": job_count, "job_sources": source_count, "by_source": sources},
        "crawlers": CRAWLER_STATUS,
    }


@router.post("/crawl")
async def trigger_crawl(x_admin_key: str = Header(...)):
    """모든 활성 크롤러를 백그라운드에서 실행."""
    _check_key(x_admin_key)

    async def run():
        from app.crawlers.wanted import crawl_wanted
        from app.crawlers.linkareer import crawl_linkareer
        from app.crawlers.jasoseol import crawl_jasoseol
        from app.crawlers.catch import crawl_catch
        from app.crawlers.groupby import crawl_groupby
        for name, fn in [
            ("wanted", crawl_wanted),
            ("linkareer", crawl_linkareer),
            ("jasoseol", crawl_jasoseol),
            ("catch", crawl_catch),
            ("groupby", crawl_groupby),
        ]:
            try:
                await fn()
                logger.info(f"{name} 완료")
            except Exception as e:
                logger.error(f"{name} 실패: {e}")

    asyncio.create_task(run())
    return {"status": "started", "active_crawlers": [k for k, v in CRAWLER_STATUS.items() if v["active"]]}


@router.post("/crawl/wanted")
async def trigger_wanted(x_admin_key: str = Header(...)):
    """원티드만 즉시 크롤링 (결과 반환)."""
    _check_key(x_admin_key)
    from app.crawlers.wanted import crawl_wanted
    jobs = await crawl_wanted()
    return {"count": len(jobs), "sample": [{"title": j.title, "company": j.company} for j in jobs[:5]]}


@router.post("/crawl/linkareer")
async def trigger_linkareer(x_admin_key: str = Header(...)):
    """링커리어만 즉시 크롤링 (결과 반환)."""
    _check_key(x_admin_key)
    from app.crawlers.linkareer import crawl_linkareer
    jobs = await crawl_linkareer()
    return {"count": len(jobs), "sample": [{"title": j.title, "company": j.company} for j in jobs[:5]]}


@router.post("/crawl/jasoseol")
async def trigger_jasoseol(x_admin_key: str = Header(...)):
    """자소설닷컴만 즉시 크롤링 (결과 반환)."""
    _check_key(x_admin_key)
    from app.crawlers.jasoseol import crawl_jasoseol
    jobs = await crawl_jasoseol()
    return {"count": len(jobs), "sample": [{"title": j.title, "company": j.company} for j in jobs[:5]]}


@router.post("/crawl/catch")
async def trigger_catch(x_admin_key: str = Header(...)):
    """캐치만 즉시 크롤링 (결과 반환)."""
    _check_key(x_admin_key)
    from app.crawlers.catch import crawl_catch
    jobs = await crawl_catch()
    return {"count": len(jobs), "sample": [{"title": j.title, "company": j.company} for j in jobs[:5]]}


@router.post("/crawl/groupby")
async def trigger_groupby(x_admin_key: str = Header(...)):
    """그룹바이만 즉시 크롤링 (Playwright, 결과 반환)."""
    _check_key(x_admin_key)
    from app.crawlers.groupby import crawl_groupby
    jobs = await crawl_groupby()
    return {"count": len(jobs), "sample": [{"title": j.title, "company": j.company} for j in jobs[:5]]}


@router.get("/jobs/recent")
async def recent_jobs(x_admin_key: str = Header(...), limit: int = 50, source: str = None):
    """최근 수집된 공고 목록."""
    _check_key(x_admin_key)
    from sqlalchemy import select, desc
    from sqlalchemy.orm import selectinload
    from app.db.database import AsyncSessionLocal
    from app.models.job import Job, JobSource
    async with AsyncSessionLocal() as session:
        q = (
            select(Job)
            .options(selectinload(Job.sources))
            .order_by(desc(Job.crawled_at))
            .limit(limit)
        )
        if source:
            subq = select(JobSource.job_id).where(JobSource.source == source).distinct()
            q = q.where(Job.id.in_(subq))
        result = await session.execute(q)
        jobs = result.scalars().all()
    return [
        {
            "id": str(j.id),
            "title": j.title,
            "company": j.company,
            "source": j.sources[0].source if j.sources else "unknown",
            "experience": j.experience,
            "employment_type": j.employment_type,
            "location": j.location,
            "url": j.sources[0].url if j.sources else "",
        }
        for j in jobs
    ]


@router.get("/debug/catch")
async def debug_catch(x_admin_key: str = Header(...)):
    """캐치 API cloudscraper Cloudflare 우회 테스트."""
    _check_key(x_admin_key)
    result = {"cloudscraper_import": False, "status": None, "count": None, "error": None}
    try:
        import cloudscraper
        result["cloudscraper_import"] = True
    except ImportError as e:
        result["error"] = f"cloudscraper 미설치: {e}"
        return result
    try:
        def _test():
            scraper = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "mobile": False})
            r = scraper.get(
                "https://www.catch.co.kr/api/v1.0/recruit/information/getRecruitList",
                params={"Career": "1", "Sort": "0", "curpage": 1, "pageSize": 5, "onRecruitYN": "Y"},
                timeout=20,
            )
            return r.status_code, r.text[:300] if r.status_code != 200 else None, r.json() if r.status_code == 200 else None
        import asyncio
        status, body, data = await asyncio.to_thread(_test)
        result["status"] = status
        if status == 200 and data:
            result["count"] = len(data.get("recruitData", []))
        else:
            result["body_preview"] = body
    except Exception as e:
        result["error"] = str(e)
    return result


@router.get("/debug/wanted")
async def debug_wanted(x_admin_key: str = Header(...)):
    """원티드 API 응답 구조 확인 (신입/IT 필터 적용)."""
    _check_key(x_admin_key)

    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://www.wanted.co.kr/",
        "Wanted-User-Agent": "user-web",
    }
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(
            "https://www.wanted.co.kr/api/v4/jobs",
            params={
                "country": "kr",
                "job_sort": "job.latest_order",
                "years": 0,
                "tag_type_ids": 518,
                "locations": "all",
                "limit": 5,
                "offset": 0,
            },
            headers=headers,
            timeout=10,
        )
        data = resp.json()
        jobs = data.get("data", [])
        return {
            "status": resp.status_code,
            "total": data.get("total"),
            "count": len(jobs),
            "sample_jobs": [
                {
                    "title": j.get("position"),
                    "company": j.get("company", {}).get("name"),
                    "annual_from": j.get("annual_from"),
                    "annual_to": j.get("annual_to"),
                }
                for j in jobs
            ],
        }


@router.get("/debug/playwright")
async def debug_playwright(x_admin_key: str = Header(...)):
    """Playwright + Chromium 동작 여부 및 catch.co.kr 접근 테스트."""
    _check_key(x_admin_key)
    result = {"import": False, "launch": False, "goto": False, "fetch": False, "error": None, "page_title": None, "fetch_status": None, "items_count": None}
    try:
        from playwright.async_api import async_playwright
        result["import"] = True
    except ImportError as e:
        result["error"] = f"import 실패: {e}"
        return result
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
            result["launch"] = True
            ctx = await browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36", locale="ko-KR")
            page = await ctx.new_page()
            try:
                await page.goto("https://www.catch.co.kr", wait_until="networkidle", timeout=25000)
                result["goto"] = True
                result["page_title"] = await page.title()
            except Exception as e:
                result["error"] = f"goto 실패: {e}"
                await browser.close()
                return result
            try:
                fetch_result = await page.evaluate("""
                async () => {
                    const resp = await fetch(
                        '/api/v1.0/recruit/information/getRecruitList?Career=1&Sort=0&curpage=1&pageSize=3&onRecruitYN=Y',
                        { headers: { Accept: 'application/json' } }
                    );
                    const status = resp.status;
                    const data = await resp.json();
                    return { status, count: (data.recruitData || []).length };
                }
                """)
                result["fetch"] = True
                result["fetch_status"] = fetch_result.get("status")
                result["items_count"] = fetch_result.get("count")
            except Exception as e:
                result["error"] = f"evaluate 실패: {e}"
            await browser.close()
    except Exception as e:
        result["error"] = f"launch 실패: {e}"
    return result


@router.get("/debug/db")
async def debug_db(x_admin_key: str = Header(...)):
    """DB 공고 수 + 소스별 집계."""
    _check_key(x_admin_key)
    from sqlalchemy import text, select, func
    from app.db.database import AsyncSessionLocal
    from app.models.job import Job, JobSource
    async with AsyncSessionLocal() as session:
        job_count = (await session.execute(select(func.count()).select_from(Job))).scalar()
        source_count = (await session.execute(select(func.count()).select_from(JobSource))).scalar()
        by_source = await session.execute(
            select(JobSource.source, func.count(JobSource.id)).group_by(JobSource.source)
        )
        sources = {row[0]: row[1] for row in by_source}
    return {"total_jobs": job_count, "total_sources": source_count, "by_source": sources}
