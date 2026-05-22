import logging
import httpx
from typing import List, Optional
from app.crawlers.base import RawJob
from app.db.database import AsyncSessionLocal
from app.crawlers.db_writer import upsert_jobs, is_caught_up

logger = logging.getLogger(__name__)

BASE_URL = "https://www.catch.co.kr"
API_URL = f"{BASE_URL}/api/v1.0/recruit/information/getRecruitList"
JOB_URL = f"{BASE_URL}/NCS/RecruitInfoDetails/{{job_id}}"
MAX_PAGES = 10
PAGE_SIZE = 30

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": f"{BASE_URL}/NCS/RecruitSearch",
}

# 캐치 응답의 Depth 필드에서 IT 직군 판별 (Playwright 분석으로 확인)
IT_DEPTHS = {
    "웹개발", "응용프로그램개발", "ERP/시스템개발/설계",
    "네트워크/서버/보안", "DBA/데이터베이스",
    "웹기획/PM/웹마케팅", "HTML/퍼블리싱/UI개발", "QA/테스트/검증",
    "게임", "빅데이터/AI", "정보기술/소프트웨어",
}

# 신입/인턴/경력무관 코드
CAREER_INCLUDE = {"신입", "인턴", "경력무관", "신입/경력"}


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
    # IT 직군 + 신입/인턴/경력무관 필터
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
    all_jobs: List[RawJob] = []

    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
        for page in range(1, MAX_PAGES + 1):
            try:
                r = await client.get(
                    API_URL,
                    params={
                        "Career": "1",   # 신입 포함 (Career=1이 신입+신입/경력)
                        "Sort": "0",     # 최신순
                        "curpage": page,
                        "pageSize": PAGE_SIZE,
                        "onRecruitYN": "Y",
                    },
                    headers=HEADERS,
                )
                if r.status_code != 200:
                    logger.warning(f"캐치 HTTP {r.status_code} (p={page})")
                    break

                data = r.json()
                items = data.get("recruitData", [])
                total = data.get("intTotalRecordCount", 0)

                if not items:
                    break

                page_jobs = [j for pos in items if (j := _to_raw_job(pos))]
                all_jobs.extend(page_jobs)

                if page == 1:
                    logger.info(f"캐치 신입 총 {total}건 → IT 필터링 중")

                if len(items) < PAGE_SIZE:
                    break

                try:
                    async with AsyncSessionLocal() as session:
                        raw_page = [j for pos in items if (j := _to_raw_job(pos))]
                        if await is_caught_up(session, raw_page):
                            break
                except Exception:
                    pass  # DB 없는 환경에서도 계속 수집

            except Exception as e:
                logger.error(f"캐치 p={page} 오류: {e}")
                break

    logger.info(f"캐치 수집 완료: {len(all_jobs)}건 (신입/인턴 IT)")
    if all_jobs:
        async with AsyncSessionLocal() as session:
            await upsert_jobs(session, all_jobs)

    return all_jobs
