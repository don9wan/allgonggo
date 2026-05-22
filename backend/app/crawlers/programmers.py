import logging
import httpx
from typing import List, Optional
from app.crawlers.base import RawJob
from app.crawlers.utils import SafeClient
from app.db.database import AsyncSessionLocal
from app.crawlers.db_writer import upsert_jobs, is_caught_up

logger = logging.getLogger(__name__)

BASE_URL = "https://career.programmers.co.kr"
API_URL = f"{BASE_URL}/api/job_positions"
JOB_URL = f"{BASE_URL}/job_positions/{{job_id}}"
MAX_PAGES = 5


def _parse_experience(pos: dict) -> str:
    min_c = pos.get("minCareer", pos.get("min_career", 0)) or 0
    if min_c == 0:
        return "경력무관"
    return f"경력 {min_c}년 이상"


def _parse_location(pos: dict) -> str:
    addr = pos.get("address", "") or ""
    if isinstance(addr, dict):
        addr = addr.get("location", "")
    return str(addr).strip() or "미정"


def _parse_raw_text(pos: dict) -> str:
    company = pos.get("company", {})
    company_name = company.get("name", "") if isinstance(company, dict) else str(company)
    skills = pos.get("technicalTags", pos.get("skills", []))
    skill_text = " ".join(
        s if isinstance(s, str) else s.get("name", "") for s in skills
    )
    parts = [
        pos.get("name", pos.get("title", "")),
        company_name,
        _parse_location(pos),
        skill_text,
    ]
    return " ".join(filter(None, parts))


def _to_raw_job(pos: dict) -> Optional[RawJob]:
    job_id = pos.get("id")
    title = pos.get("name", pos.get("title", "")).strip()
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
        source="programmers",
        location=_parse_location(pos),
        experience=_parse_experience(pos),
        employment_type="정규직",
        raw_text=_parse_raw_text(pos),
    )


async def crawl_programmers() -> List[RawJob]:
    safe = SafeClient(BASE_URL, min_delay=2.0, max_delay=4.5)
    all_jobs: List[RawJob] = []

    async with httpx.AsyncClient(follow_redirects=True) as client:
        await safe.setup(client)

        for page in range(1, MAX_PAGES + 1):
            data = await safe.get(
                client,
                API_URL,
                params={"order": "recent", "page": page, "min_career": 0},
                extra_headers={"Referer": f"{BASE_URL}/job"},
            )

            if not data:
                logger.warning(f"프로그래머스 페이지 {page} 응답 없음 → 중단")
                break

            positions = data.get("jobPositions", data.get("job_positions", []))
            if not positions:
                break

            page_jobs = [j for pos in positions if (j := _to_raw_job(pos))]
            all_jobs.extend(page_jobs)

            if page == 1:
                total = data.get("totalCount", data.get("total_count", "?"))
                logger.info(f"프로그래머스 총 {total}건, 1페이지 {len(page_jobs)}건")

            async with AsyncSessionLocal() as session:
                if await is_caught_up(session, page_jobs):
                    break

            if len(positions) < 20:
                break

    logger.info(f"프로그래머스 수집 완료: {len(all_jobs)}건")
    if all_jobs:
        async with AsyncSessionLocal() as session:
            await upsert_jobs(session, all_jobs)

    return all_jobs
