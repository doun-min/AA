"""스코프 테스트 전용 스크립트.

verify_samsung_smartphones.py 의 로직을 그대로 재사용하되,
CATEGORY_MENU(기본 Mobile) 하위의 각 카테고리에서 **제품 1개씩만** 추출해
카테고리별로 파이프라인이 정상 동작하는지 빠르게 확인한다.

사용 예:
    python scope_test.py
    SAMSUNG_CATEGORIES="Galaxy Ring,Galaxy Tab" python scope_test.py
    SAMSUNG_MENU="TV & Audio" python scope_test.py
    SCOPE_FAST=1 python scope_test.py          # 정렬 1개 + 조합 2개까지만 (초고속)
    SAMSUNG_MAX_COMBOS=3 python scope_test.py  # 제품 1개의 색상x용량 조합 상한

결과:
    - stderr 로 진행 로그
    - stdout 로 사람이 읽는 요약 표
    - scope_test_result.json 으로 전체 레코드(JSON)
"""

import json
import os
import sys

from playwright.sync_api import sync_playwright

import verify_samsung_smartphones as v

# --- 스코프 테스트 고정 설정 ---------------------------------------------------
v.MAX_CARDS = 1  # 카테고리당 제품 1개만

if os.environ.get("SCOPE_FAST"):
    v.SORT_SEQUENCE = [v.SORT_SEQUENCE[0]]  # 정렬 1개만
    v.MAX_COMBOS = v.MAX_COMBOS or 2  # 조합 2개까지만

OUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scope_test_result.json")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)


def run():
    all_results = []
    summary = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, user_agent=UA)
        page.goto(v.BASE_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        v.dismiss_consent(page)

        categories = v.discover_categories(page)
        print(
            f"[scope] {v.CATEGORY_MENU}: {len(categories)} categories -> "
            + ", ".join(c["name"] for c in categories),
            file=sys.stderr,
        )

        for cat in categories:
            print(f"[scope] scanning: {cat['name']} ({cat['href']})", file=sys.stderr)
            try:
                recs = v.scan_category(page, cat)
            except Exception as e:  # noqa: BLE001 - 한 카테고리 실패해도 계속
                recs = [
                    {
                        "category": cat["name"],
                        "category_url": cat["href"],
                        "status": f"error: {type(e).__name__}: {e}",
                    }
                ]
            all_results.extend(recs)

            skipped = [r for r in recs if r.get("status")]
            data = [r for r in recs if not r.get("status")]
            skus = [r["sku"] for r in data if r.get("sku")]
            sorts = sorted({r.get("sort_type") for r in data if r.get("sort_type")})
            summary.append(
                {
                    "category": cat["name"],
                    "records": len(data),
                    "skipped": skipped[0]["status"] if skipped else None,
                    "sorts": sorts,
                    "product": data[0]["name"] if data else None,
                    "sample_skus": skus[:6],
                    "errors": sum(1 for r in data if r.get("error")),
                }
            )

        browser.close()

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print("\n=== SCOPE TEST SUMMARY ===")
    for s in summary:
        if s["skipped"]:
            print(f"- {s['category']:<24} SKIP   ({s['skipped']})")
            continue
        line = (
            f"- {s['category']:<24} {s['records']:>3} recs  "
            f"sorts=[{','.join(s['sorts'])}]  "
            f"product=[{s['product']}]  skus={s['sample_skus']}"
        )
        if s["errors"]:
            line += f"  (combo errors: {s['errors']})"
        print(line)
    print(f"\nfull JSON -> {OUT_FILE}")
    return all_results


if __name__ == "__main__":
    run()
