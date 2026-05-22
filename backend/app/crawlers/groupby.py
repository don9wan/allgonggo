import asyncio
import logging
from typing import List, Optional
from app.crawlers.base import RawJob
from app.db.database import AsyncSessionLocal
from app.crawlers.db_writer import upsert_jobs, is_caught_up

logger = logging.getLogger(__name__)

BASE_URL = "https://groupby.kr"
API_BASE = "https://api.groupby.kr"
JOB_URL = f"{BASE_URL}/positions/{{job_id}}"

BATCH_SIZE = 20
MAX_BATCHES = 20  # 최대 400건

ENTRY_CAREER_TYPES = {"신입", "무관", "인턴"}

# positionTypes[].id 기준 IT 직군 (base-info API 확인)
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


def _is_it_job(pos: dict) -> bool:
    for pt in pos.get("positionTypes") or []:
        if pt.get("id") in IT_POSITION_TYPE_IDS:
            return True
    return False


def _is_entry_level(pos: dict) -> bool:
    career = pos.get("careerType") or ""
    return any(t in career for t in ENTRY_CAREER_TYPES)


def _parse_experience(pos: dict) -> str:
    career = pos.get("careerType") or ""
    if "인턴" in career:
        return "인턴"
    if "신입" in career:
        return "신입"
    return "경력무관"


def _parse_location(pos: dict) -> str:
    loc = pos.get("location") or pos.get("address") or ""
    if isinstance(loc, dict):
        loc = loc.get("city") or loc.get("name") or ""
    return str(loc).strip() or "미정"


def _parse_employment_type(pos: dict) -> str:
    career = pos.get("careerType") or ""
    if "인턴" in career:
        return "인턴"
    return "정규직"


def _parse_raw_text(pos: dict) -> str:
    company = (pos.get("startup") or {}).get("name", "")
    pt_names = " ".join(pt.get("name", "") for pt in (pos.get("positionTypes") or []))
    stacks = " ".join(s.get("name", "") if isinstance(s, dict) else str(s) for s in (pos.get("techStacks") or []))
    parts = [pos.get("name", ""), company, _parse_location(pos), pt_names, stacks]
    return " ".join(filter(None, parts))


def _to_raw_job(pos: dict) -> Optional[RawJob]:
    job_id = pos.get("id")
    title = str(pos.get("name", "")).strip()
    company_obj = pos.get("startup") or {}
    company = str(company_obj.get("name", "")).strip()
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
        source="groupby",
        location=_parse_location(pos),
        experience=_parse_experience(pos),
        employment_type=_parse_employment_type(pos),
        raw_text=_parse_raw_text(pos),
    )


async def crawl_groupby() -> List[RawJob]:
    """
    groupby.kr을 Playwright로 열어 CORS 세션 확보 후
    page.evaluate()로 api.groupby.kr을 직접 호출 (origin: groupby.kr → CORS 허용).
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("playwright 미설치: pip install playwright && playwright install chromium")
        return []

    all_items: List[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ko-KR",
        )
        page = await ctx.new_page()

        try:
            await page.goto(f"{BASE_URL}/positions", wait_until="networkidle", timeout=20000)
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"그룹바이 메인 페이지 로드 실패: {e}")
            await browser.close()
            return []

        seen_ids: set = set()

        for batch in range(MAX_BATCHES):
            offset = batch * BATCH_SIZE
            try:
                result = await page.evaluate(f"""
                async () => {{
                    const resp = await fetch(
                        '{API_BASE}/startup-positions?isAdvertising=false&limit={BATCH_SIZE}&offset={offset}&orderBy=-updatedAt',
                        {{ headers: {{ Accept: 'application/json' }} }}
                    );
                    if (!resp.ok) return null;
                    return await resp.json();
                }}
                """)
            except Exception as e:
                logger.warning(f"그룹바이 batch={batch} evaluate 오류: {e}")
                break

            if not result or not isinstance(result, dict):
                logger.warning(f"그룹바이 batch={batch} 응답 없음")
                break

            data = result.get("data") or {}
            items = data.get("items") or []

            if not items:
                break

            if batch == 0:
                logger.info(f"그룹바이 API 연결 성공, 수집 시작")

            new_items = []
            for item in items:
                item_id = item.get("id")
                if item_id and item_id not in seen_ids:
                    seen_ids.add(item_id)
                    new_items.append(item)
            all_items.extend(new_items)

            if len(items) < BATCH_SIZE:
                break

            page_jobs = [j for item in new_items if (j := _to_raw_job(item))]
            try:
                async with AsyncSessionLocal() as session:
                    if await is_caught_up(session, page_jobs):
                        break
            except Exception:
                pass

        await browser.close()

    jobs: List[RawJob] = [j for item in all_items if (j := _to_raw_job(item))]

    logger.info(f"그룹바이 수집 완료: {len(jobs)}건 (신입/인턴/경력무관 IT)")
    if jobs:
        async with AsyncSessionLocal() as session:
            await upsert_jobs(session, jobs)

    return jobs
