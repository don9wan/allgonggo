import logging
from typing import List

from app.crawlers.base import RawJob
from app.crawlers.browser import launch_browser, random_delay
from app.crawlers.db_writer import is_caught_up, upsert_jobs
from app.db.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

CATEGORIES = {
    "경영·비즈니스": 507,
    "개발": 518,
    "마케팅·광고": 523,
    "디자인": 511,
}

BASE_URL = "https://www.wanted.co.kr/api/v4/jobs"
SITE_URL = "https://www.wanted.co.kr/"


def _build_api_url(tag_type_id: int, offset: int) -> str:
    return (
        f"{BASE_URL}?country=kr&locations=all&job_sort=job.latest_order"
        f"&years=0"
        f"&employment_types=job.employment_type.intern"
        f"&employment_types=job.employment_type.regular"
        f"&employment_types=job.employment_type.contract"
        f"&tag_type_ids={tag_type_id}&limit=20&offset={offset}"
    )


def _parse_job(item: dict) -> RawJob | None:
    try:
        title = item.get("position", "").strip()
        company = (item.get("company") or {}).get("name", "").strip()
        job_id = item.get("id")
        if not title or not company or not job_id:
            return None

        address = item.get("address") or {}
        parts = [address.get("location", ""), address.get("district", "")]
        location = " ".join(p for p in parts if p).strip() or None

        # 고용형태: API 응답의 employment_type.code 필드 파싱
        emp_code = ((item.get("employment_type") or {}).get("code") or "")
        if "intern" in emp_code:
            employment_type = "인턴"
        elif "contract" in emp_code:
            employment_type = "계약직"
        else:
            employment_type = "정규직"

        url = f"https://www.wanted.co.kr/wd/{job_id}"
        return RawJob(
            title=title,
            company=company,
            url=url,
            source="wanted",
            location=location,
            experience="신입",  # years=0 파라미터로 신입만 수집
            employment_type=employment_type,
            raw_text=f"{title} {company} {location or ''}".strip(),
        )
    except Exception as e:
        logger.warning(f"원티드 파싱 오류: {e}")
        return None


async def crawl_wanted():
    logger.info("원티드 크롤링 시작")
    total_inserted = total_linked = 0

    browser = await launch_browser()
    try:
        context = await browser.new_context()

        for category_name, tag_type_id in CATEGORIES.items():
            category_jobs: List[RawJob] = []

            # 사이트 진입으로 쿠키 획득
            page = await context.new_page()
            await page.goto(SITE_URL, wait_until="domcontentloaded")
            await random_delay()

            offset = 0
            while True:
                url = _build_api_url(tag_type_id, offset)
                try:
                    resp = await context.request.get(
                        url,
                        headers={
                            "Accept": "application/json",
                            "Referer": f"https://www.wanted.co.kr/wdlist/{tag_type_id}",
                        },
                    )
                    data = await resp.json()
                except Exception as e:
                    logger.error(f"원티드 [{category_name}] offset={offset} 실패: {e}")
                    break

                items = data.get("data", [])
                if not items:
                    break

                page_jobs = [j for item in items if (j := _parse_job(item)) is not None]
                category_jobs.extend(page_jobs)

                async with AsyncSessionLocal() as session:
                    if await is_caught_up(session, page_jobs):
                        break

                if data.get("links", {}).get("next") is None:
                    break

                offset += 20
                await random_delay()

            await page.close()
            logger.info(f"원티드 [{category_name}] {len(category_jobs)}건 수집")

            if category_jobs:
                async with AsyncSessionLocal() as session:
                    ins, lnk = await upsert_jobs(session, category_jobs)
                total_inserted += ins
                total_linked += lnk

            await random_delay()
    finally:
        await browser.close()

    logger.info(f"원티드 완료 — 신규: {total_inserted}건, 소스 추가: {total_linked}건")
