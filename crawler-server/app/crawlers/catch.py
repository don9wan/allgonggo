import logging
from typing import List

from app.crawlers.base import RawJob
from app.crawlers.browser import launch_browser, random_delay
from app.crawlers.db_writer import is_caught_up, upsert_jobs
from app.db.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

BASE_URL = "https://www.catch.co.kr/NCS/RecruitSearch"
API_URL = "https://www.catch.co.kr/api/v1.0/recruit/information/getRecruitList"
PAGE_SIZE = 30

# Career=1: 신입, Career=4: 인턴(GubunCode=인턴 기준)
CAREER_PARAMS = {"1": "신입", "4": "인턴"}

# Depth 필드 기준 IT/디자인 직무 키워드
IT_DEPTH_KEYWORDS = (
    "웹개발", "응용프로그램개발", "ERP/시스템개발", "네트워크/서버/보안",
    "DBA/데이터베이스", "콘텐츠/사이트운영", "웹기획", "HTML/퍼블리싱",
    "QA/테스트", "게임", "동영상제작", "빅데이터", "AI",
    "그래픽디자인", "출판/편집디자인", "제품/산업디자인", "캐릭터/만화",
    "의류/패션/잡화디자인", "전시/공간디자인", "광고/시각디자인",
)


def _parse_job(item: dict) -> RawJob | None:
    try:
        recruit_id = item.get("RecruitID")
        title = (item.get("RecruitTitle") or "").strip()
        company = (item.get("CompName") or "").strip()
        depth = (item.get("Depth") or "")

        if not recruit_id or not title or not company:
            return None

        # IT/디자인 직무만 수집
        if not any(kw in depth for kw in IT_DEPTH_KEYWORDS):
            return None

        url = f"https://www.catch.co.kr/NCS/RecruitInfoDetails/{recruit_id}"
        career = (item.get("CareerGubunCode") or "").strip() or None
        emp_type = (item.get("GubunCode") or "").strip() or None
        location = (item.get("WorkArea") or "").strip() or None

        return RawJob(
            title=title,
            company=company,
            url=url,
            source="catch",
            location=location,
            experience=career,
            employment_type=emp_type,
            raw_text=f"{title} {company}".strip(),
        )
    except Exception as e:
        logger.warning(f"캐치 파싱 오류: {e}")
        return None


async def _fetch_via_page(page, url: str) -> dict | None:
    """Cloudflare 우회: 브라우저 컨텍스트 내 fetch로 API 호출."""
    try:
        result = await page.evaluate(
            """async (url) => {
                const resp = await fetch(url, {
                    headers: {
                        'Accept': 'application/json, text/plain, */*',
                    },
                    credentials: 'include',
                });
                if (!resp.ok) return { __error__: resp.status };
                return await resp.json();
            }""",
            url,
        )
        if isinstance(result, dict) and "__error__" in result:
            logger.error(f"캐치 API fetch 오류: HTTP {result['__error__']}")
            return None
        return result
    except Exception as e:
        logger.error(f"캐치 API evaluate 실패: {e}")
        return None


async def crawl_catch():
    logger.info("캐치 크롤링 시작")
    all_jobs: List[RawJob] = []
    seen_urls: set = set()

    browser = await launch_browser()
    try:
        context = await browser.new_context()
        page = await context.new_page()

        # 메인 페이지 로드 → Cloudflare 챌린지 통과 + 쿠키 획득
        try:
            await page.goto(BASE_URL, wait_until="load", timeout=45000)
        except Exception:
            pass  # load 타임아웃 무시 — 쿠키는 이미 세팅됨
        await page.wait_for_timeout(2000)
        await random_delay()

        for career_val, career_label in CAREER_PARAMS.items():
            page_num = 1
            while True:
                api_url = (
                    f"{API_URL}?Keyword=&Sido=&Career={career_val}"
                    f"&Sort=0&curpage={page_num}&pageSize={PAGE_SIZE}"
                    f"&onRecruitYN=Y&ExceptIDList="
                )

                data = await _fetch_via_page(page, api_url)
                if data is None:
                    break

                total = data.get("intTotalRecordCount", 0)
                items = data.get("recruitData", [])

                if not items:
                    break

                page_jobs = [j for item in items if (j := _parse_job(item)) is not None]
                logger.info(f"[catch][{career_label}] p{page_num} — 배치 {len(page_jobs)}건 / 전체 {total}건 중")

                async with AsyncSessionLocal() as session:
                    caught_up = await is_caught_up(session, page_jobs)

                for job in page_jobs:
                    if job.url not in seen_urls:
                        seen_urls.add(job.url)
                        all_jobs.append(job)

                if caught_up:
                    logger.info(f"[catch][{career_label}] 최신 공고 따라잡음, 조기 종료")
                    break
                if page_num * PAGE_SIZE >= total:
                    break

                page_num += 1
                await random_delay()

            logger.info(f"[catch][{career_label}] 완료 — 누적 {len(all_jobs)}건")
            await random_delay()

    finally:
        await browser.close()

    logger.info(f"캐치 총 {len(all_jobs)}건 수집")
    total_inserted = total_linked = 0
    if all_jobs:
        async with AsyncSessionLocal() as session:
            total_inserted, total_linked = await upsert_jobs(session, all_jobs)

    logger.info(f"캐치 완료 — 신규: {total_inserted}건, 소스 추가: {total_linked}건")
