#!/usr/bin/env python3
"""
크롤러 자가 테스트 스크립트.
Usage: python test_crawlers.py [--wanted] [--all] [--db]
"""
import asyncio
import sys
import json
import os

sys.path.insert(0, os.path.dirname(__file__))


async def test_wanted():
    print("\n=== 원티드 API 테스트 ===")
    import httpx

    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://www.wanted.co.kr/",
        "Wanted-User-Agent": "user-web",
    }
    params = {
        "country": "kr",
        "job_sort": "job.latest_order",
        "years": 0,
        "tag_type_ids": 518,
        "locations": "all",
        "limit": 10,
        "offset": 0,
    }

    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
        try:
            r = await client.get("https://www.wanted.co.kr/api/v4/jobs", params=params, headers=headers)
            print(f"HTTP 상태: {r.status_code}")
            if r.status_code != 200:
                print(f"오류: {r.text[:200]}")
                return False
            d = r.json()
            jobs = d.get("data", [])
            print(f"수신 공고 수: {len(jobs)}")
            print(f"페이지네이션: {d.get('links', {})}")
            for j in jobs[:5]:
                print(
                    f"  [{j.get('annual_from', '?')}y] {j.get('position', '')[:40]:40} | "
                    f"{j.get('company', {}).get('name', '')[:20]}"
                )
            ok = len(jobs) > 0
            print(f"\n결과: {'✅ 정상' if ok else '❌ 공고 없음'}")
            return ok
        except Exception as e:
            print(f"❌ 예외 발생: {e}")
            return False


async def test_blocked_sites():
    print("\n=== 비활성 크롤러 상태 확인 ===")
    import httpx

    sites = [
        ("jumpit", "https://jumpit.saramin.co.kr/api/positions?sort=rsp_rate&page=1"),
        ("catch", "https://www.catch.co.kr/api/recruit/list?pageIndex=1&pageSize=3"),
        ("groupby", "https://groupby.kr/api/v1/jobs?page=1&size=3"),
    ]

    async with httpx.AsyncClient(follow_redirects=False, timeout=10) as client:
        for name, url in sites:
            try:
                r = await client.get(url, headers={
                    "Accept": "application/json",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                })
                ct = r.headers.get("content-type", "")
                is_json = "json" in ct and r.status_code == 200
                status_str = "✅ JSON 응답" if is_json else f"❌ HTTP {r.status_code}"
                print(f"  {name:15} {status_str}")
            except Exception as e:
                print(f"  {name:15} ❌ {e}")

    # Programmers DNS check
    import socket
    try:
        socket.getaddrinfo("career.programmers.co.kr", 443)
        print(f"  {'programmers':15} ✅ DNS 해석 가능")
    except socket.gaierror:
        print(f"  {'programmers':15} ❌ DNS 해석 불가 (NXDOMAIN)")


async def test_crawler_module():
    print("\n=== 크롤러 모듈 실행 테스트 (원티드) ===")
    try:
        from app.crawlers.wanted import crawl_wanted
        from app.db.database import AsyncSessionLocal

        # 먼저 DB 연결 확인
        from sqlalchemy import text
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
            print("DB 연결: ✅")
        except Exception as e:
            print(f"DB 연결: ❌ {e}")
            print("DB 없이 API 호출만 테스트합니다.")
            return False

        print("원티드 크롤러 실행 중...")
        jobs = await crawl_wanted()
        print(f"수집 공고: {len(jobs)}건")
        for j in jobs[:3]:
            print(f"  {j.title[:40]:40} | {j.company[:20]} | {j.experience}")
        ok = len(jobs) > 0
        print(f"\n결과: {'✅ 정상' if ok else '❌ 공고 없음'}")
        return ok
    except Exception as e:
        print(f"❌ 모듈 실행 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_db():
    print("\n=== DB 상태 확인 ===")
    try:
        from sqlalchemy import text, select, func
        from app.db.database import AsyncSessionLocal
        from app.models.job import Job, JobSource

        async with AsyncSessionLocal() as session:
            job_count = (await session.execute(select(func.count()).select_from(Job))).scalar()
            source_count = (await session.execute(select(func.count()).select_from(JobSource))).scalar()
            by_source = await session.execute(
                select(Job.source, func.count(Job.id)).group_by(Job.source)
            )
            sources = {row[0]: row[1] for row in by_source}

        print(f"전체 공고: {job_count}건")
        print(f"소스 행: {source_count}건")
        print(f"소스별: {json.dumps(sources, ensure_ascii=False)}")
        return True
    except Exception as e:
        print(f"❌ DB 오류: {e}")
        return False


async def main():
    args = sys.argv[1:]
    run_all = "--all" in args or not args

    print("=" * 50)
    print("올공고 크롤러 테스트")
    print("=" * 50)

    results = {}

    if run_all or "--wanted" in args:
        results["wanted_api"] = await test_wanted()

    if run_all or "--blocked" in args:
        await test_blocked_sites()

    if run_all or "--module" in args:
        results["wanted_module"] = await test_crawler_module()

    if run_all or "--db" in args:
        results["db"] = await test_db()

    print("\n" + "=" * 50)
    print("테스트 결과 요약")
    print("=" * 50)
    for k, v in results.items():
        print(f"  {k:20} {'✅ 통과' if v else '❌ 실패'}")

    failed = [k for k, v in results.items() if not v]
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
