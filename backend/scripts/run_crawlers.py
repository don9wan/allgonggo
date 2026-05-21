"""
수동으로 크롤러를 실행하는 스크립트.
사용법: python scripts/run_crawlers.py [wanted|jumpit|programmers|catch|groupby|all]
"""
import asyncio
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def main(target: str = "all"):
    from app.crawlers.wanted import crawl_wanted
    from app.crawlers.jumpit import crawl_jumpit
    from app.crawlers.programmers import crawl_programmers
    from app.crawlers.catch import crawl_catch
    from app.crawlers.groupby import crawl_groupby

    crawlers = {
        "wanted": crawl_wanted,
        "jumpit": crawl_jumpit,
        "programmers": crawl_programmers,
        "catch": crawl_catch,
        "groupby": crawl_groupby,
    }

    if target == "all":
        targets = list(crawlers.keys())
    elif target in crawlers:
        targets = [target]
    else:
        print(f"알 수 없는 크롤러: {target}")
        print(f"사용 가능: {', '.join(crawlers.keys())}, all")
        sys.exit(1)

    for name in targets:
        print(f"\n{'='*40}")
        print(f"[{name}] 크롤링 시작")
        try:
            jobs = await crawlers[name]()
            print(f"[{name}] 완료 - {len(jobs)}건 수집")
        except Exception as e:
            print(f"[{name}] 실패: {e}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    asyncio.run(main(target))
