"""PF 페이지 스크랩 결과(JSON)를 검증 대상 실데이터(xlsx)와 대조해 필드별 PASS/FAIL 판정.

규칙:
  EXACT  - 값이 정확히 일치해야 PASS
  TOL    - review_count/review_rating_score: ±REVIEW_TOL_RATIO(20%) 또는
           절대 허용치(count ±25, rating ±0.3) 중 하나만 충족하면 PASS
  volatile - final_price, badge, stock_level_status, sorting_no, review_* 등
             시점에 따라 정상적으로 바뀌는 필드. FAIL 을 요약에서 분리 집계.
  검증 제외 - on_sale(사이트 무관), capacity(model_code 로 식별됨)
  display_category_major - 스크랩값 없으면 PF URL 슬러그 -> SLUG_TO_MAJOR 로 유도
  sorting_no - 절대 순번이 아니라 'PF 안에서의 상대 순위' 로 비교
               (사이트가 한 type 을 여러 하위 PF 로 쪼개므로)

CLI:
    python verify.py <scraped.json> <expected.xlsx>
    -> 표 출력 + verify_result.json

라이브러리:
    load_expected(path) -> (expected: {model_code: {...}}, order_map: {(mc, sort): no})
    build_report(records, expected, order_map) -> (rows, summary)
"""

import collections
import json
import re
import sys

import pandas as pd

from verify_samsung_smartphones import TOLERANCE_FIELDS, TOLERANCE_RATIO

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

# (필드명, 규칙, volatile)   규칙: EXACT | TOL
FIELDS = [
    ("model_code", "EXACT", False),
    ("model_name", "EXACT", False),
    ("display_name", "EXACT", False),
    # 카테고리 표시명은 사이트 내비 vs DB, 로케일(ca_fr)에 따라 표기가 갈리고
    # CA 카드엔 data-feedback-param 이 비어 스크랩이 안 되므로 volatile 로 둔다.
    # 스크랩값이 없으면 PF URL 슬러그 -> SLUG_TO_MAJOR 로 유도해 비교
    ("display_category_major", "EXACT", True),
    ("display_category_middle", "EXACT", True),
    ("product_color", "EXACT", False),
    # capacity: model_code/sku 로 이미 식별되므로 검증 제외 (표기 편차만 큼)
    ("product_url", "EXACT", False),
    ("cta_pd_url", "EXACT", False),
    # norm() 이 -thumb-/자산id 변동분을 떼고 안정 slug 만 비교하므로 EXACT 로 검증.
    ("image_url", "EXACT", False),
    ("family_id", "EXACT", False),
    ("badge", "EXACT", True),  # 프로모션성 배지(Labor Day 등)라 시점 따라 바뀜
    ("standard_price", "EXACT", False),
    ("currency", "EXACT", False),
    ("is_default", "EXACT", False),  # 스크랩 is_default(카드 기본 variant) vs DB key_model_yn
    ("final_price", "EXACT", True),
    # on_sale: 사이트 무관 검증 제외 (DB on_sale 은 '할인'이 아니라 '오퍼 존재' 의미)
    ("stock_level_status", "EXACT", True),
    ("sorting_no", "EXACT", True),  # sort_type 별, PF 내 상대순위로 비교
    ("review_count", "TOL", True),
    ("review_rating_score", "TOL", True),
]

# 리뷰 관련: 스냅샷 시점차로 값이 벌어져도 휴먼 검토 시 정상인 경우가 많다.
# ±비율 또는 아래 절대 허용치 중 하나만 충족해도 PASS.
REVIEW_TOL_RATIO = 0.20
REVIEW_ABS_TOL = {"review_count": 25, "review_rating_score": 0.3}

def _pf_slug(url):
    """/us/smartphones/all-smartphones -> 'smartphones' ; /ca_fr/watches/... -> 'watches'."""
    if not url:
        return None
    segs = [s for s in str(url).strip("/").split("/") if s]
    return segs[1].lower() if len(segs) >= 2 else None


def _pf_site(url):
    """/ca_fr/watches/... -> 'ca_fr'"""
    if not url:
        return None
    segs = [s for s in str(url).strip("/").split("/") if s]
    return segs[0].lower() if segs else None


# PF URL 슬러그 -> display_category_major (DB category_lv1).
# 슬러그는 로케일 불문 영어 유지. 'computers' 만 US=PC / CA=Computers 로 갈린다.
SLUG_TO_MAJOR = {
    "smartphones": "Mobile", "watches": "Mobile", "tablets": "Mobile",
    "audio-sound": "Mobile", "mobile-accessories": "Mobile", "rings": "Mobile",
    "xr": "Mobile",
    "computers": "Computers",  # US 는 아래 _major_for_slug 에서 PC 로 치환
    "computing": "Computers", "computer-accessories": "Computers",
    "audio-devices": "Audio", "jbl-harman-kardon": "Audio",
    "audio-accessories": "Audio",
    "tvs": "Television", "lifestyle-tvs": "Television",
    "tv-accessories": "Television",
    "monitors": "Display", "movable-screens": "Display", "projectors": "Display",
    "projector-accessories": "Display", "business": "Display",
    "cooking-appliances": "Home Appliances", "refrigerators": "Home Appliances",
    "laundry": "Home Appliances", "dishwashers": "Home Appliances",
    "microwaves": "Home Appliances", "microwave-ovens": "Home Appliances",
    "vacuum-cleaners": "Home Appliances", "ranges": "Home Appliances",
    "home-appliance-accessories": "Home Appliances",
    "cooktops": "Home Appliances", "wall-ovens": "Home Appliances",
    "appliance-packages": "Home Appliances",
    "memory-storage": "Memory Storage",
}
# display_category_major 가 Package 인 model_code (그 외 번들은 실제 카테고리로)
PACKAGE_CODES = {"F-4111BUNDLE1", "F-5B30BUNDLE", "F-9600BUNDLE"}
# 어느 PF 에서 나왔든 모바일 액세서리인 model_code prefix (케이스/충전/배터리/버즈)
_MOBILE_ACC_PREFIX = ("EF-", "EP-", "EI-", "ET-", "EB-", "GP-", "EO-", "EE-", "EJ-")


def _major_for(mc, pf_url):
    """model_code / PF URL 로부터 기대 display_category_major 유도. 못하면 None."""
    u = str(mc).upper()
    if u in PACKAGE_CODES:
        return "Package"
    if u.startswith(_MOBILE_ACC_PREFIX):
        return "Mobile"
    major = SLUG_TO_MAJOR.get(_pf_slug(pf_url))
    if major == "Computers" and _pf_site(pf_url) == "us":
        return "PC"
    return major


# --------------------------------------------------------------------------- #
# 기대값 로딩
# --------------------------------------------------------------------------- #
def _clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, str):
        v = v.strip()
        if v == "" or v.lower() == "nan":
            return None
    return v


def _index_by_model(df):
    """DataFrame 을 model_code -> row(dict) 로. model_code 컬럼이 없으면 빈 dict."""
    if df.empty or "model_code" not in df.columns:
        return {}
    out = {}
    for _, r in df.iterrows():
        mc = _clean(r.get("model_code"))
        if mc is not None:
            out[str(mc)] = {k: _clean(v) for k, v in r.items()}
    return out


def _model_code_column(df):
    """product_order 처럼 model_code 컬럼명이 어긋난 시트에서 실제 코드 컬럼을 추정."""
    if "model_code" in df.columns:
        return "model_code"
    for col in df.columns:
        s = df[col].dropna().astype(str)
        if len(s) and (s.str.match(r"^[A-Z]{2}-[A-Z0-9]{4,}").mean() > 0.5):
            return col
    return None


def load_expected(path):
    xl = pd.ExcelFile(path)
    sh = {n: pd.read_excel(path, sheet_name=n) for n in xl.sheet_names}

    sr = _index_by_model(sh.get("sr_merged_product", pd.DataFrame()))
    mp = _index_by_model(sh.get("model_price", pd.DataFrame()))
    fam = _index_by_model(sh.get("product_family_list", pd.DataFrame()))
    basics = _index_by_model(sh.get("product_spec_basics", pd.DataFrame()))
    color = _index_by_model(sh.get("product_spec_color", pd.DataFrame()))
    stats = _index_by_model(sh.get("product_comment_statistics", pd.DataFrame()))

    # product_spec_spec: model_code -> {spec_name(lower): spec_value}
    spec_df = sh.get("product_spec_spec", pd.DataFrame())
    spec_map = {}
    if not spec_df.empty and {"model_code", "spec_name", "spec_value"}.issubset(spec_df.columns):
        for _, r in spec_df.iterrows():
            mc = _clean(r.get("model_code"))
            if mc is None:
                continue
            spec_map.setdefault(str(mc), {})[str(r["spec_name"]).strip().lower()] = _clean(
                r.get("spec_value")
            )

    def _spec(mc, *keys):  # spec_name 은 로케일마다 다름 (color/colour/couleur, storage/taille...)
        d = spec_map.get(mc, {})
        for k in keys:
            if d.get(k) is not None:
                return d.get(k)
        return None

    all_mc = set(sr) | set(mp) | set(fam) | set(basics)
    expected = {}
    for mc in all_mc:
        g = lambda d, c: (d.get(mc, {}) or {}).get(c)  # noqa: E731
        expected[mc] = {
            "model_code": mc,
            "model_name": g(sr, "model_name") or g(basics, "model_name"),
            "display_name": g(sr, "product_name") or g(fam, "display_name") or g(basics, "display_name"),
            "display_category_major": g(sr, "display_category_major") or g(basics, "category_lv1"),
            "display_category_middle": g(sr, "display_category_middle") or g(basics, "category_lv2"),
            "product_color": (
                g(sr, "product_color") or g(color, "colors")
                or _spec(mc, "color", "colour", "couleur")
            ),
            "capacity": _spec(mc, "storage", "taille", "capacity", "capacité", "stockage"),
            "product_url": g(basics, "product_url"),
            "cta_pd_url": g(basics, "cta_pd_url"),
            "image_url": g(sr, "img_url"),
            "family_id": g(fam, "family_id"),
            "badge": g(basics, "top_flag"),
            "standard_price": g(sr, "standard_price") if g(sr, "standard_price") is not None else g(mp, "price"),
            "final_price": g(sr, "final_price"),
            "on_sale": g(sr, "on_sale"),
            "currency": g(mp, "currency"),
            "stock_level_status": g(mp, "stock_level_status"),
            "is_default": str(g(fam, "key_model_yn") or "").upper() == "Y",
            "review_count": g(stats, "review_num") if g(stats, "review_num") is not None else g(sr, "review_count"),
            "review_rating_score": g(stats, "avg_score") if g(stats, "avg_score") is not None else g(sr, "review_rating_score"),
        }

    # 정렬 순서: product_order 는 대표모델(representative_model)만 sorting_no 를 갖는다.
    # 같은 family 의 나머지 SKU 도 같은 sorting_no 를 공유하므로 family_id 로 전파한다.
    order_map = {}
    fam_df = sh.get("product_family_list", pd.DataFrame())
    mc_to_fam, fam_to_mcs = {}, collections.defaultdict(list)
    if not fam_df.empty and {"model_code", "family_id"}.issubset(fam_df.columns):
        for _, r in fam_df.iterrows():
            mc, fid = _clean(r.get("model_code")), _clean(r.get("family_id"))
            if mc and fid:
                mc_to_fam[str(mc).upper()] = str(fid)
                fam_to_mcs[str(fid)].append(str(mc).upper())

    od = sh.get("product_order", pd.DataFrame())
    if not od.empty and {"sort_type", "sorting_no"}.issubset(od.columns):
        mc_col = _model_code_column(od)
        for _, r in od.iterrows():
            mc = _clean(r.get(mc_col)) if mc_col else None
            st = str(_clean(r.get("sort_type")) or "").lower()
            try:
                no = int(r["sorting_no"])
            except (TypeError, ValueError):
                continue
            if not mc:
                continue
            order_map[(str(mc).upper(), st)] = no
            fid = mc_to_fam.get(str(mc).upper())
            for sib in fam_to_mcs.get(fid, []):
                order_map.setdefault((sib, st), no)

    return expected, order_map


# --------------------------------------------------------------------------- #
# 정규화 & 비교
# --------------------------------------------------------------------------- #
def norm(field, v):
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s.lower() == "nan":
        return None
    if field in ("standard_price", "final_price", "review_rating_score"):
        m = re.search(r"[\d.]+", s.replace(",", ""))
        return round(float(m.group(0)), 2) if m else None
    if field in ("review_count", "sorting_no", "family_id"):
        m = re.search(r"\d+", s)
        return int(m.group(0)) if m else None
    if field == "capacity":
        # '256 GB' vs '256GB (1GB=1Billion byte)* ...' 처럼 뒤에 법적 문구가 붙는다.
        # 용량 토큰만 뽑아 비교.
        m = re.search(r"(\d[\d,]*)\s*(GB|TB)", s, re.I)
        if m:
            return m.group(1).replace(",", "") + m.group(2).upper()
        return s.upper().replace(" ", "")
    if field in ("product_url", "cta_pd_url", "image_url"):
        s = s.split("#", 1)[0].split("?", 1)[0]      # fragment / query 제거
        s = re.sub(r"^https?:", "", s)               # //host 와 https://host 동일 취급
        s = s.rstrip("/").lower()
        if field == "image_url":
            # gallery 이미지 URL: PF 카드는 '-thumb-<id>?$Q90...' 썸네일,
            # DB 는 '-<id>?$PD_GALLERY_PNG$' 원본. '-thumb-' 마커와 끝 자산 id(6자리+)
            # 는 변동분이라 떼고 안정 slug(.../gallery/<slug>-<modelcode>)만 비교.
            s = re.sub(r"-thumb-\d+$", "", s)
            s = re.sub(r"-\d{6,}$", "", s)
        return s
    if field in ("is_default", "on_sale"):
        return s.lower() in ("true", "y", "yes", "1")
    return " ".join(s.split()).lower()              # 내부 개행/연속 공백 정규화


def compare(field, rule, got, exp):
    g, e = norm(field, got), norm(field, exp)
    if e is None:
        return "SKIP", f"expected 없음 (got={got!r})"
    if g is None:
        return "FAIL", f"scraped 없음 (expected={exp!r})"
    if rule == "TOL":
        absd = abs(g - e)
        abs_tol = REVIEW_ABS_TOL.get(field, 0)
        ratio = REVIEW_TOL_RATIO if field in REVIEW_ABS_TOL else TOLERANCE_RATIO
        ok = (e != 0 and absd / abs(e) <= ratio) or (absd <= abs_tol)
        pct = (absd / abs(e) * 100) if e else 0
        return ("PASS" if ok else "FAIL"), (
            f"got={g} expected={e} (Δ{absd:g} / {pct:.0f}%, 허용 ±{ratio * 100:.0f}% 또는 ±{abs_tol})"
        )
    return ("PASS" if g == e else "FAIL"), f"got={got!r} expected={exp!r}"


def compare_sorting_no(sort_type, scraped_rank, rel_rank):
    """sorting_no 를 'PF 내 상대순위' 로 비교.

    사이트는 한 type 을 여러 하위 PF 로 쪼개 보여줘서 절대 sorting_no 는 안 맞지만,
    각 하위 PF 는 DB 정렬을 보존한 슬라이스라 'PF 안에서의 상대 순위' 는 맞는다.
    rel_rank = 그 PF 의 제품들을 DB sorting_no 로 정렬했을 때 이 제품의 위치(1-base).

      Newest      : scraped == rel  또는  scraped - rel == 1 (신제품 유입)  -> PASS
      Recommended : |scraped - rel| <= 2  -> PASS  (사이트 추천정렬은 약간 큐레이션)
    """
    if scraped_rank is None or rel_rank is None:
        return "SKIP", "상대순위 산출 불가 (DB sorting_no 없음/그룹 too small)"
    d = scraped_rank - rel_rank
    st = str(sort_type).lower()
    if st == "newest":
        ok = d in (0, 1)
    else:
        ok = abs(d) <= 2
    return ("PASS" if ok else "FAIL"), (
        f"scraped_rank={scraped_rank} rel_rank={rel_rank} (Δ{d:+d})"
    )


def pick_records(records, mc):
    """model_code(=variant sku) 매칭 스크랩 레코드를 sort_type 별로."""
    mcl = str(mc).lower()
    by_sort = {}
    for r in records:
        if r.get("status"):
            continue
        if mcl in (str(r.get("sku", "")).lower(), str(r.get("model_code", "")).lower()):
            by_sort.setdefault(r.get("sort_type", "?"), r)
    return by_sort


def _relative_ranks(records, order_map):
    """(sku, sort_type) -> (scraped_rank, rel_rank).

    scraped_rank : 그 (PF, sort) 안에서 sorting_no(카드 index) 오름차순 순위(1-base)
    rel_rank     : 같은 집합을 DB sorting_no 로 정렬했을 때 순위(1-base).
                   DB no 를 가진 제품이 3개 미만이면 None (SKIP).
    """
    om = {(str(k).upper(), st): v for (k, st), v in order_map.items()}
    groups = collections.defaultdict(list)
    for r in records:
        if r.get("status") or not r.get("sku") or r.get("sorting_no") is None:
            continue
        groups[(r.get("source_pf_url"), str(r.get("sort_type") or ""))].append(r)

    out = {}
    for (_pf, st), recs in groups.items():
        recs = sorted(recs, key=lambda r: r["sorting_no"])
        rows_ = []
        for i, r in enumerate(recs, 1):
            db = om.get((str(r["sku"]).upper(), st.lower())) or om.get(
                (str(r.get("model_code") or "").upper(), st.lower())
            )
            rows_.append([str(r["sku"]), st, i, db])
        have = [x for x in rows_ if x[3] is not None]
        if len(have) < 3:
            for sku, s, sr, _ in rows_:
                out[(sku, s)] = (sr, None)
            continue
        order = sorted(range(len(have)), key=lambda k: (have[k][3], have[k][2]))
        rel = {have[k][0]: pos for pos, k in enumerate(order, 1)}
        for sku, s, sr, _ in rows_:
            out[(sku, s)] = (sr, rel.get(sku))
    return out


def build_report(records, expected, order_map):
    """rows: [{model_code, field, rule, volatile, result, got, expected, detail}], summary dict."""
    rows = []
    tally = {"PASS": 0, "FAIL": 0, "SKIP": 0, "VOL_FAIL": 0, "NOT_FOUND": 0}
    rel_ranks = _relative_ranks(records, order_map)

    # 기본조합만 수집한 스크랩(--default-only)이면 모든 레코드의 is_default 가 True 라
    # DB 의 key_model_yn(가족 대표) 과는 의미가 달라 비교가 무의미하다 -> is_default SKIP.
    live = [r for r in records if not r.get("status")]
    all_default = bool(live) and all(bool(r.get("is_default")) for r in live)


    for mc, exp in sorted(expected.items()):
        by_sort = pick_records(records, mc)
        if not by_sort:
            rows.append({
                "model_code": mc, "field": "(record)", "rule": "-", "volatile": False,
                "result": "NOT_FOUND", "got": None,
                "expected": exp.get("display_name"),
                "detail": "매칭되는 스크랩 레코드 없음 (스캔 범위 밖이거나 미노출)",
            })
            tally["NOT_FOUND"] += 1
            continue

        ref = by_sort.get("Recommended") or next(iter(by_sort.values()))
        for field, rule, volatile in FIELDS:
            if field == "sorting_no":
                for st, rec in sorted(by_sort.items()):
                    sr, rr = rel_ranks.get(
                        (str(rec.get("sku") or mc), st), (rec.get("sorting_no"), None)
                    )
                    res, detail = compare_sorting_no(st, sr, rr)
                    rows.append({
                        "model_code": mc, "field": f"sorting_no[{st}]", "rule": rule,
                        "volatile": volatile, "result": res,
                        "got": rec.get("sorting_no"),
                        "expected": order_map.get((str(mc).upper(), st.lower())),
                        "detail": detail,
                    })
                    _tally(tally, res, volatile)
                continue
            got_val = ref.get(field)
            if field == "display_category_major" and not got_val:
                got_val = _major_for(mc, ref.get("source_pf_url"))
                res, detail = compare(field, rule, got_val, exp.get(field))
            elif field == "is_default" and all_default:
                res, detail = "SKIP", "is_default 비교 제외: --default-only 스크랩이라 전부 True"
            elif field == "family_id" and (
                ref.get("is_multi_group")
                or not str(ref.get("family_id") or "").isdigit()
            ):
                res, detail = "SKIP", (
                    "family_id 비교 제외: MULTI_GROUP(멀티그룹) 상품은 카드 group-id 가 "
                    "DB family_id 와 다른 체계"
                )
            elif field == "cta_pd_url" and (
                not got_val
                or re.search(r"shop\.samsung\.com|/cart(/|$|\?|#)", str(got_val), re.I)
            ):
                # CA/CA_FR 담기전용 카드는 PDP 링크가 없어 장바구니 URL 이 잡힌다.
                # DB 는 cta_pd_url == product_url 이므로 product_url 로 대조.
                got_val = ref.get("product_url")
                res, detail = compare(field, rule, got_val, exp.get(field))
            else:
                res, detail = compare(field, rule, got_val, exp.get(field))
            rows.append({
                "model_code": mc, "field": field, "rule": rule, "volatile": volatile,
                "result": res, "got": got_val, "expected": exp.get(field),
                "detail": detail,
            })
            _tally(tally, res, volatile)

    summary = {
        "expected_models": len(expected),
        "scraped_records": sum(1 for r in records if not r.get("status")),
        "not_found": tally["NOT_FOUND"],
        "pass": tally["PASS"],
        "fail_strict": tally["FAIL"],
        "fail_volatile": tally["VOL_FAIL"],
        "skip": tally["SKIP"],
        "tolerance_fields": sorted(TOLERANCE_FIELDS),
        "tolerance_ratio": TOLERANCE_RATIO,
    }
    return rows, summary


def _tally(tally, res, volatile):
    if res == "FAIL" and volatile:
        tally["VOL_FAIL"] += 1
    else:
        tally[res] = tally.get(res, 0) + 1


# --------------------------------------------------------------------------- #
def main():
    if len(sys.argv) < 3:
        print("usage: python verify.py <scraped.json> <expected.xlsx>", file=sys.stderr)
        return 2
    records = json.load(open(sys.argv[1], encoding="utf-8"))
    expected, order_map = load_expected(sys.argv[2])
    rows, summary = build_report(records, expected, order_map)

    print(f"{'MODEL':<18} {'FIELD':<26} {'RESULT':<10} DETAIL")
    print("-" * 110)
    for r in rows:
        tag = r["result"] + ("*" if r["volatile"] and r["result"] == "FAIL" else "")
        print(f"{str(r['model_code'])[:17]:<18} {r['field']:<26} {tag:<10} {r['detail']}")
    print("-" * 110)
    print(
        f"models={summary['expected_models']}  PASS={summary['pass']}  "
        f"FAIL={summary['fail_strict']}  FAIL*(volatile)={summary['fail_volatile']}  "
        f"SKIP={summary['skip']}  NOT_FOUND={summary['not_found']}"
    )

    with open("verify_result.json", "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "rows": rows}, f, ensure_ascii=False, indent=2, default=str)
    print("-> verify_result.json")
    return 1 if summary["fail_strict"] else 0


if __name__ == "__main__":
    sys.exit(main())
