import logging
import httpx
from typing import List, Optional
from app.crawlers.base import RawJob
from app.crawlers.utils import SafeClient
from app.db.database import AsyncSessionLocal
from app.crawlers.db_writer import upsert_jobs, is_caught_up

logger = logging.getLogger(__name__)

BASE_URL = "https://www.catch.co.kr"
API_URL = f"{BASE_URL}/api/recruit/list"
JOB_URL = f"{BASE_URL}/NCS/RecruitInfoDetails/{{job_id}}"
MAX_PAGES = 4


def _parse_experience(pos: dict) -> str:
    career = str(pos.get("career", pos.get("careerNm", ""))).strip()
    if not career:
        return "경력무관"
    if "신입" in career:
        return "신입"
    if "인턴" in career:
        return "인턴"
    if "경력" in career:
        return career
    return "경력무관"


def _parse_employment_type(pos: dict) -> str:
    emp = str(pos.get("empType", pos.get("empTypeNm", ""))).strip()
    if "인턴" in emp:
        return "인턴"
    if "계약" in emp:
        return "계약직"
    return "정규직"


def _parse_location(pos: dict) -> str:
    loc = pos.get("locNm") or pos.get("location") or pos.get("addr") or ""
    return str(loc).strip() or "미정"


def _parse_raw_text(pos: dict) -> str:
    parts = [
        pos.get("recruitTitle", pos.get("title", "")),
        pos.get("compNm", pos.get("company", "")),
        _parse_location(pos),
        pos.get("jobNm", ""),
    ]
    return " ".join(filter(None, [str(p) for p in parts]))


def _to_raw_job(pos: dict) -> Optional[RawJob]:
    job_id = pos.get("recruitSeq", pos.get("id", pos.get("seq")))
    title = str(pos.get("recruitTitle", pos.get("title", ""))).strip()
    company = str(pos.get("compNm", pos.get("company", ""))).strip()
    if not job_id or not title or not company:
        return None
    return RawJob(
        title=title,
        company=company,
        url=JOB_URL.format(job_id=job_id),
        source="catch",
        location=_parse_location(pos),
        experience=_parse_experience(pos),
        employment_type=_parse_employment_type(pos),
        raw_text=_parse_raw_text(pos),
    )


async def crawl_catch() -> List[RawJob]:
    safe = SafeClient(BASE_URL, min_delay=3.0, max_delay=6.0)
    all_jobs: List[RawJob] = []

    async with httpx.AsyncClient(follow_redirects=True) as client:
        await safe.setup(client)

        for page in range(1, MAX_PAGES + 1):
            data = await safe.get(
                client,
                API_URL,
                params={
                    "pageIndex": page,
                    "pageSize": 50,
                    "sortType": "LATEST",
                    "jobType": "IT",
                },
                extra_headers={"Referer": f"{BASE_URL}/"},
            )

            if not data:
                logger.warning(f"캐치 페이지 {page} 응답 없음 → 중단")
                break

            items = (
                data.get("recruitList")
                or data.get("list")
                or (data.get("data") or {}).get("list", [])
                or []
            )
            if not items:
                break

            page_jobs = [j for pos in items if (j := _to_raw_job(pos))]
            all_jobs.extend(page_jobs)

            if page == 1:
                total = (
                    data.get("totalCnt")
                    or data.get("totalCount")
                    or (data.get("data") or {}).get("totalCnt", "?")
                )
                logger.info(f"캐치 총 {total}건, 1페이지 {len(page_jobs)}건")

            async with AsyncSessionLocal() as session:
                if await is_caught_up(session, page_jobs):
                    break

            if len(items) < 50:
                break

    logger.info(f"캐치 수집 완료: {len(all_jobs)}건")
    if all_jobs:
        async with AsyncSessionLocal() as session:
            await upsert_jobs(session, all_jobs)

    return all_jobs
