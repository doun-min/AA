"""검증 대상 실데이터(xlsx)를 받아 스코프 테스트를 한 번에 수행한다.

  1) 실데이터 파일명을 인자로 받는다
  2) GNB 의 모든 L0 메뉴에 걸친 PF 페이지를 canonical URL 로 dedup 해 순회 스크랩
     -> scrape_YYYYMMDDHHmm.json (+ .dedup.json)
  3) (sku, sort_type) 로 제품 레벨 dedup 후 실데이터와 필드별 PASS/FAIL 판정
  4) 리포트를 result_YYYYMMDDHHmm.xlsx 로 저장

사용:
    python run_scope_test.py <expected.xlsx>                 # 전 메뉴 전 PF (권장, 오래 걸림)
    python run_scope_test.py <expected.xlsx> --default-only  # 카드 기본조합만 (대폭 빠름)
    python run_scope_test.py <expected.xlsx> --from-data     # 실데이터에 있는 카테고리만
    python run_scope_test.py <expected.xlsx> --menu Mobile   # 특정 L0 메뉴만
    python run_scope_test.py <expected.xlsx> --scrape-json scrape_XXX.json  # 스크랩 재사용
    python run_scope_test.py <expected.xlsx> --fresh         # PF 캐시 무시하고 처음부터

옵션:
    --default-only     카드의 기본(대표) 조합 1개만 수집
    --max-cards N      PF 당 상위 N개 카드만
    --menu NAME        L0 메뉴 1개만 (기본: 전체)
    --menus "A,B"      L0 메뉴 여러 개
    --categories LIST  L1 카테고리 이름으로 필터 (쉼표구분)
    --from-data        실데이터(product_url/카테고리)에 등장하는 카테고리만 스캔
    --scrape-json PATH 기존 스크랩 JSON 재사용 (재스크랩 생략)
    --resume DIR       PF 단위 체크포인트 폴더 (기본: <outdir>/pf_cache, 재실행 시 이어서)
    --fresh            체크포인트 폴더를 비우고 처음부터
    --progress-file P  진행 상황 JSON 경로 (기본: <outdir>/progress.json)
    --outdir DIR       결과 저장 폴더 (기본: 현재 폴더)
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime

import pandas as pd

import verify_samsung_smartphones as scraper
from verify import build_report, load_expected

# PF product_url slug / display_category_middle -> Mobile L1 메뉴 이름
SLUG_TO_MENU = {
    "smartphones": "Galaxy Smartphones",
    "watches": "Galaxy Watch",
    "tablets": "Galaxy Tab",
    "computers": "Galaxy Book",
    "audio-sound": "Galaxy Buds",
    "audio-devices": "Galaxy Buds",
    "rings": "Galaxy Ring",
    "mobile-accessories": "Galaxy Accessories",
    "xr": "Galaxy XR",
}
MIDDLE_TO_MENU = {
    "smartphones": "Galaxy Smartphones",
    "watch": "Galaxy Watch", "watches": "Galaxy Watch",
    "tablet": "Galaxy Tab", "tablets": "Galaxy Tab",
    "computers": "Galaxy Book", "pc": "Galaxy Book",
    "audio": "Galaxy Buds", "buds": "Galaxy Buds",
    "ring": "Galaxy Ring", "rings": "Galaxy Ring",
    "accessories": "Galaxy Accessories", "mobile accessories": "Galaxy Accessories",
}


def derive_categories(expected):
    """expected 의 product_url / display_category_middle 로부터 L1 카테고리 이름 집합."""
    cats = set()
    for e in expected.values():
        url = (e.get("product_url") or "").strip("/").lower()
        slug = url.split("/")[1] if url.startswith("us/") and "/" in url else None
        if slug in SLUG_TO_MENU:
            cats.add(SLUG_TO_MENU[slug])
            continue
        mid = (e.get("display_category_middle") or "").strip().lower()
        if mid in MIDDLE_TO_MENU:
            cats.add(MIDDLE_TO_MENU[mid])
    return sorted(cats)


def _s(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (list, tuple, dict)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def write_report(path, summary, rows, meta, ambiguities, sku_mismatches=()):
    detail = pd.DataFrame(rows, columns=[
        "model_code", "field", "rule", "volatile", "result", "got", "expected", "detail",
    ])
    for col in ("got", "expected", "volatile"):
        detail[col] = detail[col].map(_s)
    fails = detail[detail["result"] == "FAIL"]
    notfound = detail[detail["result"] == "NOT_FOUND"][["model_code", "expected"]].rename(
        columns={"expected": "display_name"}
    )
    summ = pd.DataFrame(
        [{"key": k, "value": _s(v)} for k, v in {**meta, **summary}.items()],
        columns=["key", "value"],
    )
    amb = pd.DataFrame(
        [
            {
                "sku": a["sku"], "sort_type": a["sort_type"],
                "sources": _s(a["sources"]), "fields": _s(a["fields"]),
            }
            for a in ambiguities
        ],
        columns=["sku", "sort_type", "sources", "fields"],
    )
    skua = pd.DataFrame(
        list(sku_mismatches),
        columns=["sku_dom", "sku_qv", "source_pf_url", "color", "capacity"],
    )

    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        summ.to_excel(xw, sheet_name="Summary", index=False)
        detail.to_excel(xw, sheet_name="Detail", index=False)
        fails.to_excel(xw, sheet_name="Failures", index=False)
        notfound.to_excel(xw, sheet_name="NotFound", index=False)
        amb.to_excel(xw, sheet_name="Ambiguities", index=False)
        skua.to_excel(xw, sheet_name="SkuAudit", index=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("expected", help="검증 대상 실데이터 xlsx")
    ap.add_argument("--site", default="us", choices=["us", "ca", "ca_fr"],
                    help="대상 사이트 (samsung.com/<site>)")
    ap.add_argument("--scrape-json", help="기존 스크랩 JSON 재사용")
    ap.add_argument("--max-cards", type=int, default=0)
    ap.add_argument("--default-only", action="store_true")
    ap.add_argument("--verify-sku-sample", type=int, default=0,
                    help="PF 마다 첫 N개 variant 는 Quick View 로 SKU 교차검증")
    ap.add_argument("--menu", help="L0 메뉴 1개만")
    ap.add_argument("--menus", help="L0 메뉴 여러 개 (쉼표구분)")
    ap.add_argument("--categories", help="L1 카테고리 이름 필터 (쉼표구분)")
    ap.add_argument("--from-data", action="store_true", help="실데이터에 있는 카테고리만")
    ap.add_argument("--resume", help="PF 체크포인트 폴더 (기본 <outdir>/pf_cache)")
    ap.add_argument("--fresh", action="store_true", help="체크포인트 비우고 처음부터")
    ap.add_argument("--progress-file", help="진행 상황 JSON 경로")
    ap.add_argument("--outdir", default=".")
    args = ap.parse_args()

    if not os.path.exists(args.expected):
        ap.error(f"파일 없음: {args.expected}")

    scraper.set_site(args.site)  # BASE_URL / SITE / 통화 갱신

    ts = datetime.now().strftime("%Y%m%d%H%M")
    tag = args.site  # 파일명에 사이트 구분자
    os.makedirs(args.outdir, exist_ok=True)
    scrape_path = os.path.join(args.outdir, f"scrape_{tag}_{ts}.json")
    dedup_path = os.path.join(args.outdir, f"scrape_{tag}_{ts}.dedup.json")
    result_path = os.path.join(args.outdir, f"result_{tag}_{ts}.xlsx")
    progress_file = args.progress_file or os.path.join(args.outdir, f"progress_{tag}.json")
    resume_dir = args.resume or os.path.join(args.outdir, f"pf_cache_{tag}")

    # 1) 기대값 로드
    expected, order_map = load_expected(args.expected)
    print(f"[1/4] expected: {len(expected)} models  <- {args.expected}", file=sys.stderr)

    # 2) 스크랩 (또는 재사용)
    if args.scrape_json:
        raw = json.load(open(args.scrape_json, encoding="utf-8"))
        scrape_path = args.scrape_json
        print(f"[2/4] reuse scrape: {len(raw)} records <- {args.scrape_json}", file=sys.stderr)
    else:
        if args.menus:
            menus = [m.strip() for m in args.menus.split(",") if m.strip()]
        elif args.menu:
            menus = [args.menu]
        else:
            menus = None  # 전체 L0 메뉴
        only = [c.strip() for c in args.categories.split(",")] if args.categories else []
        if args.from_data and not only:
            only = derive_categories(expected)

        if args.fresh and os.path.isdir(resume_dir):
            shutil.rmtree(resume_dir)

        scraper.MENUS = menus
        scraper.ONLY_CATEGORIES = only
        scraper.MAX_CARDS = args.max_cards or None
        scraper.DEFAULT_ONLY = bool(args.default_only)
        scraper.QV_AUDIT_N = args.verify_sku_sample or 0
        scraper.RESUME_DIR = resume_dir
        print(
            f"[2/4] scraping site={args.site} ({scraper.BASE_URL}) "
            f"menus={menus or 'ALL'} categories={only or 'ALL'} "
            f"max_cards={scraper.MAX_CARDS} default_only={scraper.DEFAULT_ONLY} "
            f"resume_dir={resume_dir}",
            file=sys.stderr,
        )
        raw = scraper.run_scan(progress_file=progress_file)
        with open(scrape_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
        print(f"[2/4] scrape saved -> {scrape_path} ({len(raw)} records)", file=sys.stderr)

    # 3) 제품 레벨 dedup + 비교
    records, ambiguities = scraper.dedupe_records(raw)
    with open(dedup_path, "w", encoding="utf-8") as f:
        json.dump({"records": records, "ambiguities": ambiguities}, f, ensure_ascii=False, indent=2)
    rows, summary = build_report(records, expected, order_map)

    # SKU 소스 분포 + Quick View 교차검증 불일치
    src_counts = {}
    sku_mismatches = []
    for r in raw:
        if r.get("status"):
            continue
        src_counts[r.get("sku_source")] = src_counts.get(r.get("sku_source"), 0) + 1
        if r.get("sku_audit_mismatch"):
            sku_mismatches.append(
                {"sku_dom": r["sku_audit_mismatch"].get("dom"),
                 "sku_qv": r["sku_audit_mismatch"].get("qv"),
                 "source_pf_url": r.get("source_pf_url"),
                 "color": r.get("product_color"), "capacity": r.get("capacity")}
            )
    summary["ambiguous_products"] = len(ambiguities)
    summary["raw_records"] = len(raw)
    summary["sku_source_counts"] = src_counts
    summary["sku_audit_mismatches"] = len(sku_mismatches)
    print(
        f"[3/4] dedup {len(raw)}->{len(records)}  ambiguous={len(ambiguities)}  "
        f"sku_src={src_counts}  sku_audit_mismatch={len(sku_mismatches)}  || "
        f"PASS={summary['pass']} FAIL={summary['fail_strict']} "
        f"FAIL*(volatile)={summary['fail_volatile']} SKIP={summary['skip']} "
        f"NOT_FOUND={summary['not_found']}",
        file=sys.stderr,
    )

    # 4) 리포트 저장
    meta = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "site": args.site,
        "expected_file": os.path.abspath(args.expected),
        "scrape_json": os.path.abspath(scrape_path),
        "scrape_reused": bool(args.scrape_json),
        "menus": (args.menus or args.menu or "ALL"),
        "categories": (args.categories or ("from-data" if args.from_data else "ALL")),
        "max_cards": args.max_cards or "ALL",
        "default_only": bool(args.default_only),
    }
    write_report(result_path, summary, rows, meta, ambiguities, sku_mismatches)
    print(f"[4/4] report -> {result_path}", file=sys.stderr)
    print(result_path)
    return 1 if summary["fail_strict"] else 0


if __name__ == "__main__":
    sys.exit(main())
