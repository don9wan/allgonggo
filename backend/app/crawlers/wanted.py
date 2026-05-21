import asyncio
import logging
import httpx
from typing import List, Optional
from app.crawlers.base import RawJob
from app.db.database import AsyncSessionLocal
from app.crawlers.db_writer import upsert_jobs

logger = logging.getLogger(__name__)

WANTED_API_URL = "https://www.wanted.co.kr/api/chaos/jobs/v1/wanted"
WANTED_JOB_URL = "https://www.wanted.co.kr/wd/{job_id}"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Wanted-User-Agent": "user-web",
    "Referer": "https://www.wanted.co.kr/",
}

CATEGORY_TAGS = [
    518,   # 개발
    873,   # 데이터 엔지니어
    655,   # 프론트엔드
    660,   # 백엔드
    876,   # DevOps/인프라
    872,   # 머신러닝
    1024,  # 안드로이드
    1025,  # iOS
    659,   # 풀스택
    674,   # 웹 개발자
    1026,  # 임베디드/시스템
    900,   # QA
    671,   # 보안
    1027,  # 데이터 분석가
    1037,  # PM
    10110, # 디자이너
]


def _parse_employment_type(position: dict) -> Optional[str]:
    tags = position.get("tags", [])
    for tag in tags:
        name = tag.get("title", "")
        if "인턴" in name:
            return "인턴"
        if "계약" in name:
            return "계약직"
    return "정규직"


def _parse_experience(position: dict) -> str:
    years_of_experience = position.get("years_of_experience", "")
    if not years_of_experience:
        return "경력무관"
    return str(years_of_experience)


def _parse_location(position: dict) -> str:
    address = position.get("address", {})
    location = address.get("location", "") if address else ""
    return location or "미정"


def _parse_raw_text(position: dict) -> str:
    parts = [
        position.get("title", ""),
        position.get("company_name", ""),
        position.get("address", {}).get("location", "") if position.get("address") else "",
    ]
    tags = position.get("tags", [])
    for tag in tags:
        parts.append(tag.get("title", ""))
    return " ".join(filter(None, parts))


async def fetch_wanted_jobs(client: httpx.AsyncClient, offset: int = 0) -> dict:
    params = {
        "country": "kr",
        "tag_type_ids": ",".join(str(t) for t in CATEGORY_TAGS[:4]),
        "limit": 100,
        "offset": offset,
        "years_of_experience": "",
    }
    try:
        resp = await client.get(WANTED_API_URL, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"원티드 API 요청 실패 (offset={offset}): {e}")
        return {}


async def crawl_wanted() -> List[RawJob]:
    raw_jobs: List[RawJob] = []

    async with httpx.AsyncClient() as client:
        data = await fetch_wanted_jobs(client, offset=0)
        if not data:
            return raw_jobs

        positions = data.get("data", [])
        total = data.get("total", 0)
        logger.info(f"원티드 총 공고 수: {total}, 이번 배치: {len(positions)}")

        for pos in positions:
            try:
                job_id = pos.get("id")
                if not job_id:
                    continue
                raw_jobs.append(RawJob(
                    title=pos.get("title", "").strip(),
                    company=pos.get("company_name", "").strip(),
                    url=WANTED_JOB_URL.format(job_id=job_id),
                    source="wanted",
                    location=_parse_location(pos),
                    experience=_parse_experience(pos),
                    employment_type=_parse_employment_type(pos),
                    raw_text=_parse_raw_text(pos),
                ))
            except Exception as e:
                logger.warning(f"공고 파싱 오류: {e}")
                continue

        await asyncio.sleep(1)

        if total > 100:
            batches = min((total // 100), 4)
            for i in range(1, batches + 1):
                batch = await fetch_wanted_jobs(client, offset=i * 100)
                for pos in batch.get("data", []):
                    try:
                        job_id = pos.get("id")
                        if not job_id:
                            continue
                        raw_jobs.append(RawJob(
                            title=pos.get("title", "").strip(),
                            company=pos.get("company_name", "").strip(),
                            url=WANTED_JOB_URL.format(job_id=job_id),
                            source="wanted",
                            location=_parse_location(pos),
                            experience=_parse_experience(pos),
                            employment_type=_parse_employment_type(pos),
                            raw_text=_parse_raw_text(pos),
                        ))
                    except Exception as e:
                        logger.warning(f"공고 파싱 오류: {e}")
                        continue
                await asyncio.sleep(1)

    logger.info(f"원티드 수집 완료: {len(raw_jobs)}건")

    if raw_jobs:
        async with AsyncSessionLocal() as session:
            await upsert_jobs(session, raw_jobs)

    return raw_jobs
