import logging
import httpx
from typing import List, Optional
from app.crawlers.base import RawJob
from app.crawlers.utils import SafeClient
from app.db.database import AsyncSessionLocal
from app.crawlers.db_writer import upsert_jobs, is_caught_up

logger = logging.getLogger(__name__)

BASE_URL = "https://www.groupby.kr"
API_URL = f"{BASE_URL}/api/v1/jobs"
JOB_URL = f"{BASE_URL}/jobs/{{job_id}}"
MAX_PAGES = 4


def _parse_experience(pos: dict) -> str:
    exp = str(pos.get("experience", pos.get("career", ""))).strip()
    if not exp or exp == "0":
        return "경력무관"
    if "신입" in exp:
        return "신입"
    if "인턴" in exp:
        return "인턴"
    if exp.isdigit():
        return f"경력 {exp}년 이상"
    return exp


def _parse_employment_type(pos: dict) -> str:
    emp = str(pos.get("employmentType", pos.get("jobType", ""))).lower()
    if "인턴" in emp or "intern" in emp:
        return "인턴"
    if "계약" in emp or "contract" in emp:
        return "계약직"
    return "정규직"


def _parse_location(pos: dict) -> str:
    loc = pos.get("location") or pos.get("address") or pos.get("workPlace") or ""
    if isinstance(loc, dict):
        loc = loc.get("name", loc.get("city", ""))
    return str(loc).strip() or "미정"


def _parse_raw_text(pos: dict) -> str:
    company = pos.get("company", {})
    company_name = company.get("name", "") if isinstance(company, dict) else str(company)
    tags = pos.get("tags", pos.get("skills", []))
    tag_text = " ".join(
        t if isinstance(t, str) else t.get("name", "") for t in tags
    )
    parts = [pos.get("title", ""), company_name, _parse_location(pos), tag_text]
    return " ".join(filter(None, parts))


def _to_raw_job(pos: dict) -> Optional[RawJob]:
    job_id = pos.get("id", pos.get("jobId", pos.get("slug")))
    title = str(pos.get("title", "")).strip()
    company = pos.get("company", {})
    company_name = (
        company.get("name", "") if isinstance(company, dict) else str(company)
    ).strip()
    if not job_id or not title or not company_name:
        return None
    return RawJob(
        title=title,
        company=company_name,
        url=JOB_URL.format(job_id=job_id),
        source="groupby",
        location=_parse_location(pos),
        experience=_parse_experience(pos),
        employment_type=_parse_employment_type(pos),
        raw_text=_parse_raw_text(pos),
    )


async def crawl_groupby() -> List[RawJob]:
    safe = SafeClient(BASE_URL, min_delay=2.0, max_delay=4.0)
    all_jobs: List[RawJob] = []

    async with httpx.AsyncClient(follow_redirects=True) as client:
        await safe.setup(client)

        for page in range(1, MAX_PAGES + 1):
            data = await safe.get(
                client,
                API_URL,
                params={"page": page, "size": 50, "sort": "latest"},
                extra_headers={"Referer": f"{BASE_URL}/"},
            )

            if not data:
                logger.warning(f"그룹바이 페이지 {page} 응답 없음 → 중단")
                break

            items = (
                data.get("jobs")
                or data.get("data")
                or (data.get("result") or {}).get("jobs", [])
                or []
            )
            if not items:
                break

            page_jobs = [j for pos in items if (j := _to_raw_job(pos))]
            all_jobs.extend(page_jobs)

            if page == 1:
                total = (
                    data.get("total")
                    or data.get("totalCount")
                    or (data.get("result") or {}).get("total", "?")
                )
                logger.info(f"그룹바이 총 {total}건, 1페이지 {len(page_jobs)}건")

            async with AsyncSessionLocal() as session:
                if await is_caught_up(session, page_jobs):
                    break

            if len(items) < 50:
                break

    logger.info(f"그룹바이 수집 완료: {len(all_jobs)}건")
    if all_jobs:
        async with AsyncSessionLocal() as session:
            await upsert_jobs(session, all_jobs)

    return all_jobs
