"""
raw_text 정리 스크립트.
모든 소스의 기존 레코드 중 카테고리 태그 등이 섞인 raw_text를
title + company 형태로 정규화한다.

사용: python -m scripts.cleanup_raw_text [--dry-run]
"""
import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

from sqlalchemy import text
from app.db.database import AsyncSessionLocal


async def cleanup(dry_run: bool = False):
    async with AsyncSessionLocal() as session:
        # 노이즈가 있는 레코드 수 조회 (jasoseol, catch 소스)
        count_result = await session.execute(text("""
            SELECT COUNT(DISTINCT j.id)
            FROM jobs j
            JOIN job_sources js ON js.job_id = j.id
            WHERE js.source IN ('jasoseol', 'catch', 'linkareer')
              AND j.raw_text IS NOT NULL
              AND j.raw_text != (j.title || ' ' || j.company)
        """))
        noisy_count = count_result.scalar()
        logger.info("노이즈 레코드 수: %d건 (jasoseol/catch/linkareer)", noisy_count)

        if noisy_count == 0:
            logger.info("정리할 레코드 없음 — 완료")
            return

        # 샘플 출력 (확인용)
        samples = await session.execute(text("""
            SELECT DISTINCT j.id, j.title, j.company, j.raw_text
            FROM jobs j
            JOIN job_sources js ON js.job_id = j.id
            WHERE js.source IN ('jasoseol', 'catch', 'linkareer')
              AND j.raw_text IS NOT NULL
              AND j.raw_text != (j.title || ' ' || j.company)
            LIMIT 5
        """))
        for row in samples:
            logger.info("  샘플: [%s] %s | raw_text=%s", row.title, row.company, row.raw_text[:80])

        if dry_run:
            logger.info("--dry-run 모드: 실제 업데이트 생략")
            return

        # raw_text = title + ' ' + company 로 정규화
        result = await session.execute(text("""
            UPDATE jobs j
            SET raw_text = j.title || ' ' || j.company
            WHERE EXISTS (
                SELECT 1 FROM job_sources js
                WHERE js.job_id = j.id
                  AND js.source IN ('jasoseol', 'catch')
            )
              AND j.raw_text IS NOT NULL
              AND j.raw_text != (j.title || ' ' || j.company)
        """))
        await session.commit()
        logger.info("업데이트 완료: %d건", result.rowcount)


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(cleanup(dry_run=dry_run))
