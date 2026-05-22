import logging
import httpx
from typing import List, Optional
from app.crawlers.base import RawJob
from app.crawlers.utils import SafeClient
from app.db.database import AsyncSessionLocal
from app.crawlers.db_writer import upsert_jobs, is_caught_up

logger = logging.getLogger(__name__)

BASE_URL = "https://www.wanted.co.kr"
API_URL = f"{BASE_URL}/api/chaos/jobs/v1/wanted"
JOB_URL = "https://www.wanted.co.kr/wd/{job_id}"

CATEGORY_TAGS = [518, 873, 655, 660, 876, 872, 1024, 1025, 659, 674]
MAX_PAGES = 5


def _parse_employment_type(pos: dict) -> str:
    for tag in pos.get("tags", []):
        name = tag.get("title", "")
        if "인턴" in name:
            return "인턴"
        if "계약" in name:
            return "계약직"
    return "정규직"


def _parse_experience(pos: dict) -> str:
    exp = pos.get("years_of_experience", "")
    return str(exp) if exp else "경력무관"


def _parse_location(pos: dict) -> str:
    addr = pos.get("address") or {}
    return addr.get("location", "").strip() or "미정"


def _parse_raw_text(pos: dict) -> str:
    parts = [
        pos.get("title", ""),
        pos.get("company_name", ""),
        (pos.get("address") or {}).get("location", ""),
        *[t.get("title", "") for t in pos.get("tags", [])],
    ]
    return " ".join(filter(None, parts))


def _to_raw_job(pos: dict) -> Optional[RawJob]:
    job_id = pos.get("id")
    title = pos.get("title", "").strip()
    company = pos.get("company_name", "").strip()
    if not job_id or not title or not company:
        return None
    return RawJob(
        title=title,
        company=company,
        url=JOB_URL.format(job_id=job_id),
        source="wanted",
        location=_parse_location(pos),
        experience=_parse_experience(pos),
        employment_type=_parse_employment_type(pos),
        raw_text=_parse_raw_text(pos),
    )


async def crawl_wanted() -> List[RawJob]:
    safe = SafeClient(BASE_URL, min_delay=2.0, max_delay=5.0)
    all_jobs: List[RawJob] = []

    async with httpx.AsyncClient(follow_redirects=True) as client:
        await safe.setup(client)

        extra = {"Referer": f"{BASE_URL}/", "Wanted-User-Agent": "user-web"}

        for page in range(MAX_PAGES):
            offset = page * 100
            data = await safe.get(
                client,
                API_URL,
                params={
                    "country": "kr",
                    "tag_type_ids": ",".join(str(t) for t in CATEGORY_TAGS),
                    "limit": 100,
                    "offset": offset,
                },
                extra_headers=extra,
            )

            if not data:
                logger.warning(f"원티드 페이지 {page+1} 응답 없음 → 중단")
                break

            positions = data.get("data", [])
            if not positions:
                break

            page_jobs = [j for pos in positions if (j := _to_raw_job(pos))]
            all_jobs.extend(page_jobs)

            if page == 0:
                total = data.get("total", 0)
                logger.info(f"원티드 총 {total}건, 1페이지 {len(page_jobs)}건")

            # 이전 크롤링 시점까지 따라잡았는지 확인
            async with AsyncSessionLocal() as session:
                if await is_caught_up(session, page_jobs):
                    break

            if len(positions) < 100:
                break

    logger.info(f"원티드 수집 완료: {len(all_jobs)}건")
    if all_jobs:
        async with AsyncSessionLocal() as session:
            await upsert_jobs(session, all_jobs)

    return all_jobs
