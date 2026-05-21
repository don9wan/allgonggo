import asyncio
import logging
import httpx
from typing import List, Optional
from app.crawlers.base import RawJob
from app.db.database import AsyncSessionLocal
from app.crawlers.db_writer import upsert_jobs

logger = logging.getLogger(__name__)

JUMPIT_API = "https://jumpit.saramin.co.kr/api/positions"
JUMPIT_JOB_URL = "https://jumpit.saramin.co.kr/position/{job_id}"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://jumpit.saramin.co.kr/",
}


def _parse_experience(pos: dict) -> str:
    min_c = pos.get("minCareer", 0)
    max_c = pos.get("maxCareer", 0)
    if min_c == 0 and max_c == 0:
        return "경력무관"
    if min_c == 0:
        return "신입"
    return f"경력 {min_c}년 이상"


def _parse_location(pos: dict) -> str:
    work_place = pos.get("workPlace", "") or pos.get("address", "")
    return work_place.strip() if work_place else "미정"


def _parse_raw_text(pos: dict) -> str:
    parts = [
        pos.get("title", ""),
        pos.get("companyName", ""),
        pos.get("workPlace", ""),
    ]
    tech_stacks = pos.get("techStacks", [])
    if isinstance(tech_stacks, list):
        parts.extend([ts if isinstance(ts, str) else ts.get("name", "") for ts in tech_stacks])
    return " ".join(filter(None, parts))


async def fetch_page(client: httpx.AsyncClient, page: int) -> dict:
    params = {"sort": "rsp_rate", "page": page, "highlight": "false"}
    try:
        resp = await client.get(JUMPIT_API, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"점핏 API 요청 실패 (page={page}): {e}")
        return {}


async def crawl_jumpit() -> List[RawJob]:
    raw_jobs: List[RawJob] = []

    async with httpx.AsyncClient() as client:
        data = await fetch_page(client, 1)
        if not data:
            return raw_jobs

        result = data.get("result", data)
        positions = result.get("positions", result.get("position", []))
        total_count = result.get("totalCount", result.get("total_count", 0))

        logger.info(f"점핏 총 공고 수: {total_count}, 이번 배치: {len(positions)}")

        for pos in positions:
            try:
                job_id = pos.get("id")
                if not job_id:
                    continue
                raw_jobs.append(RawJob(
                    title=pos.get("title", "").strip(),
                    company=pos.get("companyName", pos.get("company_name", "")).strip(),
                    url=JUMPIT_JOB_URL.format(job_id=job_id),
                    source="jumpit",
                    location=_parse_location(pos),
                    experience=_parse_experience(pos),
                    employment_type="정규직",
                    raw_text=_parse_raw_text(pos),
                ))
            except Exception as e:
                logger.warning(f"점핏 공고 파싱 오류: {e}")

        await asyncio.sleep(1)

        page_size = len(positions) or 20
        if total_count > page_size:
            max_pages = min((total_count // page_size) + 1, 5)
            for p in range(2, max_pages + 1):
                batch = await fetch_page(client, p)
                if not batch:
                    break
                result = batch.get("result", batch)
                for pos in result.get("positions", result.get("position", [])):
                    try:
                        job_id = pos.get("id")
                        if not job_id:
                            continue
                        raw_jobs.append(RawJob(
                            title=pos.get("title", "").strip(),
                            company=pos.get("companyName", pos.get("company_name", "")).strip(),
                            url=JUMPIT_JOB_URL.format(job_id=job_id),
                            source="jumpit",
                            location=_parse_location(pos),
                            experience=_parse_experience(pos),
                            employment_type="정규직",
                            raw_text=_parse_raw_text(pos),
                        ))
                    except Exception as e:
                        logger.warning(f"점핏 공고 파싱 오류: {e}")
                await asyncio.sleep(1)

    logger.info(f"점핏 수집 완료: {len(raw_jobs)}건")

    if raw_jobs:
        async with AsyncSessionLocal() as session:
            await upsert_jobs(session, raw_jobs)

    return raw_jobs
