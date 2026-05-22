"""
보수적 크롤링 유틸리티.

설계 원칙:
- robots.txt 준수 및 Crawl-delay 자동 반영
- 요청 간 랜덤 딜레이 (2~5초 기본, 사이트별 조정 가능)
- 429 → Retry-After 헤더 준수
- 403/503 → 지수 백오프 (10s → 20s → 40s)
- 연속 5회 실패 시 해당 사이트 전체 크롤링 중단
- 투명한 User-Agent (위장보다 실제 신원 명시가 차단 리스크 낮음)
"""

import asyncio
import random
import logging
from urllib.robotparser import RobotFileParser
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

BOT_UA = (
    "AllgonggoBot/1.0 (IT job aggregator; "
    "https://allgonggo.com; "
    "contact: pm.don9wan@gmail.com)"
)

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class SafeClient:
    """
    단일 도메인에 대한 보수적 HTTP 클라이언트.
    인스턴스 하나 = 하나의 사이트.
    """

    def __init__(
        self,
        base_url: str,
        min_delay: float = 2.0,
        max_delay: float = 5.0,
        max_retries: int = 3,
        use_bot_ua: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.user_agent = BOT_UA if use_bot_ua else BROWSER_UA
        self._last_request_at: float = 0.0
        self._robots: Optional[RobotFileParser] = None
        self._consecutive_errors: int = 0
        self._aborted: bool = False

    async def setup(self, client: httpx.AsyncClient) -> None:
        """robots.txt 로드 및 Crawl-delay 적용."""
        robots_url = f"{self.base_url}/robots.txt"
        try:
            resp = await client.get(
                robots_url,
                headers={"User-Agent": self.user_agent},
                timeout=10,
                follow_redirects=True,
            )
            if resp.status_code == 200:
                parser = RobotFileParser()
                parser.set_url(robots_url)
                parser.parse(resp.text.splitlines())
                self._robots = parser

                for ua in (BOT_UA, "*"):
                    delay = parser.crawl_delay(ua)
                    if delay:
                        self.min_delay = max(self.min_delay, float(delay))
                        self.max_delay = max(self.max_delay, float(delay) + 2.0)
                        logger.info(
                            f"[{self.base_url}] robots.txt Crawl-delay {delay}s "
                            f"→ 딜레이 {self.min_delay:.1f}~{self.max_delay:.1f}s"
                        )
                        break
        except Exception as e:
            logger.warning(f"[{self.base_url}] robots.txt 로드 실패: {e}")

    def can_fetch(self, url: str) -> bool:
        if not self._robots:
            return True
        for ua in (BOT_UA, self.user_agent, "*"):
            if not self._robots.can_fetch(ua, url):
                return False
        return True

    async def _wait(self) -> None:
        loop = asyncio.get_event_loop()
        elapsed = loop.time() - self._last_request_at
        target = random.uniform(self.min_delay, self.max_delay)
        remaining = target - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)
        self._last_request_at = loop.time()

    async def get(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: Optional[dict] = None,
        extra_headers: Optional[dict] = None,
    ) -> Optional[dict]:
        """
        안전한 GET 요청. 실패 시 None 반환 (예외 전파 없음).
        연속 5회 실패 시 이후 모든 요청 즉시 None 반환.
        """
        if self._aborted:
            return None

        if not self.can_fetch(url):
            logger.warning(f"robots.txt 에 의해 차단된 URL: {url}")
            return None

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }
        if extra_headers:
            headers.update(extra_headers)

        for attempt in range(1, self.max_retries + 1):
            await self._wait()

            try:
                resp = await client.get(url, params=params, headers=headers, timeout=15)

                # Rate limit
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 60))
                    logger.warning(
                        f"[{self.base_url}] 429 Too Many Requests "
                        f"→ {retry_after}s 대기 후 재시도 ({attempt}/{self.max_retries})"
                    )
                    await asyncio.sleep(retry_after)
                    self._consecutive_errors += 1
                    continue

                # 일시적 차단 또는 서버 오류
                if resp.status_code in (403, 503, 502):
                    wait = (2 ** (attempt - 1)) * 10
                    logger.warning(
                        f"[{self.base_url}] HTTP {resp.status_code} "
                        f"→ {wait}s 백오프 ({attempt}/{self.max_retries})"
                    )
                    await asyncio.sleep(wait)
                    self._consecutive_errors += 1
                    if self._consecutive_errors >= 5:
                        logger.error(f"[{self.base_url}] 연속 오류 5회 → 사이트 크롤링 중단")
                        self._aborted = True
                    continue

                resp.raise_for_status()

                # 정상 응답
                self._consecutive_errors = 0
                content_type = resp.headers.get("content-type", "")
                if "json" in content_type:
                    return resp.json()
                # HTML 반환 시 (API가 아닌 경우)
                logger.warning(f"[{self.base_url}] JSON이 아닌 응답: {content_type[:50]}")
                return None

            except httpx.TimeoutException:
                wait = (2 ** (attempt - 1)) * 5
                logger.warning(f"[{self.base_url}] 타임아웃 (시도 {attempt}) → {wait}s 대기")
                await asyncio.sleep(wait)
                self._consecutive_errors += 1

            except Exception as e:
                logger.error(f"[{self.base_url}] 요청 실패 (시도 {attempt}): {type(e).__name__}: {e}")
                self._consecutive_errors += 1
                break

        if self._consecutive_errors >= 5:
            self._aborted = True
            logger.error(f"[{self.base_url}] 연속 오류 5회 → 사이트 크롤링 중단")

        return None
