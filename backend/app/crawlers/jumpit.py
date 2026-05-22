import logging
import httpx
from typing import List, Optional
from app.crawlers.base import RawJob
from app.db.database import AsyncSessionLocal
from app.crawlers.db_writer import upsert_jobs, is_caught_up

logger = logging.getLogger(__name__)

BASE_URL = "https://jumpit.saramin.co.kr"
# 실제 API는 jumpit-api 서브도메인에 위치 (Playwright 분석으로 발견)
API_URL = "https://jumpit-api.saramin.co.kr/api/positions"
JOB_URL = f"{BASE_URL}/position/{{job_id}}"
MAX_PAGES = 6

# IT 관련 jobCategory ID 목록 (code-initialize API에서 확인)
IT_JOB_CATEGORIES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 16, 17, 18, 19, 20, 22]
# 1=서버/백엔드, 2=프론트엔드, 3=웹풀스택, 4=안드로이드, 5=게임클라이언트,
# 6=게임서버, 7=DBA, 8=AI/ML, 9=DevOps, 10=보안, 11=QA, 16=iOS,
# 17=퍼블리셔, 18=크로스플랫폼, 19=빅데이터, 20=개발PM, 22=블록체인

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": f"{BASE_URL}/",
    "Origin": BASE_URL,
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def _parse_experience(pos: dict) -> str:
    if pos.get("newcomer"):
        return "신입"
    min_c = pos.get("minCareer", 0) or 0
    max_c = pos.get("maxCareer", 0) or 0
    if min_c == 0 and max_c == 0:
        return "경력무관"
    if min_c == 0:
        return "신입"
    return f"경력 {min_c}년 이상"


def _parse_location(pos: dict) -> str:
    locations = pos.get("locations", [])
    if locations:
        return locations[0]
    return "미정"


def _parse_raw_text(pos: dict) -> str:
    stacks = pos.get("techStacks", [])
    stack_text = " ".join(s if isinstance(s, str) else s.get("name", "") for s in stacks)
    parts = [
        pos.get("title", ""),
        pos.get("companyName", ""),
        _parse_location(pos),
        pos.get("jobCategory", ""),
        stack_text,
    ]
    return " ".join(filter(None, parts))


def _to_raw_job(pos: dict) -> Optional[RawJob]:
    job_id = pos.get("id")
    title = pos.get("title", "").strip()
    company = pos.get("companyName", "").strip()
    if not job_id or not title or not company:
        return None

    is_intern = "인턴" in title
    emp_type = "인턴" if is_intern else "정규직"

    return RawJob(
        title=title,
        company=company,
        url=JOB_URL.format(job_id=job_id),
        source="jumpit",
        location=_parse_location(pos),
        experience=_parse_experience(pos),
        employment_type=emp_type,
        raw_text=_parse_raw_text(pos),
    )


async def crawl_jumpit() -> List[RawJob]:
    all_jobs: List[RawJob] = []

    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
        # IT 카테고리 + 신입(career=0) 필터로 수집
        # career=0이 신입 필터 (Playwright 분석으로 확인: 6건 → 56건 차이)
        for category_id in IT_JOB_CATEGORIES:
            cat_jobs: List[RawJob] = []

            for page in range(1, MAX_PAGES + 1):
                try:
                    r = await client.get(
                        API_URL,
                        params={
                            "jobCategory": category_id,
                            "career": 0,  # 신입 필터
                            "sort": "rsp_rate",
                            "highlight": "false",
                            "page": page,
                        },
                        headers=HEADERS,
                    )
                    if r.status_code != 200:
                        logger.warning(f"점핏 HTTP {r.status_code} (cat={category_id}, p={page})")
                        break

                    result = r.json().get("result", {})
                    positions = result.get("positions", [])
                    if not positions:
                        break

                    page_jobs = [j for pos in positions if (j := _to_raw_job(pos))]
                    cat_jobs.extend(page_jobs)

                    if page == 1:
                        total = result.get("totalCount", "?")
                        logger.debug(f"점핏 cat={category_id} 총 {total}건")

                    try:
                        async with AsyncSessionLocal() as session:
                            if await is_caught_up(session, page_jobs):
                                break
                    except Exception:
                        pass  # DB 없는 환경에서도 계속 수집

                    if len(positions) < 16:  # 페이지당 최대 16건
                        break

                except Exception as e:
                    logger.error(f"점핏 cat={category_id} p={page} 오류: {e}")
                    break

            all_jobs.extend(cat_jobs)

    # URL 중복 제거
    seen = set()
    unique_jobs = []
    for j in all_jobs:
        if j.url not in seen:
            seen.add(j.url)
            unique_jobs.append(j)

    logger.info(f"점핏 수집 완료: {len(unique_jobs)}건 (신입 IT)")
    if unique_jobs:
        async with AsyncSessionLocal() as session:
            await upsert_jobs(session, unique_jobs)

    return unique_jobs
