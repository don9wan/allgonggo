import json
import logging
import re
from typing import List, Optional

from cloakbrowser import launch_async

from app.crawlers.base import RawJob
from app.crawlers.browser import random_delay
from app.crawlers.db_writer import is_caught_up, upsert_jobs
from app.db.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

BASE_URL = (
    "https://jasoseol.com/search"
    "?division=1,3"
    "&dutyGroupIds=106,108,109,110,111,112,113,114,115,116,117,118,119,120,121,122,123,124,"
    "125,126,127,128,129,130,131,134,135,136,137,138,139,140,141,142,143,144,160,164,165,"
    "166,167,168,169,170,171,172,173,174,175,176,177,178,179,180,181,182,238,239,240,241,"
    "242,243,244,245,246"
    "&excludeClosed=true"
    "&page={page}"
)

PAGE_SIZE = 20


def _extract_next_data(html: str) -> Optional[dict]:
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _parse_job(item: dict) -> Optional[RawJob]:
    try:
        job_id = item.get("id")
        title = (item.get("title") or "").strip()
        company = (item.get("name") or "").strip()
        if not title or not company or not job_id:
            return None

        employments = item.get("employments", [])
        experience = None
        employment_type = None
        field_texts = []

        if employments:
            first = employments[0]
            divisions = first.get("division", [])
            has_new = 1 in divisions
            has_intern = 3 in divisions
            if has_new and has_intern:
                experience = "신입,인턴"
            elif has_intern:
                experience = "인턴"
            else:
                experience = "신입"

            work_type = (first.get("work_type") or "").strip()
            employment_type = "정규직" if work_type == "풀타임" else (work_type or None)

            for emp in employments:
                field = (emp.get("field") or "").strip()
                if field:
                    field_texts.append(field)

        return RawJob(
            title=title,
            company=company,
            url=f"https://jasoseol.com/recruit/{job_id}",
            source="jasoseol",
            location=None,
            experience=experience,
            employment_type=employment_type,
            raw_text=f"{title} {company} {' '.join(field_texts)}".strip(),
        )
    except Exception as e:
        logger.warning(f"자소설닷컴 파싱 오류: {e}")
        return None


async def crawl_jasoseol():
    logger.info("자소설닷컴 크롤링 시작")
    all_jobs: List[RawJob] = []

    browser = await launch_async(headless=True, humanize=True)
    try:
        context = await browser.new_context()
        page = await context.new_page()
        page_num = 1

        while True:
            url = BASE_URL.format(page=page_num)
            try:
                await page.goto(url, wait_until="networkidle")
            except Exception as e:
                logger.error(f"자소설닷컴 페이지 {page_num} 로드 실패: {e}")
                break

            next_data = _extract_next_data(await page.content())
            if not next_data:
                logger.warning(f"자소설닷컴 페이지 {page_num} __NEXT_DATA__ 없음")
                break

            try:
                queries = next_data["props"]["pageProps"]["dehydratedState"]["queries"]
                result = queries[0]["state"]["data"]
                items = result.get("data", [])
                total_count = result.get("totalCount", 0)
            except (KeyError, IndexError, TypeError) as e:
                logger.warning(f"자소설닷컴 페이지 {page_num} 데이터 추출 실패: {e}")
                break

            if not items:
                break

            page_jobs = [j for item in items if (j := _parse_job(item)) is not None]
            all_jobs.extend(page_jobs)

            async with AsyncSessionLocal() as session:
                if await is_caught_up(session, page_jobs):
                    break

            total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE
            if page_num >= total_pages:
                break

            page_num += 1
            await random_delay()

    finally:
        await browser.close()

    logger.info(f"자소설닷컴 총 {len(all_jobs)}건 수집")
    total_inserted = total_linked = 0
    if all_jobs:
        async with AsyncSessionLocal() as session:
            total_inserted, total_linked = await upsert_jobs(session, all_jobs)

    logger.info(f"자소설닷컴 완료 — 신규: {total_inserted}건, 소스 추가: {total_linked}건")
