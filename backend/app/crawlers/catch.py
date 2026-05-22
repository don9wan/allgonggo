import asyncio
import logging
from typing import List, Optional
from app.crawlers.base import RawJob
from app.db.database import AsyncSessionLocal
from app.crawlers.db_writer import upsert_jobs, is_caught_up

logger = logging.getLogger(__name__)

BASE_URL = "https://www.catch.co.kr"
JOB_URL = f"{BASE_URL}/NCS/RecruitInfoDetails/{{job_id}}"
MAX_PAGES = 10
PAGE_SIZE = 30

IT_DEPTHS = {
    "웹개발", "응용프로그램개발", "ERP/시스템개발/설계",
    "네트워크/서버/보안", "DBA/데이터베이스",
    "웹기획/PM/웹마케팅", "HTML/퍼블리싱/UI개발", "QA/테스트/검증",
    "게임", "빅데이터/AI", "정보기술/소프트웨어",
}


def _is_it_job(pos: dict) -> bool:
    depth = pos.get("Depth", "")
    depths = {d.strip() for d in depth.split(",")}
    return bool(depths & IT_DEPTHS)


def _is_entry_level(pos: dict) -> bool:
    career = pos.get("CareerGubunCode", "")
    return any(c in career for c in ["신입", "인턴", "무관"])


def _parse_experience(pos: dict) -> str:
    career = pos.get("CareerGubunCode", "")
    if "인턴" in career:
        return "인턴"
    if "신입" in career:
        return "신입"
    return "경력무관"


def _parse_location(pos: dict) -> str:
    area = pos.get("WorkArea", "") or ""
    return area.strip() or "미정"


def _parse_employment_type(pos: dict) -> str:
    gubun = pos.get("GubunCode", "") or ""
    career = pos.get("CareerGubunCode", "") or ""
    if "인턴" in gubun or "인턴" in career:
        return "인턴"
    if "계약" in gubun:
        return "계약직"
    return "정규직"


def _parse_raw_text(pos: dict) -> str:
    parts = [
        pos.get("RecruitTitle", ""),
        pos.get("CompName", ""),
        _parse_location(pos),
        pos.get("Depth", ""),
    ]
    return " ".join(filter(None, [str(p) for p in parts]))


def _to_raw_job(pos: dict) -> Optional[RawJob]:
    job_id = pos.get("RecruitID")
    title = str(pos.get("RecruitTitle", "")).strip()
    company = str(pos.get("CompName", "")).strip()
    if not job_id or not title or not company:
        return None
    if not _is_it_job(pos):
        return None
    if not _is_entry_level(pos):
        return None
    return RawJob(
        title=title,
        company=company,
        url=JOB_URL.format(job_id=job_id),
        source="catch",
        location=_parse_location(pos),
        experience=_parse_experience(pos),
        employment_type=_parse_employment_type(pos),
        raw_text=_parse_raw_text(pos),
    )


async def crawl_catch() -> List[RawJob]:
    """
    Playwright로 catch.co.kr 세션 확보 후
    page.evaluate()로 same-origin API 호출 → Cloudflare WAF 우회.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("playwright 미설치: pip install playwright && playwright install chromium")
        return []

    all_items: List[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ko-KR",
        )
        page = await ctx.new_page()

        # 메인 페이지로 Cloudflare 세션/쿠키 확보
        try:
            await page.goto(BASE_URL, wait_until="networkidle", timeout=20000)
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"캐치 메인 페이지 로드 실패: {e}")
            await browser.close()
            return []

        if page == 1:
            logger.info("캐치 세션 확보 완료, API 수집 시작")

        for page_num in range(1, MAX_PAGES + 1):
            try:
                result = await page.evaluate(f"""
                async () => {{
                    const resp = await fetch(
                        '/api/v1.0/recruit/information/getRecruitList'
                        + '?Career=1&Sort=0&curpage={page_num}&pageSize={PAGE_SIZE}&onRecruitYN=Y',
                        {{ headers: {{ Accept: 'application/json' }} }}
                    );
                    return await resp.json();
                }}
                """)
            except Exception as e:
                logger.warning(f"캐치 p={page_num} evaluate 오류: {e}")
                break

            items = result.get("recruitData", []) if isinstance(result, dict) else []
            if not items:
                break

            if page_num == 1:
                total = result.get("intTotalRecordCount", 0)
                logger.info(f"캐치 신입 총 {total}건 → IT 필터링 중")

            all_items.extend(items)

            if len(items) < PAGE_SIZE:
                break

            page_jobs = [j for item in items if (j := _to_raw_job(item))]
            try:
                async with AsyncSessionLocal() as session:
                    if await is_caught_up(session, page_jobs):
                        break
            except Exception:
                pass

        await browser.close()

    jobs: List[RawJob] = [j for item in all_items if (j := _to_raw_job(item))]

    logger.info(f"캐치 수집 완료: {len(jobs)}건 (신입/인턴 IT)")
    if jobs:
        async with AsyncSessionLocal() as session:
            await upsert_jobs(session, jobs)

    return jobs
