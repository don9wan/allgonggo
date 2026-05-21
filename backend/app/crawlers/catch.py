import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from typing import List
from app.crawlers.base import RawJob
from app.db.database import AsyncSessionLocal
from app.crawlers.db_writer import upsert_jobs

logger = logging.getLogger(__name__)

CATCH_API = "https://www.catch.co.kr/api/recruit/list"
CATCH_JOB_URL = "https://www.catch.co.kr/NCS/RecruitInfoDetails/{job_id}"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://www.catch.co.kr/",
}


def _parse_experience(pos: dict) -> str:
    career = pos.get("career", pos.get("careerNm", ""))
    if not career:
        return "경력무관"
    career = str(career).strip()
    if "신입" in career:
        return "신입"
    if "인턴" in career:
        return "인턴"
    if "경력" in career or "year" in career.lower():
        return career
    return "경력무관"


def _parse_employment_type(pos: dict) -> str:
    emp = pos.get("empType", pos.get("empTypeNm", "정규직"))
    if not emp:
        return "정규직"
    emp = str(emp)
    if "인턴" in emp:
        return "인턴"
    if "계약" in emp:
        return "계약직"
    return "정규직"


def _parse_location(pos: dict) -> str:
    loc = pos.get("locNm", pos.get("location", pos.get("addr", "")))
    return str(loc).strip() if loc else "미정"


def _parse_raw_text(pos: dict) -> str:
    parts = [
        pos.get("title", pos.get("recruitTitle", "")),
        pos.get("compNm", pos.get("company", "")),
        _parse_location(pos),
        pos.get("career", ""),
        pos.get("jobNm", ""),
    ]
    return " ".join(filter(None, [str(p) for p in parts]))


async def fetch_page(client: httpx.AsyncClient, page: int) -> dict:
    params = {
        "pageIndex": page,
        "pageSize": 50,
        "sortType": "LATEST",
        "jobType": "IT",
    }
    try:
        resp = await client.get(CATCH_API, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"캐치 API 요청 실패 (page={page}): {e}")
        return {}


async def crawl_catch() -> List[RawJob]:
    raw_jobs: List[RawJob] = []

    async with httpx.AsyncClient() as client:
        data = await fetch_page(client, 1)
        if not data:
            return raw_jobs

        items = (
            data.get("recruitList")
            or data.get("list")
            or data.get("data", {}).get("list", [])
            or []
        )
        total = (
            data.get("totalCnt")
            or data.get("totalCount")
            or data.get("data", {}).get("totalCnt", 0)
            or 0
        )

        logger.info(f"캐치 총 공고 수: {total}, 이번 배치: {len(items)}")

        for pos in items:
            try:
                job_id = pos.get("recruitSeq", pos.get("id", pos.get("seq")))
                if not job_id:
                    continue
                raw_jobs.append(RawJob(
                    title=str(pos.get("recruitTitle", pos.get("title", ""))).strip(),
                    company=str(pos.get("compNm", pos.get("company", ""))).strip(),
                    url=CATCH_JOB_URL.format(job_id=job_id),
                    source="catch",
                    location=_parse_location(pos),
                    experience=_parse_experience(pos),
                    employment_type=_parse_employment_type(pos),
                    raw_text=_parse_raw_text(pos),
                ))
            except Exception as e:
                logger.warning(f"캐치 공고 파싱 오류: {e}")

        await asyncio.sleep(1)

        page_size = len(items) or 50
        if total > page_size:
            max_pages = min((total // page_size) + 1, 4)
            for p in range(2, max_pages + 1):
                batch = await fetch_page(client, p)
                if not batch:
                    break
                batch_items = (
                    batch.get("recruitList")
                    or batch.get("list")
                    or batch.get("data", {}).get("list", [])
                    or []
                )
                for pos in batch_items:
                    try:
                        job_id = pos.get("recruitSeq", pos.get("id", pos.get("seq")))
                        if not job_id:
                            continue
                        raw_jobs.append(RawJob(
                            title=str(pos.get("recruitTitle", pos.get("title", ""))).strip(),
                            company=str(pos.get("compNm", pos.get("company", ""))).strip(),
                            url=CATCH_JOB_URL.format(job_id=job_id),
                            source="catch",
                            location=_parse_location(pos),
                            experience=_parse_experience(pos),
                            employment_type=_parse_employment_type(pos),
                            raw_text=_parse_raw_text(pos),
                        ))
                    except Exception as e:
                        logger.warning(f"캐치 공고 파싱 오류: {e}")
                await asyncio.sleep(1)

    logger.info(f"캐치 수집 완료: {len(raw_jobs)}건")

    if raw_jobs:
        async with AsyncSessionLocal() as session:
            await upsert_jobs(session, raw_jobs)

    return raw_jobs
