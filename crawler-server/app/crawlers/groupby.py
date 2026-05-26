import logging
from typing import List
from urllib.parse import quote

from cloakbrowser import launch_async

from app.crawlers.base import RawJob
from app.crawlers.browser import random_delay
from app.crawlers.db_writer import is_caught_up, upsert_jobs
from app.db.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

API_URL = "https://api.groupby.kr/startup-positions"
SITE_URL = "https://groupby.kr/"
LIMIT = 10
CAREER_TYPES = ["신입", "인턴"]


def _parse_job(item: dict, career_type: str) -> RawJob | None:
    try:
        title = (item.get("name") or "").strip()
        job_id = item.get("id")
        if not title or not job_id:
            return None

        startup = item.get("startup") or {}
        company = (startup.get("name") or "").strip()
        if not company:
            return None

        loc = item.get("location") or item.get("address") or ""
        location = (loc if isinstance(loc, str) else loc.get("name", "") if isinstance(loc, dict) else "").strip() or None
        raw_career = (item.get("careerType") or career_type).strip()
        experience = "경력무관" if raw_career == "무관" else raw_career
        employment_type = "인턴" if raw_career == "인턴" else "정규직"

        return RawJob(
            title=title,
            company=company,
            url=f"https://groupby.kr/positions/{job_id}",
            source="groupby",
            location=location,
            experience=experience,
            employment_type=employment_type,
            raw_text=f"{title} {company}".strip(),
        )
    except Exception as e:
        logger.warning(f"그룹바이 파싱 오류: {e}")
        return None


async def crawl_groupby():
    logger.info("그룹바이 크롤링 시작")
    seen_urls: set = set()
    all_jobs: List[RawJob] = []

    browser = await launch_async(headless=True, humanize=True)
    try:
        context = await browser.new_context()

        for career_type in CAREER_TYPES:
            # 사이트 진입으로 쿠키 획득
            page = await context.new_page()
            await page.goto(SITE_URL, wait_until="domcontentloaded")
            await random_delay()

            offset = 0
            while True:
                url = (
                    f"{API_URL}?careerTypes={quote(career_type)}"
                    f"&limit={LIMIT}&offset={offset}&orderBy=-updatedAt"
                )
                try:
                    resp = await context.request.get(
                        url,
                        headers={
                            "Accept": "*/*",
                            "Origin": "https://groupby.kr",
                            "Referer": "https://groupby.kr/",
                        },
                    )
                    data = await resp.json()
                except Exception as e:
                    logger.error(f"그룹바이 [{career_type}] offset={offset} 실패: {e}")
                    break

                inner = data.get("data") or {}
                items = inner.get("items", [])
                total = inner.get("total", 0)

                if not items:
                    break

                page_jobs = [j for item in items if (j := _parse_job(item, career_type)) is not None]

                for job in page_jobs:
                    if job.url not in seen_urls:
                        seen_urls.add(job.url)
                        all_jobs.append(job)

                async with AsyncSessionLocal() as session:
                    if await is_caught_up(session, page_jobs):
                        break

                offset += LIMIT
                if offset >= total:
                    break

                await random_delay()

            await page.close()
            logger.info(f"그룹바이 [{career_type}] 수집 완료")
            await random_delay()
    finally:
        await browser.close()

    logger.info(f"그룹바이 총 {len(all_jobs)}건 (dedup 후)")
    total_inserted = total_linked = 0
    if all_jobs:
        async with AsyncSessionLocal() as session:
            total_inserted, total_linked = await upsert_jobs(session, all_jobs)

    logger.info(f"그룹바이 완료 — 신규: {total_inserted}건, 소스 추가: {total_linked}건")
