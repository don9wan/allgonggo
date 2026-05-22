import logging
import httpx
from typing import List, Optional
from app.crawlers.base import RawJob
from app.crawlers.utils import SafeClient
from app.db.database import AsyncSessionLocal
from app.crawlers.db_writer import upsert_jobs, is_caught_up

logger = logging.getLogger(__name__)

BASE_URL = "https://www.wanted.co.kr"
API_URL = f"{BASE_URL}/api/v4/jobs"
JOB_URL = f"{BASE_URL}/wd/{{job_id}}"
MAX_PAGES = 5
PAGE_SIZE = 100


def _parse_experience(pos: dict) -> str:
    annual_from = pos.get("annual_from", 0) or 0
    if annual_from == 0:
        return "경력무관"
    if annual_from <= 1:
        return "신입"
    return f"경력 {annual_from}년 이상"


def _parse_location(pos: dict) -> str:
    addr = pos.get("address") or {}
    return addr.get("location", "").strip() or "미정"


def _parse_raw_text(pos: dict) -> str:
    company = pos.get("company") or {}
    tags = pos.get("category_tags") or []
    parts = [
        pos.get("position", ""),
        company.get("name", ""),
        _parse_location(pos),
        company.get("industry_name", ""),
    ]
    return " ".join(filter(None, parts))


def _to_raw_job(pos: dict) -> Optional[RawJob]:
    job_id = pos.get("id")
    title = pos.get("position", "").strip()
    company = pos.get("company") or {}
    company_name = company.get("name", "").strip()

    if not job_id or not title or not company_name:
        return None
    if pos.get("hidden") or pos.get("status") == "closed":
        return None

    return RawJob(
        title=title,
        company=company_name,
        url=JOB_URL.format(job_id=job_id),
        source="wanted",
        location=_parse_location(pos),
        experience=_parse_experience(pos),
        employment_type="정규직",
        raw_text=_parse_raw_text(pos),
    )


async def crawl_wanted() -> List[RawJob]:
    safe = SafeClient(BASE_URL, min_delay=2.0, max_delay=5.0)
    all_jobs: List[RawJob] = []

    params = {
        "country": "kr",
        "job_sort": "job.latest_order",
        "years": -1,
        "locations": "all",
        "limit": PAGE_SIZE,
        "offset": 0,
    }
    extra = {"Referer": f"{BASE_URL}/", "Wanted-User-Agent": "user-web"}

    async with httpx.AsyncClient(follow_redirects=True) as client:
        await safe.setup(client)

        for page in range(MAX_PAGES):
            params["offset"] = page * PAGE_SIZE
            data = await safe.get(client, API_URL, params=params, extra_headers=extra)

            if not data:
                logger.warning(f"원티드 페이지 {page+1} 응답 없음 → 중단")
                break

            positions = data.get("data", [])
            if not positions:
                break

            page_jobs = [j for pos in positions if (j := _to_raw_job(pos))]
            all_jobs.extend(page_jobs)

            if page == 0:
                logger.info(f"원티드 1페이지 {len(page_jobs)}건 수집")

            async with AsyncSessionLocal() as session:
                if await is_caught_up(session, page_jobs):
                    break

            if not data.get("links", {}).get("next"):
                break

    logger.info(f"원티드 수집 완료: {len(all_jobs)}건")
    if all_jobs:
        async with AsyncSessionLocal() as session:
            await upsert_jobs(session, all_jobs)

    return all_jobs
