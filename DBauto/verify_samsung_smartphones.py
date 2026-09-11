import json
import os
import re
import sys
import time
from urllib.parse import unquote

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

# Windows 콘솔(cp949)에서도 불어(é 등) 출력이 깨지지 않도록 + 파일 리다이렉트 시에도
# 진행 로그가 즉시 보이도록 라인버퍼링 강제(block-buffered 방지).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:  # noqa: BLE001
        pass

SITE_ROOT = "https://www.samsung.com"

# 대상 사이트: us | ca | ca_fr  (URL 경로 프리픽스 그대로)
SITE = (os.environ.get("SAMSUNG_SITE", "us") or "us").strip().lower()
_SITE_CURRENCY = {"us": "USD", "ca": "CAD", "ca_fr": "CAD"}
BASE_URL = f"{SITE_ROOT}/{SITE}/"
SITE_CURRENCY = _SITE_CURRENCY.get(SITE, "USD")


def set_site(site):
    """run_scope_test 등에서 스캔 사이트를 런타임에 바꿀 때 사용."""
    global SITE, BASE_URL, SITE_CURRENCY
    SITE = (site or "us").strip().lower()
    BASE_URL = f"{SITE_ROOT}/{SITE}/"
    SITE_CURRENCY = _SITE_CURRENCY.get(SITE, "USD")


CARD_SELECTOR = ".js-pfv2-product-card.pd21-product-card__item--active"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)

# 스캔할 상단(L0) 메뉴.
#   CATEGORY_MENU : 단일 메뉴 스캔(하위호환)용 기본 메뉴 이름
#   MENUS         : None 이면 GNB 의 모든 L0 메뉴, 리스트면 그 메뉴들만
CATEGORY_MENU = os.environ.get("SAMSUNG_MENU", "Mobile")
MENUS = (
    [m.strip() for m in os.environ["SAMSUNG_MENUS"].split(",") if m.strip()]
    if os.environ.get("SAMSUNG_MENUS")
    else None
)
# PF 단위 재개(resume)용 체크포인트 폴더. 지정 시 PF별 결과 JSON 을 저장/재사용.
RESUME_DIR = os.environ.get("SAMSUNG_RESUME_DIR") or None

# Recommended 로 한 번, Newest 로 한 번 전체 수집한다.
# (정규화 이름, sort code) — code 는 사이트/언어와 무관하게 동일하다.
SORT_SEQUENCE = [("Recommended", "recommended"), ("Newest", "newest")]

# 디버깅/부분 실행용 (환경변수로 조절). 0 또는 미설정이면 전체.
MAX_CARDS = int(os.environ.get("SAMSUNG_MAX_CARDS", "0")) or None
# 카드당 색상 x 용량 조합 수 상한 (테스트용). 0/미설정이면 전체 조합.
MAX_COMBOS = int(os.environ.get("SAMSUNG_MAX_COMBOS", "0")) or None
# 카드의 기본 선택(대표) 조합 1개만 수집 (대표모델만 검증할 때 대폭 빨라짐).
DEFAULT_ONLY = bool(int(os.environ.get("SAMSUNG_DEFAULT_ONLY", "0") or "0"))

# 특정 카테고리만 돌리고 싶을 때: SAMSUNG_CATEGORIES="Galaxy Watch,Galaxy Tab"
ONLY_CATEGORIES = [
    c.strip() for c in os.environ.get("SAMSUNG_CATEGORIES", "").split(",") if c.strip()
]

# 카드/조합 수를 제한하는 옵션이 하나라도 켜져 있으면 개수 검증은 참고용(부분 스캔).
PARTIAL_SCAN = bool(MAX_CARDS or MAX_COMBOS or DEFAULT_ONLY)

# PF(= canonical path) 별 "고정 기대 SKU 수". 데이터 추출 시점 기준 고정치이며,
# 여기 없는 PF 는 개수 검증을 건너뛴다. SAMSUNG_EXPECTED_COUNTS 로 JSON 병합 가능.
#   예: {"/us/watches/all-watches": 30, "/us/smartphones/all-smartphones": 55}
EXPECTED_COUNTS = {
}
try:
    EXPECTED_COUNTS.update(
        json.loads(os.environ.get("SAMSUNG_EXPECTED_COUNTS", "") or "{}")
    )
except Exception:  # noqa: BLE001
    pass
# Newest 정렬은 추출 시점 이후 신제품이 나올 수 있어 +N 까지 pass 로 허용(기본 +1).
NEWEST_COUNT_TOLERANCE = int(os.environ.get("SAMSUNG_NEWEST_TOLERANCE", "1") or "1")

SKU_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-/]{4,}$")

# CA/CA_FR 카드: 색상칩 클릭 시 data-model-code 등은 안 바뀌지만, 카드가 color별
# 개별 PDP 링크(href)를 갖는 경우엔 href 슬러그 끝에 코드가 붙는다.
#   '.../galaxy-s26-fe-blueberry-128gb-sm-s741wzvaxac/' -> 'SM-S741WZVAXAC'
# 완전 통합 패밀리 카드(href가 클릭해도 안 바뀜, 예: Z Fold8 Ultra)는 여기서도 못 잡는다.
_SLUG_SKU_RE = re.compile(r"-((?:sm|ef|ep|et|ei|eo|ej|eb|gp)-[a-z0-9]+)/?(?:[?#].*)?$", re.I)


def _slug_href_sku(card):
    link = first_or_none(
        card, "a.pd21-product-card__image-cta, a.pd21-product-card__name"
    )
    href = link.get_attribute("href") if link else None
    m = _SLUG_SKU_RE.search(href) if href else None
    return m.group(1).upper() if m else None

# 검증 시 완전일치가 아니라 ±10% 이내면 pass 로 처리할 필드
# (데이터 추출 시점과 검증 시점의 시간차로 값이 변동하기 때문)
TOLERANCE_FIELDS = {"review_count", "review_rating_score"}
TOLERANCE_RATIO = 0.10

# 완전일치(pass/fail) 로 검증 가능한, PF 페이지에서 직접 읽히는 필드
EXACT_MATCH_FIELDS = [
    "model_code",
    "sku",
    "model_name",
    "display_name",
    "display_category_major",
    "display_category_middle",
    "product_color",
    "capacity",
    "product_url",
    "cta_pd_url",
    "image_url",
    "family_id",
    "badge",
    "standard_price",
    "final_price",
    "currency",
    "on_sale",
    "stock_level_status",
    "sort_type",
    "sorting_no",
    "is_default",
]

_CUR_SYMBOL = {
    "US$": "USD", "USD": "USD", "CA$": "CAD", "CAD": "CAD", "C$": "CAD",
    "€": "EUR", "£": "GBP", "₩": "KRW",
}
_CUR_TOKEN = r"US\$|CA\$|C\$|USD|CAD|\$|€|£|₩"
# 금액: 앞/뒤 어디든 통화 기호 허용, 천단위(., ,, 공백/nbsp) + 소수(., ,) 혼용
_MONEY_RE = re.compile(
    rf"(?:(?P<pre>{_CUR_TOKEN})\s*)?"
    r"(?P<num>\d[\d\s .,]*\d|\d)"
    rf"(?:\s*(?P<post>{_CUR_TOKEN}))?"
)
_MONTHLY_TAIL_RE = re.compile(r"^\s*/\s*mo(?:is|nth)?s?\b", re.I)
_MONTHS_RE = re.compile(r"(?:for|pour|pendant)\s*(\d+)\s*mo(?:is|nths?|s)?\b", re.I)


def _parse_amount(num_str):
    """'1,799.99' / '1 049,99' / '1.799,99' / '949,99' -> float. 실패 시 None."""
    s = str(num_str).strip().replace(" ", " ").replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        # 뒤에 오는 구분자를 소수점으로 본다
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            s = parts[0] + "." + parts[1]          # 불어 소수점
        else:
            s = s.replace(",", "")                 # 천단위
    try:
        return float(s)
    except ValueError:
        return None


def _iter_money(text):
    """(amount, currency_raw, is_monthly) 를 순서대로 yield."""
    if not text:
        return
    for m in _MONEY_RE.finditer(text):
        num = m.group("num")
        cur = m.group("pre") or m.group("post")
        has_dec = bool(re.search(r"[.,]\d{1,2}$", num.replace(" ", " ").replace(" ", "")))
        if not cur and not has_dec:
            continue  # 'for 24 mos' 같은 순수 정수는 금액 아님
        amt = _parse_amount(num)
        if amt is None:
            continue
        is_monthly = bool(_MONTHLY_TAIL_RE.match(text[m.end():m.end() + 10]))
        yield amt, cur, is_monthly


def _money_from(text):
    """문자열에서 (full_price, monthly_price, currency) 추출.
    full = 월납 아닌 금액 중 최댓값, monthly = 월납 금액 중 최솟값.
    """
    full, monthly, cur = [], [], None
    for amt, craw, is_monthly in _iter_money(text):
        if cur is None and craw:
            cur = _CUR_SYMBOL.get(craw.upper(), craw)
        (monthly if is_monthly else full).append(amt)
    return (max(full) if full else None), (min(monthly) if monthly else None), cur


def _to_number(text):
    if text is None:
        return None
    m = re.search(r"\d[\d\s .,]*\d|\d", str(text))
    return _parse_amount(m.group(0)) if m else None


def parse_price_save(text):
    """취소선(정가) 문자열 -> {'currency', 'price'}."""
    if not text:
        return None
    full, _m, cur = _money_from(text)
    return {"currency": cur, "price": full}


def parse_price_current(text):
    """'From $1,799.99 or $75.00/mo for 24mo' / 'Prix total: 949,99 $' 등 현재가 파싱."""
    if not text:
        return {}
    full, monthly, cur = _money_from(text)
    out = {}
    if full is not None:
        out["final_price"] = full
    if monthly is not None:
        out["monthly_price"] = monthly
    if cur:
        out["currency"] = cur
    mo = _MONTHS_RE.search(text)
    if mo:
        out["monthly_months"] = int(mo.group(1))
    return out


def first_or_none(scope, selector):
    loc = scope.locator(selector).first
    return loc if loc.count() > 0 else None


_CONSENT_JS = """
() => {
    const ids = ['consent_blackbar', 'truste-consent-track'];
    for (const id of ids) document.getElementById(id)?.remove();
    document.querySelectorAll(
        '.trustarc-banner, #teconsent, .truste_overlay, .truste_box_overlay'
    ).forEach((el) => el.remove());
}
"""


def dismiss_consent(page):
    """TrustArc 쿠키 배너가 클릭을 가로채지 못하도록 제거 + 재삽입 대비 스타일 주입."""
    try:
        btn = page.locator("#truste-consent-button")
        if btn.count() and btn.first.is_visible():
            btn.first.click(timeout=3000)
    except Exception:  # noqa: BLE001
        pass
    try:
        page.evaluate(_CONSENT_JS)
    except Exception:  # noqa: BLE001
        pass
    try:
        page.add_style_tag(
            content="#consent_blackbar,#truste-consent-track,.trustarc-banner,"
            ".truste_overlay,.truste_box_overlay{display:none!important;"
            "pointer-events:none!important;}"
        )
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
# 정렬 (Sort) 제어
# --------------------------------------------------------------------------- #
def read_current_sort(page):
    """현재 선택된 정렬의 표시 이름 (로케일에 따라 다를 수 있음, 로그용)."""
    el = first_or_none(page, "span.pd21-sort__opener-name")
    return " ".join(el.inner_text().split()) if el else None


def read_current_sort_code(page):
    """현재 선택된 정렬 코드 ('recommended' / 'newest' ...). 사이트/언어 불문 동일.

    체크된 라디오 input 의 id 로 판정한다 (US/CA 공통).
    """
    el = first_or_none(
        page,
        ".pd21-sort__contents input[type='radio']:checked, "
        ".pd21-sort__list input[type='radio']:checked",
    )
    if el:
        cid = el.get_attribute("id")
        if cid:
            return cid.strip().lower()
    lbl = first_or_none(
        page, "label.pd21-sort__select-option-label:has(input:checked)"
    )
    return (lbl.get_attribute("data-sort-code") or "").strip().lower() or None if lbl else None


def set_sort(page, sort_name, sort_code):
    """정렬을 sort_code 로 바꾸고 그리드 재렌더까지 대기.

    반환: 적용된 정규화 이름(sort_name) / 이 PF 에 해당 정렬이 없으면 None.
    US 는 label[data-sort-code], CA 는 label[for=code] / input#code 를 쓴다.
    """
    dismiss_consent(page)
    opener = page.locator("button.pd21-sort__opener").first
    if opener.count() == 0:
        return None
    try:
        opener.scroll_into_view_if_needed(timeout=3000)
    except PWTimeout:
        pass

    if read_current_sort_code(page) == sort_code:
        return sort_name

    opener.click()
    page.wait_for_timeout(500)
    if read_current_sort_code(page) == sort_code:
        page.keyboard.press("Escape")
        return sort_name

    option = page.locator(
        f".pd21-sort label.pd21-sort__select-option-label[data-sort-code='{sort_code}'], "
        f".pd21-sort label[for='{sort_code}'], "
        f".pd21-sort input#{sort_code}"
    ).first
    if option.count() == 0:
        page.keyboard.press("Escape")
        return None  # 이 PF/사이트에 해당 정렬 없음
    try:
        option.click(timeout=5000)
    except Exception:  # noqa: BLE001 - 숨겨진 라디오 등
        try:
            option.click(force=True, timeout=2000)
        except Exception:  # noqa: BLE001
            option.evaluate("el => el.click()")

    # 모바일 레이아웃은 Apply 버튼을 눌러야 반영됨 (데스크톱은 즉시 반영)
    apply_btn = page.locator("button.pd21-sort__apply-cta-mob")
    if apply_btn.count() and apply_btn.first.is_visible():
        apply_btn.first.click()

    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PWTimeout:
        pass
    page.wait_for_timeout(1500)
    page.wait_for_selector(CARD_SELECTOR, timeout=30000)
    page.wait_for_timeout(1000)
    return sort_name


# --------------------------------------------------------------------------- #
# 카드 단위 추출
# --------------------------------------------------------------------------- #
def _feedback_params(card):
    """카드 링크의 data-feedback-param 을 dict 로 파싱 (pn/pi/dc/sc/dg/sb/pr/cg ...).

    주의: 이 속성은 엄격한 form-urlencoded 가 아니다. 공백과 '+' 를 문자 그대로
    쓰기 때문에 parse_qs(내부적으로 unquote_plus) 를 쓰면 'OptiDry+' 의 '+' 가
    공백으로 뭉개진다. '&'/'=' 로만 쪼개고 %XX 만 unquote 한다.
    """
    el = first_or_none(
        card, "a.pd21-product-card__image-cta, a.pd21-product-card__name"
    )
    raw = el.get_attribute("data-feedback-param") if el else None
    if not raw:
        return {}
    out = {}
    for part in raw.split("&"):
        if not part:
            continue
        k, _sep, v = part.partition("=")
        out.setdefault(unquote(k), unquote(v))  # 첫 값 유지
    return out


def _drop_frag(href):
    """URL 에서 #fragment, ?query 제거."""
    return href.split("#", 1)[0].split("?", 1)[0] if href else href


def _strip_buy_url(href):
    """구매 링크 정규화.
    스마트폰:  .../buy/<variant-slug>  -> .../buy/
    그 외(가전 등): /buy/ 세그먼트가 없으므로 PDP 경로를 그대로 사용.
    """
    href = _drop_frag(href)
    if not href:
        return None
    m = re.match(r"(.*/buy/)", href)
    return m.group(1) if m else href


def _promo_url(href):
    """카드 링크를 DB product_url 형태로 정규화.
      .../galaxy-s26-fe/buy/...                         -> .../galaxy-s26-fe/
      .../where-to-buy/<slug>-sku-<code>/<code path>/   -> .../<slug>-sku-<code>/
    비구매 variant 의 learn-more 는 /where-to-buy/ 를 거치고 뒤에 모델코드 경로가
    덧붙는데, DB 는 '...-sku-<code>' 에서 끝난다.
    """
    href = _drop_frag(href)
    if not href:
        return None
    href = href.replace("/where-to-buy/", "/")
    # '-sku-<code>' 이후 꼬리(모델코드 경로 등) 제거
    href = re.sub(r"(-sku-[a-z0-9-]+)(/[a-z0-9/._-]*)?/?$", r"\1/", href)
    href = re.sub(r"/buy(/.*)?$", "/", href)
    if not href.endswith("/"):
        href += "/"
    return href


def _variant_fields(card):
    """선택된 색상/용량(variant)에 따라 바뀌는 카드 필드.

    이 값들은 칩을 클릭하면 카드 DOM 이 갱신되므로 variant 마다 다시 읽어야 한다
    (기존엔 카드 기본값을 모든 조합에 복사해 EW/HW 같은 형제 variant 가
     엉뚱한 URL·이름·이미지를 갖는 버그가 있었음).
    """
    cb = first_or_none(card, "input.pd21-product-card__compare-checkbox")

    # 파란 "New" 배지뿐 아니라 프로모션 배지("Labor Day", "BUY MORE, SAVE MORE" 등)도 읽는다
    badge_el = first_or_none(
        card,
        "div.pd21-product-card__badge span.badge-icon, "
        "span.badge-icon.badge-icon--label-v2",
    )
    badge_text = badge_el.inner_text().strip() if badge_el else None

    img_el = first_or_none(card, "div.pd21-product-card__image img")
    image_url = (
        (img_el.get_attribute("src") or img_el.get_attribute("data-desktop-src"))
        if img_el
        else None
    )
    rep_image_url = cb.get_attribute("data-img-src") if cb else None

    name_el = first_or_none(card, "div.pd21-product-card__name-wrap")
    # CA 카드는 inner_text 에 \n\n 이 섞여 나오므로 공백 1칸으로 정규화
    name_text = " ".join(name_el.inner_text().split()) if name_el else None

    link_el = first_or_none(
        card, "a.pd21-product-card__image-cta, a.pd21-product-card__name"
    )
    model_name = link_el.get_attribute("data-modelname") if link_el else None

    learn_el = first_or_none(
        card, "div.pd21-product-card__cta a.cta__link:not([href*='/buy'])"
    )
    product_url = _promo_url(
        (learn_el.get_attribute("href") if learn_el else None)
        or (link_el.get_attribute("href") if link_el else None)
    )

    # 구매 링크:
    #   US 스마트폰  : a.cta__link[href*='/buy']
    #   US 가전      : a.cta__link:has(button[an-ac='Buy'])  (href 에 /buy 없음)
    #   CA/CA_FR     : a.js-pfv2-buy-now (href='javascript:;', 경로는 data-config_info)
    buy_el = first_or_none(
        card,
        "div.pd21-product-card__cta a.cta__link:has(button[an-ac='Buy']), "
        "div.pd21-product-card__cta a.cta__link[href*='/buy'], "
        "div.pd21-product-card__cta a.js-pfv2-buy-now, "
        "div.pd21-product-card__cta a[data-config_info]",
    )
    buy_url = None
    if buy_el:
        href = (buy_el.get_attribute("href") or "").strip()
        if href and not href.lower().startswith("javascript:"):
            buy_url = href
        buy_url = (
            buy_url
            or buy_el.get_attribute("data-config_info")
            or buy_el.get_attribute("data-link_info")
            or None
        )
    # CA 담기 버튼은 일반 장바구니 URL(shop.samsung.com/.../cart) 이라 PDP 가 아님
    if buy_url and re.search(r"shop\.samsung\.com|/cart(\b|$|[/?#])", buy_url, re.I):
        buy_url = None

    family_id = None
    is_multi_group = False
    group_id = cb.get_attribute("data-group-id") if cb else None
    if group_id:
        is_multi_group = "MULTI_GROUP" in group_id.upper()
        # 'FMY_ID_600251' -> '600251', 'MULTI_GROUP_ID_601773' -> '601773'
        m = re.search(r"(\d+)\s*$", group_id)
        family_id = m.group(1) if m else (group_id.strip() or None)

    # 평점 / 리뷰 수 (±10% 허용 대상)
    rp = first_or_none(card, "strong.rating__point span:last-child")
    review_rating_score = _to_number(rp.inner_text()) if rp else None
    rc = first_or_none(card, "em.rating__review-count span:last-child")
    review_count = int(_to_number(rc.inner_text())) if rc and _to_number(rc.inner_text()) is not None else None

    fp = _feedback_params(card)

    # Buy 링크가 없는 경우(US where-to-buy variant, CA 담기전용 카드) DB 는
    # cta_pd_url == product_url (PDP 경로) 이므로 product_url 로 대체한다.
    cta_pd_url = _strip_buy_url(buy_url)
    if not cta_pd_url and product_url and product_url.startswith("/"):
        cta_pd_url = product_url

    display_name = " ".join((fp.get("pn") or name_text or "").split()) or None

    return {
        "model_name": model_name,
        "name": name_text,
        "display_name": display_name,
        "display_category_major": fp.get("dc"),
        "display_category_middle": fp.get("sc"),
        "sub_family": fp.get("dg"),
        "category_code": fp.get("cg"),
        "badge": badge_text,
        "image_url": image_url,
        "rep_image_url": rep_image_url,
        "product_url": product_url,
        "cta_pd_url": cta_pd_url,
        "buy_url": buy_url,
        "family_id": family_id,
        "is_multi_group": is_multi_group,
        "review_count": review_count,
        "review_rating_score": review_rating_score,
        "feedback_model_code": fp.get("pi"),
        "feedback_rank": int(fp["pr"]) if str(fp.get("pr", "")).isdigit() else None,
    }


def extract_card_base(card):
    """카드 불변 정보(product_id) + 기본 선택 variant 필드."""
    product_id = card.get_attribute("data-productidx")
    cb = first_or_none(card, "input.pd21-product-card__compare-checkbox")
    if product_id is None and cb:
        product_id = cb.get_attribute("data-productidx")
    base = {"product_id": product_id}
    base.update(_variant_fields(card))
    return base


def _checked_chip_value(card, wrap_class):
    """카드가 기본 선택(is-checked)한 칩 값."""
    wrap = card.locator(f"div.{wrap_class}")
    if wrap.count() == 0:
        return None
    slide = wrap.locator("div.option-selector-v2__swiper-slide.is-checked").first
    if slide.count() == 0:
        return None
    v = slide.get_attribute("data-chip-value")
    if not v:
        t = slide.locator("span.option-selector-v2__size-text")
        v = t.inner_text().strip() if t.count() else slide.get_attribute("data-chip-code")
    if not v:
        btn = slide.locator("button").first
        if btn.count():
            v = _chip_label_from_btn(btn)
    return v


def _max_save(card):
    """카드에 표기된 모든 할인액(Save $X / Économisez X $ / -X $) 중 최댓값. 없으면 None."""
    hi = card.locator("div.price-ux__wrap span.price-ux__price-save-highlight")
    saves = []
    for i in range(hi.count()):
        full, _m, _c = _money_from(hi.nth(i).inner_text() or "")
        if full is not None:
            saves.append(full)
    return max(saves) if saves else None


def _card_list_price(card):
    """CA 카드의 담기/구매 버튼 data-price = 정가(list). 현재가 문자열엔 프로모가만
    보이는 경우가 많아 이걸로 standard_price 를 보정한다."""
    el = first_or_none(
        card,
        "div.pd21-product-card__cta [data-price], "
        "div.pd21-product-card__cta-wrap [data-price]",
    )
    return _to_number(el.get_attribute("data-price")) if el else None


def read_prices(card):
    """standard_price / final_price / currency / on_sale / 할인액 / 월 납부.

    final_price(최종 = 할인가) 규칙:
      - 카드에 'Save $X'(price-save) 표기가 있으면
            final_price = standard_price - max(Save $X)   ← 최대 할인 적용
      - 표기가 없으면 final_price = standard_price (= 현재가)
    CA 는 취소선(정가)을 안 보여주고 현재가에 프로모가만 나오므로,
    담기 버튼의 data-price(정가)가 있으면 그걸 standard_price 로 쓴다.
    """
    out = {
        "standard_price": None,
        "final_price": None,
        "currency": None,
        "on_sale": False,
        "discount_amount": None,
        "monthly_price": None,
        "monthly_months": None,
    }
    was = first_or_none(
        card,
        "div.price-ux__wrap p.price-ux__price-save span.price-ux__price-save-was",
    )
    cur = first_or_none(card, "div.price-ux__wrap .price-ux__price-current")

    cur_info = parse_price_current(cur.inner_text()) if cur else {}
    current_price = cur_info.get("final_price")  # 월납이 아닌 실제 현재가(=CA 프로모가)
    out["currency"] = cur_info.get("currency")
    out["monthly_price"] = cur_info.get("monthly_price")
    out["monthly_months"] = cur_info.get("monthly_months")

    if was:
        ps = parse_price_save(was.inner_text().strip())
        out["standard_price"] = ps.get("price") if ps else None
        if out["currency"] is None and ps and ps.get("currency"):
            out["currency"] = ps["currency"]

    list_price = _card_list_price(card)
    if list_price is not None and (
        out["standard_price"] is None or list_price >= out["standard_price"]
    ):
        out["standard_price"] = list_price

    # 통화 기호($)만으로는 USD/CAD 구분이 안 되므로 사이트 기준으로 확정
    if out["currency"] in (None, "$"):
        out["currency"] = SITE_CURRENCY

    save = _max_save(card)

    # 기준가가 없으면 현재가를 기준가로 사용
    if out["standard_price"] is None:
        out["standard_price"] = current_price

    # 최종가: Save 표기 있으면 기준가-할인, 아니면 현재가, 그것도 없으면 기준가
    if out["standard_price"] is not None and save is not None:
        out["final_price"] = round(out["standard_price"] - save, 2)
    elif current_price is not None:
        out["final_price"] = current_price
    else:
        out["final_price"] = out["standard_price"]

    # on_sale: 명시적 Save 표기가 있거나, 기준가 > 최종가면 세일 중
    if save is not None:
        out["on_sale"] = True
        out["discount_amount"] = save
    elif (
        out["standard_price"] is not None
        and out["final_price"] is not None
        and out["final_price"] < out["standard_price"]
    ):
        out["on_sale"] = True
        out["discount_amount"] = round(out["standard_price"] - out["final_price"], 2)

    return out


def read_stock_status(card):
    """카드 CTA 로 재고 상태 추정: inStock / outOfStock / notifyMe / comingSoon / unknown."""
    cta = card.locator("div.pd21-product-card__cta-wrap")
    txt = (cta.inner_text().lower() if cta.count() else "")
    if "sold out" in txt or "out of stock" in txt:
        return "outOfStock"
    if "notify me" in txt or "coming soon" in txt or "pre-order" in txt or "preorder" in txt:
        return "notifyMe" if "notify" in txt else "comingSoon"
    if "buy" in txt or "add to cart" in txt:
        return "inStock"
    return "unknown"


def read_price_save(card):
    el = first_or_none(
        card,
        "div.price-ux__wrap.price-ux__wrap--ux-v2 "
        "p.price-ux__price-save span.price-ux__price-save-was",
    )
    return parse_price_save(el.inner_text().strip()) if el else None


def read_card_modelcode(card):
    cb = first_or_none(card, "input.pd21-product-card__compare-checkbox")
    if cb:
        v = cb.get_attribute("data-model-code") or cb.get_attribute("data-modelcode")
        if v:
            return v
    link = first_or_none(card, "a.pd21-product-card__name")
    v = link.get_attribute("data-modelcode") if link else None
    return v or _slug_href_sku(card)


def _chip_label_from_btn(btn):
    """CA/CA_FR 칩은 slide 에 data-chip-value 가 없다. 버튼의 an-la='color:titanium gray'
    / aria-label / hidden span 에서 라벨을 뽑는다."""
    al = btn.get_attribute("an-la") or btn.get_attribute("aria-label") or ""
    m = re.search(r"[:\-]\s*(.+)$", al)
    if m:
        return m.group(1).strip()
    hs = btn.locator("span.hidden, span.blind, span.option-selector-v2__color-name")
    if hs.count():
        t = hs.first.inner_text().strip()
        if t and t.lower() != "selected":
            return t
    return None


def _chip_options(card, wrap_class, btn_class):
    """(라벨, 버튼 로케이터) 목록을 반환. 옵션 셀렉터가 없으면 빈 리스트."""
    wrap = card.locator(f"div.{wrap_class}")
    if wrap.count() == 0:
        return []
    slides = wrap.locator("div.option-selector-v2__swiper-slide")
    btns = wrap.locator(f"button.{btn_class}")
    out = []
    for i in range(min(slides.count(), btns.count())):
        slide = slides.nth(i)
        label = slide.get_attribute("data-chip-value")
        if not label:
            txt = slide.locator("span.option-selector-v2__size-text")
            label = (
                txt.inner_text().strip()
                if txt.count()
                else slide.get_attribute("data-chip-code")
            )
        if not label:
            label = _chip_label_from_btn(btns.nth(i))
        out.append((label or f"opt{i}", btns.nth(i)))
    return out


def _click_chip(page, btn):
    """옵션 칩 클릭. 스와이퍼 캐러셀에 가려 뷰포트 밖이면 JS 클릭으로 폴백."""
    ok = False
    try:
        btn.scroll_into_view_if_needed(timeout=3000)
        btn.click(timeout=4000)
        ok = True
    except Exception:  # noqa: BLE001
        try:
            btn.click(force=True, timeout=2000)
            ok = True
        except Exception:  # noqa: BLE001
            try:
                btn.evaluate("el => el.click()")
                ok = True
            except Exception:  # noqa: BLE001
                ok = False
    page.wait_for_timeout(700)
    return ok


def _close_quick_view(page):
    close = page.locator("button.pd21-quick-view__close").first
    try:
        if close.count() and close.is_visible():
            close.click(timeout=3000)
        else:
            page.keyboard.press("Escape")
    except PWTimeout:
        page.keyboard.press("Escape")
    page.wait_for_timeout(500)


def _open_quick_view_once(page, card):
    btn = card.locator("button.pd21-product-card__quickview_btn").first
    if btn.count() == 0:
        return None
    try:
        btn.scroll_into_view_if_needed(timeout=3000)
        btn.click(timeout=5000)
    except Exception:  # noqa: BLE001
        try:
            btn.click(force=True, timeout=2000)
        except Exception:  # noqa: BLE001
            btn.evaluate("el => el.click()")

    # 패널이 보이고 SKU 텍스트가 채워질 때까지만 대기 (이전 값과의 비교는 하지 않는다:
    # 크기 옵션처럼 조합이 바뀌어도 SKU 가 동일할 수 있음).
    try:
        page.wait_for_function(
            """() => {
                const els = document.querySelectorAll('p.pd21-quick-view__sku');
                for (const el of els) {
                    if (el.offsetParent === null) continue;
                    if ((el.textContent || '').trim().length > 0) return true;
                }
                return false;
            }""",
            timeout=6000,
        )
    except PWTimeout:
        pass

    sku_loc = page.locator("p.pd21-quick-view__sku:visible").first
    if sku_loc.count():
        return sku_loc.inner_text().strip() or None
    any_loc = page.locator("p.pd21-quick-view__sku").first
    return (any_loc.inner_text().strip() or None) if any_loc.count() else None


def read_quick_view_sku(page, card):
    """Quick view 슬라이드를 열어 p.pd21-quick-view__sku 값을 읽고 다시 닫는다.

    빈 값/형식 불일치일 때만 한 번 더 시도한다 (렌더 지연 대비).
    """
    sku = None
    for _ in range(2):
        sku = _open_quick_view_once(page, card)
        _close_quick_view(page)
        if sku and SKU_RE.match(sku):
            break
        page.wait_for_timeout(500)
    return sku


# --------------------------------------------------------------------------- #
# DOM 기반 variant SKU (Quick View 를 열지 않음)
#
# 칩을 선택하면 카드 DOM 이 해당 variant 코드로 갱신된다. 서로 독립적인 소스
# (compare-checkbox data-model-code / id, image-cta data-feedback-param 의 pi=)
# 가 항상 일치하며, 표본 검증에서 Quick View SKU 와 100% 동일했다.
# --------------------------------------------------------------------------- #
# 첫 N개 variant 는 Quick View 로 교차검증 (SAMSUNG_QV_AUDIT_N, PF 마다 리셋)
QV_AUDIT_N = int(os.environ.get("SAMSUNG_QV_AUDIT_N", "0") or "0")
_QV_AUDIT_LEFT = 0


def _consume_qv_audit():
    global _QV_AUDIT_LEFT
    if _QV_AUDIT_LEFT > 0:
        _QV_AUDIT_LEFT -= 1
        return True
    return False


def _card_codes(card):
    """카드 DOM 의 현재 variant 코드 후보 리스트 (대문자, 형식검증 통과분만)."""
    raw = []
    cb = first_or_none(card, "input.pd21-product-card__compare-checkbox")
    if cb:
        raw += [
            cb.get_attribute("data-model-code"),
            cb.get_attribute("data-modelcode"),
            cb.get_attribute("id"),
        ]
    link = first_or_none(
        card, "a.pd21-product-card__image-cta, a.pd21-product-card__name"
    )
    if link:
        raw.append(link.get_attribute("data-modelcode"))
        fp = link.get_attribute("data-feedback-param") or ""
        m = re.search(r"(?:^|&)pi=([^&]+)", fp)
        if m:
            raw.append(m.group(1))
    # href 슬러그 코드: CA/CA_FR 에서 색상마다 바뀌는 유일한 소스라 2표를 줘서
    # (안 바뀌는) data-model-code 같은 static 값보다 다수결에서 이기게 한다.
    slug = _slug_href_sku(card)
    if slug:
        raw += [slug, slug]
    out = []
    for c in raw:
        if c and SKU_RE.match(c.strip()):
            out.append(c.strip().upper())
    return out


def read_variant_sku(page, card, prev_code=None):
    """칩 선택 후 카드 DOM 에서 variant SKU 를 읽는다 (Quick View 안 엶).

    반환: (sku, source, mismatch)
      source   : 'dom' | 'dom-stable' | 'dom-nochange' | 'quickview' | None
      mismatch : Quick View 교차검증 시 불일치면 {'dom':.., 'qv':..}, 아니면 None
    """
    prev = (prev_code or "").upper() or None
    chosen, source = None, None
    for i in range(15):  # 최대 ~3s
        codes = _card_codes(card)
        if codes:
            cur = max(set(codes), key=codes.count)
            agree = codes.count(cur)
            if agree >= 2 and (prev is None or cur != prev):
                chosen, source = cur, "dom"
                break
            if agree >= 3 and i >= 4:  # 값이 안 바뀐 조합(기본 등) — 안정 후 수용
                chosen, source = cur, "dom-stable"
                break
        page.wait_for_timeout(200)
    if chosen is None:
        codes = _card_codes(card)
        if codes:
            chosen, source = max(set(codes), key=codes.count), "dom-nochange"

    mismatch = None
    audit = _consume_qv_audit()
    if chosen is None or audit:
        qv = None
        try:
            qv = read_quick_view_sku(page, card)
        except Exception:  # noqa: BLE001
            _close_quick_view(page)
        if chosen is None:
            chosen, source = qv, "quickview"
        elif qv and qv.upper() != chosen:
            mismatch = {"dom": chosen, "qv": qv}
    return chosen, source, mismatch


def _variant_record(
    page, card, base, sort_type, sorting_no, color_name, capacity, is_default,
    prev_code=None,
):
    rec = dict(base)
    sku = src = None
    mism = None
    try:
        sku, src, mism = read_variant_sku(page, card, prev_code)
    except Exception as e:  # noqa: BLE001 - 조합 하나 실패해도 계속 진행
        rec["error"] = f"{type(e).__name__}: {e}"
        _close_quick_view(page)

    # read_variant_sku 가 DOM 이 새 variant 로 갱신되길 기다렸으므로,
    # 이 시점에서 카드 필드(URL/이름/이미지/배지 등)를 다시 읽는다.
    rec.update(_variant_fields(card))

    modelcode = read_card_modelcode(card)
    rec.update(
        {
            "sort_type": sort_type,
            "sorting_no": sorting_no,
            "product_color": color_name,
            "color_name": color_name,  # 하위호환
            "capacity": capacity,
            "is_default": is_default,
            "modelcode": modelcode,
            "model_code": modelcode,
            "stock_level_status": read_stock_status(card),
            "price_save": read_price_save(card),  # 하위호환
            "sku": sku,
            "sku_source": src,
        }
    )
    rec.update(read_prices(card))
    if mism:
        rec["sku_audit_mismatch"] = mism
    return rec


def extract_card_variants(page, card, base, sort_type, sorting_no):
    """카드의 모든 색상 x 용량(또는 사이즈) 조합을 순회하며 SKU + 검증 필드를 수집."""
    records = []
    default_color = _checked_chip_value(card, "option-selector-v2__wrap--color-chip")
    default_capacity = _checked_chip_value(card, "option-selector-v2__wrap--capacity")

    dc = _card_codes(card)
    prev_code = max(set(dc), key=dc.count) if dc else None  # 카드 현재(기본) 코드

    if DEFAULT_ONLY:
        return [
            _variant_record(
                page, card, base, sort_type, sorting_no,
                default_color, default_capacity, True, prev_code=None,
            )
        ]

    colors = _chip_options(
        card, "option-selector-v2__wrap--color-chip", "option-selector-v2__color"
    )
    if not colors:
        colors = [(None, None)]

    for color_name, color_btn in colors:
        if color_btn is not None:
            _click_chip(page, color_btn)

        # 색상마다 선택 가능한 용량이 달라질 수 있으므로 다시 읽는다.
        caps = _chip_options(
            card, "option-selector-v2__wrap--capacity", "option-selector-v2__size"
        )
        if not caps:
            caps = [(None, None)]

        for capacity, cap_btn in caps:
            if MAX_COMBOS and len(records) >= MAX_COMBOS:
                return records
            if cap_btn is not None:
                _click_chip(page, cap_btn)

            rec = _variant_record(
                page, card, base, sort_type, sorting_no, color_name, capacity,
                color_name == default_color and capacity == default_capacity,
                prev_code=prev_code,
            )
            if rec.get("sku"):
                prev_code = rec["sku"]
            records.append(rec)
    return records


def extract_all(page, sort_type, progress=None):
    """현재 정렬 상태에서 활성 카드 전체를 순회."""
    page.wait_for_selector(CARD_SELECTOR, timeout=30000)
    page.wait_for_timeout(1200)

    # 무한 스크롤 PF 는 첫 배치만 렌더되므로 끝까지 스크롤해 모두 로드한다.
    # (정렬을 바꾸면 그리드가 처음부터 다시 그려지므로 sort 마다 호출)
    load_all_cards(page)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(400)

    cards = page.locator(CARD_SELECTOR)
    total = cards.count()
    if MAX_CARDS:
        total = min(total, MAX_CARDS)
    if progress:
        progress.set_cards(total)

    results = []
    for i in range(total):
        card = cards.nth(i)
        try:
            card.scroll_into_view_if_needed(timeout=3000)
        except PWTimeout:
            pass
        try:
            base = extract_card_base(card)
            results.extend(
                extract_card_variants(page, card, base, sort_type, i + 1)
            )
        except Exception as e:  # noqa: BLE001 - 카드 하나 실패해도 다음 카드 진행
            results.append(
                {
                    "sort_type": sort_type,
                    "product_id": card.get_attribute("data-productidx"),
                    "status": f"card error: {type(e).__name__}: {e}",
                }
            )
            _close_quick_view(page)
        if progress:
            progress.card(i + 1, sort_type, len(results))
    return results


# --------------------------------------------------------------------------- #
# 카테고리 (Mobile L0 메뉴의 하위 제품군) 탐색 & 이동
# --------------------------------------------------------------------------- #
_DISCOVER_JS = r"""
(menuText) => {
    const l0 = [...document.querySelectorAll('a.nv00-gnb-v4__l0-menu-link')]
        .find((a) => a.textContent.trim().toLowerCase().startsWith(menuText.toLowerCase()));
    if (!l0) return [];
    let node = l0;
    while (node && node.parentElement) {
        node = node.parentElement;
        if (node.querySelector && node.querySelector('a.nv00-gnb-v4__l1-menu-link')) break;
    }
    const seen = new Set();
    const out = [];
    for (const a of node.querySelectorAll('a.nv00-gnb-v4__l1-menu-link')) {
        const text = a.textContent.trim().replace(/\s+/g, ' ');
        const href = a.getAttribute('href');
        if (!text || !href || seen.has(href)) continue;
        seen.add(href);
        out.push({ name: text.replace(/\s*(NEW|NOUVEAUT\u00c9|NOUVEAUTE|NOUVEAU)$/i, '').trim(), href: href });
    }
    return out;
}
"""


def discover_categories(page):
    """CATEGORY_MENU 플라이아웃을 열어 [{name, href}, ...] 를 반환 (단일 메뉴, 하위호환)."""
    try:
        page.locator(
            "a.nv00-gnb-v4__l0-menu-link", has_text=CATEGORY_MENU
        ).first.hover()
        page.wait_for_timeout(1000)
    except Exception:  # noqa: BLE001
        pass
    cats = page.evaluate(_DISCOVER_JS, CATEGORY_MENU)
    if ONLY_CATEGORIES:
        cats = [c for c in cats if c["name"] in ONLY_CATEGORIES]
    return cats


_DISCOVER_ALL_JS = r"""
() => {
    const l0s = [...document.querySelectorAll('a.nv00-gnb-v4__l0-menu-link')];
    const out = [];
    for (const l0 of l0s) {
        const l0name = l0.textContent.trim().replace(/\s+/g, ' ');
        let node = l0;
        while (node && node.parentElement) {
            node = node.parentElement;
            if (node.querySelector && node.querySelector('a.nv00-gnb-v4__l1-menu-link')) break;
        }
        if (!node) continue;
        const seen = new Set();
        for (const a of node.querySelectorAll('a.nv00-gnb-v4__l1-menu-link')) {
            const text = a.textContent.trim().replace(/\s+/g, ' ').replace(/\s*(NEW|NOUVEAUT\u00c9|NOUVEAUTE|NOUVEAU)$/i, '').trim();
            const href = a.getAttribute('href');
            if (!href || seen.has(href)) continue;
            seen.add(href);
            out.push({ l0: l0name, l1: text || '(unnamed)', href: href });
        }
    }
    return out;
}
"""


def _canon_url(href):
    """호스트/쿼리/프래그먼트/끝슬래시 제거 + 소문자 -> PF 식별용 canonical path."""
    if not href:
        return None
    href = href.split("#")[0].split("?")[0]
    m = re.search(r"https?://[^/]+(/.*)$", href)
    path = m.group(1) if m else href
    if href.startswith("http") and not m:  # 도메인만 있고 path 없음
        return None
    return "/" + path.strip("/").lower()


def _looks_like_pf(canon):
    """PF(제품 파인더) 페이지일 법한 URL 만 통과. 개별 상품/구매플로우/외부/너무 깊은 경로 제외."""
    if not canon or "-sku-" in canon:
        return False
    segs = [s for s in canon.strip("/").split("/") if s]
    if not segs or segs[0] != SITE or not (2 <= len(segs) <= 4):
        return False
    if segs[-1] in ("buy", "buy-now"):  # 구매 플로우 페이지
        return False
    if len(segs) >= 3 and segs[-1] == segs[-2]:  # /us/xr/galaxy-xr/galaxy-xr = 단일 상품
        return False
    return True


def discover_all_categories(page):
    """GNB 의 모든 L0 메뉴에서 L1 링크를 모아 canonical URL 로 dedup.

    반환: [{name, href, canon, sources:[{l0,l1}, ...]}]  (sources = 이 PF 로 이어진 모든 메뉴 경로)
    """
    raw = page.evaluate(_DISCOVER_ALL_JS)
    groups = {}
    for r in raw:
        if MENUS and r["l0"] not in MENUS:
            continue
        canon = _canon_url(r["href"])
        if not _looks_like_pf(canon):
            continue
        g = groups.setdefault(
            canon, {"name": r["l1"], "href": r["href"], "canon": canon, "sources": []}
        )
        src = {"l0": r["l0"], "l1": r["l1"]}
        if src not in g["sources"]:
            g["sources"].append(src)
    cats = list(groups.values())
    if ONLY_CATEGORIES:
        cats = [
            c
            for c in cats
            if c["name"] in ONLY_CATEGORIES
            or any(s["l1"] in ONLY_CATEGORIES for s in c["sources"])
        ]
    return cats


class Progress:
    """PF/카드 단위 진행 상황 로거. 터미널이면 \\r 갱신, 리다이렉트면 줄단위."""

    def __init__(self, total_pf, stream=None):
        self.total = total_pf
        self.done = 0
        self.stream = stream or sys.stderr
        self.tty = bool(getattr(self.stream, "isatty", lambda: False)())
        self.t0 = time.time()
        self.pf_times = []
        self.cur = {}

    def _clock(self):
        return time.strftime("%H:%M:%S")

    def _eta(self):
        if not self.pf_times:
            return ""
        avg = sum(self.pf_times) / len(self.pf_times)
        rem = (self.total - self.done) * avg
        return f"avg {avg / 60:.1f}m/PF ETA ~{rem / 60:.0f}m"

    def _emit(self, msg, transient=False):
        if self.tty:
            self.stream.write("\r\033[K" + msg + ("" if transient else "\n"))
        elif not transient:
            self.stream.write(msg + "\n")
        self.stream.flush()

    def start_pf(self, idx, cat):
        self.cur = {"idx": idx, "name": cat["canon"], "t": time.time(), "cards": 0}
        src = "; ".join(f'{s["l0"]}>{s["l1"]}' for s in cat.get("sources", []))
        self._emit(f"[{self._clock()}] PF {idx}/{self.total}  {cat['canon']}  (from: {src})")

    def set_cards(self, n):
        self.cur["cards"] = n

    def card(self, i, sort, recs):
        c = self.cur.get("cards", 0)
        msg = (
            f"    PF {self.cur.get('idx')}/{self.total}  card {i}/{c}  "
            f"sort={sort}  recs={recs}  {self._eta()}"
        )
        self._emit(msg, transient=self.tty and not (i == c))

    def end_pf(self, status, nrecs):
        dt = time.time() - self.cur.get("t", time.time())
        self.pf_times.append(dt)
        self.done += 1
        self._emit(
            f"[{self._clock()}] done PF {self.cur.get('idx')}/{self.total}  "
            f"{self.cur.get('name')}  {status}  {nrecs} recs  {dt / 60:.1f}m  {self._eta()}"
        )

    def snapshot(self, n_records):
        return {
            "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "pf_total": self.total,
            "pf_done": self.done,
            "current_pf": self.cur.get("name"),
            "elapsed_min": round((time.time() - self.t0) / 60, 1),
            "eta": self._eta(),
            "records_so_far": n_records,
        }


def _ckpt_path(cat):
    slug = re.sub(r"[^a-z0-9]+", "_", cat["canon"]).strip("_") or "root"
    return os.path.join(RESUME_DIR, f"{slug}.json")


def navigate_to_category(page, cat):
    """해당 PF URL 로 직접 이동 (여러 L0 메뉴에 걸친 PF 를 순회하므로 goto 가 안정적)."""
    href = cat.get("href") or cat.get("canon") or ""
    url = href if href.startswith("http") else SITE_ROOT + href
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    dismiss_consent(page)


def _trigger_lazy_load(page):
    """제품 파인더는 화면에 들어와야 카드를 렌더한다(IntersectionObserver).
    파인더 영역으로 스크롤한 뒤, 안 되면 페이지 전체를 훑어 내린다."""
    try:
        finder = page.locator(".js-pfv2-finder, .pd21-product-finder").first
        if finder.count():
            finder.scroll_into_view_if_needed(timeout=4000)
            page.wait_for_timeout(1500)
    except Exception:  # noqa: BLE001
        pass
    if page.locator(CARD_SELECTOR).count() > 0:
        return
    for _ in range(12):
        page.mouse.wheel(0, 1400)
        page.wait_for_timeout(800)
        if page.locator(CARD_SELECTOR).count() > 0:
            break
    page.wait_for_timeout(1500)


def wait_for_pf(page, timeout_ms=15000):
    """제품 파인더 그리드(활성 카드)가 나타나면 True."""
    try:
        page.wait_for_selector(CARD_SELECTOR, timeout=timeout_ms)
    except PWTimeout:
        pass
    if page.locator(CARD_SELECTOR).count() == 0:
        _trigger_lazy_load(page)
    # 렌더가 느린 파인더 대비 최대 ~30초 폴링
    for _ in range(15):
        if page.locator(CARD_SELECTOR).count() > 0:
            page.wait_for_timeout(1200)
            return True
        page.wait_for_timeout(2000)
    return page.locator(CARD_SELECTOR).count() > 0


def _pf_result_count(page):
    """PF 상단 'N Results' 숫자. 못 읽으면 None."""
    el = first_or_none(page, ".pd21-top__result-count")
    if not el:
        return None
    n = _to_number(el.inner_text())
    return int(n) if n is not None and n > 0 else None


def load_all_cards(page, max_iter=80, settle=3):
    """무한 스크롤 PF: 활성 카드 수가 더 이상 안 늘거나(연속 settle회) result-count 에
    도달할 때까지 페이지 끝으로 스크롤해 카드를 모두 로드한다.
    MAX_CARDS 가 걸려 있으면 그만큼만 채우고 멈춘다.
    반환: 최종 활성 카드 수.
    """
    target = _pf_result_count(page)
    cap = MAX_CARDS or target or 100000

    prev, stable = -1, 0
    for _ in range(max_iter):
        n = page.locator(CARD_SELECTOR).count()
        if n >= cap:
            break
        if n == prev:
            stable += 1
            if stable >= settle:
                break
        else:
            stable = 0
        prev = n
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except Exception:  # noqa: BLE001
            page.mouse.wheel(0, 6000)
        page.wait_for_timeout(1100)
        page.mouse.wheel(0, -400)  # 살짝 위로 튕겨 IntersectionObserver 재트리거
        page.wait_for_timeout(250)

    n = page.locator(CARD_SELECTOR).count()
    if target and n < target and not MAX_CARDS:
        print(
            f"[warn] load_all_cards: {n}/{target} 만 로드됨 ({page.url})",
            file=sys.stderr,
        )
    return n


# --------------------------------------------------------------------------- #
# 진입점
# --------------------------------------------------------------------------- #
def scan_category(page, cat, progress=None):
    """한 PF 에서 두 정렬 모두 전체 추출. 그리드가 없으면 skip 마커 1건 반환."""
    global _QV_AUDIT_LEFT
    _QV_AUDIT_LEFT = QV_AUDIT_N  # PF 마다 Quick View 교차검증 카운터 리셋
    navigate_to_category(page, cat)
    canon = cat.get("canon") or _canon_url(cat.get("href"))
    src_menus = [f'{s["l0"]}>{s["l1"]}' for s in cat.get("sources", [])]
    if not wait_for_pf(page):
        return [
            {
                "category": cat["name"],
                "category_url": cat.get("href"),
                "source_pf_url": canon,
                "source_menus": src_menus,
                "status": "skipped: no product-finder grid",
            }
        ]

    out = []
    done_sorts = set()
    for sort_name, sort_code in SORT_SEQUENCE:
        try:
            applied = set_sort(page, sort_name, sort_code)
        except PWTimeout:
            applied = None
        if not applied:  # 이 PF/사이트에 해당 정렬이 없음
            continue
        if applied in done_sorts:
            continue
        done_sorts.add(applied)
        for rec in extract_all(page, applied, progress=progress):
            rec["category"] = cat["name"]
            rec["category_url"] = cat.get("href")
            rec["source_pf_url"] = canon
            rec["source_menus"] = src_menus
            out.append(rec)
    return out


def _dedup_compare_keys():
    return (
        "model_name", "display_name", "display_category_major",
        "display_category_middle", "product_color", "capacity", "standard_price",
        "final_price", "currency", "on_sale", "stock_level_status", "badge",
        "family_id", "product_url", "cta_pd_url", "image_url", "review_count",
        "review_rating_score", "is_default",
    )


def dedupe_records(records):
    """(sku, sort_type) 기준 제품 레벨 dedup.

    값이 같으면 하나로 합치고(also_seen_on 기록), 다르면 유지 + ambiguous 표시.
    sorting_no 는 PF 마다 다른 게 정상이므로 sorting_no_by_source 로 보존.
    반환: (deduped_records, ambiguities)
    """
    groups, passthrough = {}, []
    for r in records:
        if r.get("status") or not r.get("sku"):
            passthrough.append(r)
            continue
        groups.setdefault((r["sku"], r.get("sort_type")), []).append(r)

    out = list(passthrough)
    ambiguities = []
    for (sku, sort_type), rs in groups.items():
        if len(rs) == 1:
            out.append(rs[0])
            continue
        base = dict(rs[0])
        diffs = {}
        for r in rs[1:]:
            for k in _dedup_compare_keys():
                if r.get(k) != base.get(k):
                    diffs.setdefault(k, set()).update(
                        [base.get(k), r.get(k)]
                    )
        base["seen_count"] = len(rs)
        base["also_seen_on"] = sorted({r.get("source_pf_url") for r in rs if r.get("source_pf_url")})
        base["sorting_no_by_source"] = {
            r.get("source_pf_url"): r.get("sorting_no") for r in rs
        }
        if diffs:
            base["ambiguous_fields"] = sorted(diffs)
            ambiguities.append(
                {
                    "sku": sku,
                    "sort_type": sort_type,
                    "sources": base["also_seen_on"],
                    "fields": {k: sorted(map(str, v)) for k, v in diffs.items()},
                }
            )
        out.append(base)
    return out, ambiguities


def verify_counts(records):
    """PF(canonical URL) x sort_type 별 고유 SKU 수를 EXPECTED_COUNTS 와 대조.

      Recommended : actual == expected            -> pass
      Newest      : expected <= actual
                    <= expected + NEWEST_COUNT_TOLERANCE  -> pass
                    (추출 시점 이후 신제품 추가분 허용)
    부분 스캔(MAX_CARDS 등) 시엔 판정 없이 counts 만 보고한다.
    """
    by_pf = {}   # canon -> sort_type -> set(sku)
    pf_name = {}
    for r in records:
        canon = r.get("source_pf_url")
        if not canon:
            continue
        pf_name.setdefault(canon, r.get("category"))
        if r.get("status") or not r.get("sku"):
            continue
        by_pf.setdefault(canon, {}).setdefault(
            r.get("sort_type"), set()
        ).add(r["sku"])

    out = []
    for canon in sorted(by_pf):
        expected = EXPECTED_COUNTS.get(canon)
        counts = {st: len(s) for st, s in sorted(by_pf[canon].items())}
        entry = {
            "pf_url": canon,
            "category": pf_name.get(canon),
            "expected": expected,
            "counts": counts,
        }
        if PARTIAL_SCAN:
            entry["result"] = "skipped: partial scan"
        elif expected is None:
            entry["result"] = "skipped: no expected count"
        else:
            checks, overall = {}, "pass"
            for st, skus in sorted(by_pf[canon].items()):
                actual = len(skus)
                if (st or "").lower() == "newest":
                    lo, hi = expected, expected + NEWEST_COUNT_TOLERANCE
                    ok = lo <= actual <= hi
                    checks[st] = {
                        "actual": actual,
                        "expected": expected,
                        "allowed_range": [lo, hi],
                        "pass": ok,
                    }
                else:
                    ok = actual == expected
                    checks[st] = {
                        "actual": actual,
                        "expected": expected,
                        "pass": ok,
                    }
                overall = overall if ok else "fail"
            entry["checks"] = checks
            entry["result"] = overall
        out.append(entry)

    # 기대치는 있는데 이번 스캔에 안 잡힌 PF 도 실패로 보고
    for canon, expected in EXPECTED_COUNTS.items():
        if canon not in by_pf:
            out.append(
                {
                    "pf_url": canon,
                    "category": None,
                    "expected": expected,
                    "counts": {},
                    "result": "fail: PF not scanned",
                }
            )
    return out


def run_scan(progress_file=None):
    """GNB 의 모든 L0 메뉴(MENUS=None) 또는 지정 메뉴의 PF 페이지를 canonical URL 로
    dedup 해 순회 스크랩. RESUME_DIR 지정 시 PF 단위 체크포인트 저장/재사용.
    """
    log = lambda m: print(m, file=sys.stderr)  # noqa: E731
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 900}, user_agent=USER_AGENT
        )
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        dismiss_consent(page)

        cats = discover_all_categories(page)
        log(
            f"[info] menus={'ALL' if not MENUS else ','.join(MENUS)}  "
            f"unique PF pages={len(cats)}  "
            f"(dup menu-paths collapsed: "
            f"{sum(len(c['sources']) for c in cats) - len(cats)})"
        )
        prog = Progress(len(cats))

        for i, cat in enumerate(cats, 1):
            ckpt = _ckpt_path(cat) if RESUME_DIR else None
            if ckpt and os.path.exists(ckpt):
                try:
                    recs = json.load(open(ckpt, encoding="utf-8"))
                    results.extend(recs)
                    prog.done += 1
                    log(f"[resume] PF {i}/{len(cats)} {cat['canon']} <- checkpoint ({len(recs)})")
                    continue
                except Exception:  # noqa: BLE001 - 손상된 체크포인트는 다시 스크랩
                    pass

            prog.start_pf(i, cat)
            try:
                recs = scan_category(page, cat, progress=prog)
                status = "ok" if any(not x.get("status") for x in recs) else "skip"
            except Exception as e:  # noqa: BLE001 - 한 PF 실패해도 계속
                recs = [
                    {
                        "category": cat["name"],
                        "category_url": cat.get("href"),
                        "source_pf_url": cat["canon"],
                        "status": f"error: {type(e).__name__}: {e}",
                    }
                ]
                status = "error"

            if ckpt:
                os.makedirs(RESUME_DIR, exist_ok=True)
                with open(ckpt, "w", encoding="utf-8") as f:
                    json.dump(recs, f, ensure_ascii=False, indent=2)
            results.extend(recs)
            prog.end_pf(status, len(recs))
            if progress_file:
                try:
                    with open(progress_file, "w", encoding="utf-8") as f:
                        json.dump(prog.snapshot(len(results)), f, ensure_ascii=False, indent=2)
                except Exception:  # noqa: BLE001
                    pass

        browser.close()
    return results


def main():
    records = run_scan()
    verification = verify_counts(records)
    for v in verification:
        print(
            f"[verify] {v['pf_url']}  expected={v.get('expected')}  "
            f"counts={v.get('counts')}  -> {v['result']}",
            file=sys.stderr,
        )
    out = {"records": records, "count_verification": verification}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


if __name__ == "__main__":
    main()
