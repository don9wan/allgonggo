import json
import logging
import re
from typing import List, Optional

import aiohttp

from app.crawlers.base import RawJob
from app.crawlers.browser import random_delay
from app.crawlers.db_writer import is_caught_up, upsert_jobs
from app.db.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

RECRUIT_BASE = (
    "https://linkareer.com/list/recruit"
    "?filterBy_activityTypeID=5"
    "&filterBy_categoryIDs=63&filterBy_categoryIDs=58"
    "&filterBy_categoryIDs=54&filterBy_categoryIDs=53"
    "&filterBy_jobTypes=NEW&filterBy_jobTypes=INTERN&filterBy_jobTypes=CONTRACT"
    "&filterBy_status=OPEN&orderBy_direction=DESC&orderBy_field=RECENT&page={page}"
)

INTERN_BASE = (
    "https://linkareer.com/list/intern"
    "?filterBy_activityTypeID=5"
    "&filterBy_categoryIDs=58&filterBy_categoryIDs=54"
    "&filterBy_categoryIDs=53&filterBy_categoryIDs=63"
    "&filterBy_jobTypes=INTERN"
    "&filterBy_status=OPEN&orderBy_direction=DESC&orderBy_field=RECENT&page={page}"
)

PAGE_SIZE = 20

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://linkareer.com/",
}


def _extract_next_data(html: str) -> Optional[dict]:
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _parse_jobs_from_apollo(next_data: dict) -> tuple[List[RawJob], int]:
    try:
        apollo = next_data["props"]["pageProps"]["__APOLLO_STATE__"]
    except (KeyError, TypeError):
        return [], 0

    root_query = apollo.get("ROOT_QUERY", {})
    node_refs: List[str] = []
    total_count = 0

    for k, v in root_query.items():
        if k.startswith("activities") and isinstance(v, dict) and "totalCount" in v:
            total_count = v.get("totalCount", 0)
            node_refs = [n["__ref"] for n in v.get("nodes", []) if isinstance(n, dict) and "__ref" in n]
            break

    jobs: List[RawJob] = []
    for ref in node_refs:
        activity = apollo.get(ref, {})
        if not activity:
            continue
        job = _parse_activity(activity, apollo)
        if job:
            jobs.append(job)

    return jobs, total_count


def _parse_activity(activity: dict, apollo: dict) -> Optional[RawJob]:
    try:
        act_id = activity.get("id", "")
        title = (activity.get("title") or "").strip()
        company = (activity.get("organizationName") or "").strip()
        if not title or not company or not act_id:
            return None

        location_parts = []
        for regions_key, obj_list in [("regions", activity.get("regions", [])), ("regionDistricts", activity.get("regionDistricts", []))]:
            if obj_list and isinstance(obj_list[0], dict):
                ref = obj_list[0].get("__ref", "")
                name = apollo.get(ref, {}).get("name", "")
                if name:
                    location_parts.append(name)
        location = " ".join(location_parts) or None

        job_types = activity.get("jobTypes", [])
        if "NEW" in job_types:
            experience = "신입"
        elif "INTERN" in job_types:
            experience = "인턴"
        elif "CONTRACT" in job_types:
            experience = "경력무관"
        else:
            experience = None

        employment_type = "인턴" if ("INTERN" in job_types and "NEW" not in job_types) else "정규직"

        return RawJob(
            title=title,
            company=company,
            url=f"https://linkareer.com/activity/{act_id}",
            source="linkareer",
            location=location,
            experience=experience,
            employment_type=employment_type,
            raw_text=f"{title} {company}".strip(),
        )
    except Exception as e:
        logger.warning(f"링커리어 activity 파싱 오류: {e}")
        return None


async def _crawl_url_template(http: aiohttp.ClientSession, url_template: str, label: str) -> List[RawJob]:
    results: List[RawJob] = []
    page_num = 1

    while True:
        url = url_template.format(page=page_num)
        try:
            async with http.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    logger.error(f"링커리어 [{label}] 페이지 {page_num} HTTP {resp.status}")
                    break
                html = await resp.text()
        except Exception as e:
            logger.error(f"링커리어 [{label}] 페이지 {page_num} 로드 실패: {e}")
            break

        next_data = _extract_next_data(html)
        if not next_data:
            logger.warning(f"링커리어 [{label}] 페이지 {page_num} __NEXT_DATA__ 없음")
            break

        page_jobs, total_count = _parse_jobs_from_apollo(next_data)
        if not page_jobs:
            break

        results.extend(page_jobs)
        total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE
        logger.info(f"[linkareer][{label}] p{page_num}/{total_pages} — 배치 {len(page_jobs)}건 / 누적 {len(results)}건")

        async with AsyncSessionLocal() as session:
            if await is_caught_up(session, page_jobs):
                logger.info(f"[linkareer][{label}] 최신 공고 따라잡음, 조기 종료")
                break

        if page_num >= total_pages:
            break

        page_num += 1
        await random_delay()

    logger.info(f"[linkareer][{label}] 완료 — {len(results)}건")
    return results


async def crawl_linkareer():
    logger.info("링커리어 크롤링 시작")

    async with aiohttp.ClientSession(headers=_HEADERS) as http:
        recruit_jobs = await _crawl_url_template(http, RECRUIT_BASE, "신입/계약")
        await random_delay()
        intern_jobs = await _crawl_url_template(http, INTERN_BASE, "인턴")

    seen_urls: set = set()
    all_jobs: List[RawJob] = []
    for job in recruit_jobs + intern_jobs:
        if job.url not in seen_urls:
            seen_urls.add(job.url)
            all_jobs.append(job)

    logger.info(f"링커리어 총 {len(all_jobs)}건 (dedup 후)")
    total_inserted = total_linked = 0
    if all_jobs:
        async with AsyncSessionLocal() as session:
            total_inserted, total_linked = await upsert_jobs(session, all_jobs)

    logger.info(f"링커리어 완료 — 신규: {total_inserted}건, 소스 추가: {total_linked}건")
