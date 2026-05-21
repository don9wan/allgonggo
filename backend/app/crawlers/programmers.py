import asyncio
import logging
import httpx
from typing import List
from app.crawlers.base import RawJob
from app.db.database import AsyncSessionLocal
from app.crawlers.db_writer import upsert_jobs

logger = logging.getLogger(__name__)

PROGRAMMERS_API = "https://career.programmers.co.kr/api/job_positions"
PROGRAMMERS_JOB_URL = "https://career.programmers.co.kr/job_positions/{job_id}"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://career.programmers.co.kr/job",
}


def _parse_experience(pos: dict) -> str:
    min_c = pos.get("minCareer", pos.get("min_career", 0)) or 0
    max_c = pos.get("maxCareer", pos.get("max_career", 0)) or 0
    if min_c == 0 and max_c == 0:
        return "경력무관"
    if min_c == 0:
        return "신입"
    return f"경력 {min_c}년 이상"


def _parse_location(pos: dict) -> str:
    address = pos.get("address", "") or ""
    if isinstance(address, dict):
        address = address.get("location", "")
    return address.strip() if address else "미정"


def _parse_raw_text(pos: dict) -> str:
    company = pos.get("company", {})
    company_name = company.get("name", "") if isinstance(company, dict) else str(company)
    parts = [
        pos.get("name", pos.get("title", "")),
        company_name,
        _parse_location(pos),
    ]
    skills = pos.get("technicalTags", pos.get("skills", []))
    if isinstance(skills, list):
        parts.extend([s if isinstance(s, str) else s.get("name", "") for s in skills])
    return " ".join(filter(None, parts))


async def fetch_page(client: httpx.AsyncClient, page: int) -> dict:
    params = {"order": "recent", "page": page, "min_career": 0}
    try:
        resp = await client.get(PROGRAMMERS_API, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"프로그래머스 API 요청 실패 (page={page}): {e}")
        return {}


async def crawl_programmers() -> List[RawJob]:
    raw_jobs: List[RawJob] = []

    async with httpx.AsyncClient() as client:
        data = await fetch_page(client, 1)
        if not data:
            return raw_jobs

        positions = data.get("jobPositions", data.get("job_positions", []))
        total = data.get("totalCount", data.get("total_count", 0))

        logger.info(f"프로그래머스 총 공고 수: {total}, 이번 배치: {len(positions)}")

        def parse_pos(pos: dict):
            job_id = pos.get("id")
            if not job_id:
                return None
            company = pos.get("company", {})
            company_name = company.get("name", "") if isinstance(company, dict) else str(company)
            return RawJob(
                title=pos.get("name", pos.get("title", "")).strip(),
                company=company_name.strip(),
                url=PROGRAMMERS_JOB_URL.format(job_id=job_id),
                source="programmers",
                location=_parse_location(pos),
                experience=_parse_experience(pos),
                employment_type="정규직",
                raw_text=_parse_raw_text(pos),
            )

        for pos in positions:
            try:
                job = parse_pos(pos)
                if job:
                    raw_jobs.append(job)
            except Exception as e:
                logger.warning(f"프로그래머스 공고 파싱 오류: {e}")

        await asyncio.sleep(1)

        page_size = len(positions) or 20
        if total > page_size:
            max_pages = min((total // page_size) + 1, 5)
            for p in range(2, max_pages + 1):
                batch = await fetch_page(client, p)
                if not batch:
                    break
                for pos in batch.get("jobPositions", batch.get("job_positions", [])):
                    try:
                        job = parse_pos(pos)
                        if job:
                            raw_jobs.append(job)
                    except Exception as e:
                        logger.warning(f"프로그래머스 공고 파싱 오류: {e}")
                await asyncio.sleep(1)

    logger.info(f"프로그래머스 수집 완료: {len(raw_jobs)}건")

    if raw_jobs:
        async with AsyncSessionLocal() as session:
            await upsert_jobs(session, raw_jobs)

    return raw_jobs
