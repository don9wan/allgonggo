import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from typing import List
from app.crawlers.base import RawJob
from app.db.database import AsyncSessionLocal
from app.crawlers.db_writer import upsert_jobs

logger = logging.getLogger(__name__)

GROUPBY_API = "https://www.groupby.kr/api/v1/jobs"
GROUPBY_JOB_URL = "https://www.groupby.kr/jobs/{job_id}"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://www.groupby.kr/",
}


def _parse_experience(pos: dict) -> str:
    exp = pos.get("experience", pos.get("career", ""))
    if not exp:
        return "경력무관"
    exp = str(exp).strip()
    if "신입" in exp or exp == "0":
        return "신입"
    if "인턴" in exp:
        return "인턴"
    if exp.isdigit():
        return f"경력 {exp}년 이상"
    return exp


def _parse_employment_type(pos: dict) -> str:
    emp = pos.get("employmentType", pos.get("jobType", "정규직"))
    if not emp:
        return "정규직"
    emp = str(emp)
    if "인턴" in emp or "intern" in emp.lower():
        return "인턴"
    if "계약" in emp or "contract" in emp.lower():
        return "계약직"
    return "정규직"


def _parse_location(pos: dict) -> str:
    loc = pos.get("location", pos.get("address", pos.get("workPlace", "")))
    if isinstance(loc, dict):
        loc = loc.get("name", loc.get("city", ""))
    return str(loc).strip() if loc else "미정"


def _parse_raw_text(pos: dict) -> str:
    company = pos.get("company", {})
    company_name = company.get("name", "") if isinstance(company, dict) else str(company)
    tags = pos.get("tags", pos.get("skills", []))
    tag_text = " ".join([t if isinstance(t, str) else t.get("name", "") for t in tags]) if tags else ""
    parts = [
        pos.get("title", ""),
        company_name,
        _parse_location(pos),
        tag_text,
    ]
    return " ".join(filter(None, parts))


async def fetch_page(client: httpx.AsyncClient, page: int) -> dict:
    params = {"page": page, "size": 50, "sort": "latest"}
    try:
        resp = await client.get(GROUPBY_API, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"그룹바이 API 요청 실패 (page={page}): {e}")
        return {}


async def crawl_groupby() -> List[RawJob]:
    raw_jobs: List[RawJob] = []

    async with httpx.AsyncClient() as client:
        data = await fetch_page(client, 1)
        if not data:
            return raw_jobs

        items = (
            data.get("jobs")
            or data.get("data")
            or data.get("result", {}).get("jobs", [])
            or []
        )
        total = (
            data.get("total")
            or data.get("totalCount")
            or data.get("result", {}).get("total", 0)
            or 0
        )

        logger.info(f"그룹바이 총 공고 수: {total}, 이번 배치: {len(items)}")

        def parse_pos(pos: dict):
            job_id = pos.get("id", pos.get("jobId", pos.get("slug")))
            if not job_id:
                return None
            company = pos.get("company", {})
            company_name = company.get("name", "") if isinstance(company, dict) else str(company)
            return RawJob(
                title=str(pos.get("title", "")).strip(),
                company=company_name.strip(),
                url=GROUPBY_JOB_URL.format(job_id=job_id),
                source="groupby",
                location=_parse_location(pos),
                experience=_parse_experience(pos),
                employment_type=_parse_employment_type(pos),
                raw_text=_parse_raw_text(pos),
            )

        for pos in items:
            try:
                job = parse_pos(pos)
                if job and job.title and job.company:
                    raw_jobs.append(job)
            except Exception as e:
                logger.warning(f"그룹바이 공고 파싱 오류: {e}")

        await asyncio.sleep(1)

        page_size = len(items) or 50
        if total > page_size:
            max_pages = min((total // page_size) + 1, 4)
            for p in range(2, max_pages + 1):
                batch = await fetch_page(client, p)
                if not batch:
                    break
                batch_items = (
                    batch.get("jobs")
                    or batch.get("data")
                    or batch.get("result", {}).get("jobs", [])
                    or []
                )
                for pos in batch_items:
                    try:
                        job = parse_pos(pos)
                        if job and job.title and job.company:
                            raw_jobs.append(job)
                    except Exception as e:
                        logger.warning(f"그룹바이 공고 파싱 오류: {e}")
                await asyncio.sleep(1)

    logger.info(f"그룹바이 수집 완료: {len(raw_jobs)}건")

    if raw_jobs:
        async with AsyncSessionLocal() as session:
            await upsert_jobs(session, raw_jobs)

    return raw_jobs
