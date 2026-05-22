import asyncio
import logging
from typing import List, Optional
from app.crawlers.base import RawJob
from app.db.database import AsyncSessionLocal
from app.crawlers.db_writer import upsert_jobs, is_caught_up

logger = logging.getLogger(__name__)

BASE_URL = "https://groupby.kr"
JOB_URL = f"{BASE_URL}/positions/{{job_id}}"

# careerType values from API: 신입=신입, 무관=무관, 인턴=인턴, 경력=경력
ENTRY_CAREER_TYPES = {"신입", "무관", "인턴"}

# IT positionType IDs from base-info API
IT_POSITION_TYPE_IDS = {
    1,   # 프론트엔드
    2,   # 백엔드
    3,   # iOS
    4,   # Android
    5,   # 크로스플랫폼앱
    6,   # DevOps
    7,   # AI
    8,   # 데이터엔지니어
    9,   # 게임클라이언트
    10,  # 게임서버
    11,  # 풀스택
    33,  # 소프트웨어엔지니어
    37,  # QA엔지니어
    59,  # 정보보안
}

# Pages to visit for interception (각 페이지가 다른 careerType 쿼리를 트리거)
FILTER_URLS = [
    f"{BASE_URL}/positions",
    f"{BASE_URL}/positions?career=신입",
    f"{BASE_URL}/positions?career=무관",
    f"{BASE_URL}/positions?career=인턴",
]


def _is_it_job(pos: dict) -> bool:
    position_type = pos.get("positionType") or {}
    type_id = position_type.get("id") if isinstance(position_type, dict) else None
    return type_id in IT_POSITION_TYPE_IDS


def _is_entry_level(pos: dict) -> bool:
    career = pos.get("careerType") or ""
    if isinstance(career, dict):
        career = career.get("name", "")
    return any(t in career for t in ENTRY_CAREER_TYPES)


def _parse_experience(pos: dict) -> str:
    career = pos.get("careerType") or ""
    if isinstance(career, dict):
        career = career.get("name", "")
    if "인턴" in career:
        return "인턴"
    if "신입" in career:
        return "신입"
    return "경력무관"


def _parse_location(pos: dict) -> str:
    address = pos.get("address") or pos.get("location") or ""
    if isinstance(address, dict):
        address = address.get("city") or address.get("name") or ""
    return str(address).strip() or "미정"


def _parse_employment_type(pos: dict) -> str:
    career = pos.get("careerType") or ""
    if isinstance(career, dict):
        career = career.get("name", "")
    if "인턴" in career:
        return "인턴"
    return "정규직"


def _parse_raw_text(pos: dict) -> str:
    position_type = pos.get("positionType") or {}
    type_name = position_type.get("name", "") if isinstance(position_type, dict) else ""
    company = pos.get("company") or {}
    company_name = company.get("name", "") if isinstance(company, dict) else str(company)
    parts = [
        pos.get("title", ""),
        company_name,
        _parse_location(pos),
        type_name,
    ]
    return " ".join(filter(None, [str(p) for p in parts]))


def _to_raw_job(pos: dict) -> Optional[RawJob]:
    job_id = pos.get("id")
    title = str(pos.get("title", "")).strip()
    company = pos.get("company") or {}
    company_name = company.get("name", "").strip() if isinstance(company, dict) else str(company).strip()

    if not job_id or not title or not company_name:
        return None
    if not _is_it_job(pos):
        return None
    if not _is_entry_level(pos):
        return None

    return RawJob(
        title=title,
        company=company_name,
        url=JOB_URL.format(job_id=job_id),
        source="groupby",
        location=_parse_location(pos),
        experience=_parse_experience(pos),
        employment_type=_parse_employment_type(pos),
        raw_text=_parse_raw_text(pos),
    )


async def _scrape_via_playwright() -> List[dict]:
    """Playwright로 groupby 페이지를 열고 API 응답을 가로챔."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("playwright 미설치: pip install playwright && playwright install chromium")
        return []

    captured_items: List[dict] = []
    seen_ids: set = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ko-KR",
            viewport={"width": 1280, "height": 800},
        )
        page = await ctx.new_page()

        captured_pages: List[dict] = []
        done_event = asyncio.Event()

        async def on_response(response):
            url = response.url
            if "startup-positions" not in url:
                return
            if response.status != 200:
                return
            try:
                body = await response.json()
                data = body.get("data") or {}
                items = data.get("items") or data.get("positions") or []
                total = data.get("total") or data.get("totalCount") or 0
                if items:
                    captured_pages.append({"url": url, "items": items, "total": total})
                    logger.debug(f"그룹바이 캡처: {url} → {len(items)}건 (total={total})")
            except Exception as e:
                logger.debug(f"그룹바이 응답 파싱 실패: {e}")

        page.on("response", on_response)

        for filter_url in FILTER_URLS:
            captured_pages.clear()
            try:
                await page.goto(filter_url, wait_until="networkidle", timeout=20000)
                await asyncio.sleep(2)

                for capture in captured_pages:
                    for item in capture["items"]:
                        item_id = item.get("id")
                        if item_id and item_id not in seen_ids:
                            seen_ids.add(item_id)
                            captured_items.append(item)

                # 스크롤 → 추가 페이지 로드
                prev_count = len(seen_ids)
                for _ in range(5):
                    captured_pages.clear()
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(2)
                    for capture in captured_pages:
                        for item in capture["items"]:
                            item_id = item.get("id")
                            if item_id and item_id not in seen_ids:
                                seen_ids.add(item_id)
                                captured_items.append(item)
                    if len(seen_ids) == prev_count:
                        break
                    prev_count = len(seen_ids)

            except Exception as e:
                logger.warning(f"그룹바이 페이지 로드 실패 ({filter_url}): {e}")

        await browser.close()

    return captured_items


async def crawl_groupby() -> List[RawJob]:
    raw_items = await _scrape_via_playwright()

    jobs: List[RawJob] = []
    for item in raw_items:
        j = _to_raw_job(item)
        if j:
            jobs.append(j)

    # URL 중복 제거 (혹시 필터 URL들 간 중복)
    seen = set()
    unique_jobs = []
    for j in jobs:
        if j.url not in seen:
            seen.add(j.url)
            unique_jobs.append(j)

    logger.info(f"그룹바이 수집 완료: {len(unique_jobs)}건 (신입/인턴/경력무관 IT)")
    if unique_jobs:
        async with AsyncSessionLocal() as session:
            await upsert_jobs(session, unique_jobs)

    return unique_jobs
