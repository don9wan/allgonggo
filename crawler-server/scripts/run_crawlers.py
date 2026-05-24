"""
수동 실행용 스크립트.
사용: python -m scripts.run_crawlers [wanted|catch|linkareer|groupby|jasoseol|all]
"""
import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from app.crawlers import wanted, catch, linkareer, groupby, jasoseol

CRAWLERS = {
    "wanted": wanted.crawl_wanted,
    "catch": catch.crawl_catch,
    "linkareer": linkareer.crawl_linkareer,
    "groupby": groupby.crawl_groupby,
    "jasoseol": jasoseol.crawl_jasoseol,
}


async def main(target: str):
    if target == "all":
        for name, fn in CRAWLERS.items():
            print(f"=== {name} 시작 ===")
            try:
                await fn()
            except Exception as e:
                print(f"!!! {name} 실패: {e}")
    elif target in CRAWLERS:
        await CRAWLERS[target]()
    else:
        print(f"Unknown target: {target}")
        print(f"Available: {list(CRAWLERS.keys()) + ['all']}")
        sys.exit(1)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    asyncio.run(main(target))
