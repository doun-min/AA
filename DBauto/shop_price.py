"""Samsung 커머스 API 로 정확한 가격을 가져와 스크랩 레코드를 보강.

PF 카드는 현재가(프로모가)만 보여주는 경우가 많아 standard_price/final_price 가
어긋난다. DB(model_price.price / promotion_price)는 아래 API 에서 생성되므로
같은 API 를 직접 호출해 값을 채운다.

  GET https://api.shop.samsung.com/tokocommercewebservices/v2/<site>/products/<code>
    site : us | ca | ca_fr
    code : SKU 그대로 (슬래시 '/' 는 인코딩하지 않음 - %2F 는 400)
    -> ~2KB JSON, 인증/JS 불필요, ~0.1~0.9s

레코드에 채우는 값:
  standard_price   <- price.value              (정가 / regular)
  final_price      <- promotionPrice.value 있으면 그것, 없으면 price.value
  currency         <- price.currencyIso
  *_pf             <- 기존 PF 카드 파싱값 보존 (교차검증용)
  price_source     <- 'shop-api' | None(미조회 -> 기존값 유지)
  price_drift_pf_vs_api <- PF 현재가와 API 최종가 차이(>2%) 있을 때만

on_sale / discount_amount 는 건드리지 않는다: DB on_sale 은 "할인 여부"가 아니라
"활성 오퍼 존재"에 가까워(정가인데 True 인 행 다수) API 로 재현 불가.

CLI:
  python shop_price.py scrape_ca_XXXX.json --site ca [-o out.json]
"""

import argparse
import concurrent.futures as cf
import json
import sys
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

API = "https://api.shop.samsung.com/tokocommercewebservices/v2/{site}/products/{code}"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def _num(d):
    """{'value': 1599.99, ...} -> float / None"""
    if isinstance(d, dict):
        v = d.get("value")
        try:
            return round(float(v), 2) if v is not None else None
        except (TypeError, ValueError):
            return None
    return None


def fetch_price(site, code, timeout=15, retries=1):
    """(standard, final, currency, on_sale, discount) 또는 None."""
    url = API.format(site=site, code=code)  # 슬래시 인코딩 안 함
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                j = json.loads(r.read().decode("utf-8", "replace"))
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt >= retries:
                return None
        except Exception:  # noqa: BLE001
            if attempt >= retries:
                return None
        time.sleep(0.4)
    else:
        return None

    std = _num(j.get("price"))
    promo = _num(j.get("promotionPrice"))
    if std is None and promo is None:
        return None
    cur = (j.get("price") or {}).get("currencyIso") or (
        j.get("promotionPrice") or {}
    ).get("currencyIso")
    final = promo if promo is not None else std
    return {
        "standard_price": std if std is not None else final,
        "final_price": final,
        "currency": cur,
    }


def enrich_prices(records, site, workers=10, log=None):
    """records(list[dict]) in-place 보강. 반환: 통계."""
    log = log or (lambda m: print(m, file=sys.stderr))
    site = (site or "us").lower()

    codes = {}
    for r in records:
        if r.get("status"):
            continue
        c = r.get("sku") or r.get("model_code")
        if c:
            codes.setdefault(str(c), []).append(r)
    log(f"[info] 가격 API 보강: distinct SKU {len(codes)}개 (site={site})")

    t0 = time.time()
    result = {}
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        fut = {ex.submit(fetch_price, site, c): c for c in codes}
        done = 0
        for f in cf.as_completed(fut):
            result[fut[f]] = f.result()
            done += 1
            if done % 250 == 0:
                log(f"  {done}/{len(codes)}  ({time.time() - t0:.0f}s)")

    hit = drift = 0
    for c, recs in codes.items():
        pr = result.get(c)
        if not pr:
            continue
        for r in recs:
            for k in ("standard_price", "final_price", "currency"):
                r.setdefault(k + "_pf", r.get(k))
            # PF vs API final 차이(>2%) 는 실시간 프로모 편차 -> 표시
            pf_final = r.get("final_price_pf")
            if (
                pf_final and pr["final_price"]
                and abs(pf_final - pr["final_price"]) / pr["final_price"] > 0.02
            ):
                r["price_drift_pf_vs_api"] = round(pf_final - pr["final_price"], 2)
                drift += 1
            r.update(pr)
            r["price_source"] = "shop-api"
        hit += 1

    stats = {
        "distinct_sku": len(codes),
        "api_hit": hit,
        "api_miss": len(codes) - hit,
        "pf_vs_api_drift": drift,
        "elapsed_sec": round(time.time() - t0, 1),
    }
    log(f"[info] 가격 API 보강 완료: {stats}")
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scrape_json")
    ap.add_argument("--site", required=True, choices=["us", "ca", "ca_fr"])
    ap.add_argument("-o", "--output")
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()

    data = json.load(open(args.scrape_json, encoding="utf-8"))
    records = data if isinstance(data, list) else data.get("records", [])
    enrich_prices(records, args.site, workers=args.workers)
    out = args.output or args.scrape_json.replace(".json", ".priced.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"-> {out}")


if __name__ == "__main__":
    main()
