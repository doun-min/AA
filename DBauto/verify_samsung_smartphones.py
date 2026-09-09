import json
import os
import re
import sys

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

SITE_ROOT = "https://www.samsung.com"
BASE_URL = SITE_ROOT + "/us/"
CARD_SELECTOR = ".js-pfv2-product-card.pd21-product-card__item--active"

# 스캔할 상단(L0) 메뉴. 이 메뉴의 하위(L1) 제품 카테고리를 모두 순회한다.
CATEGORY_MENU = os.environ.get("SAMSUNG_MENU", "Mobile")

# Recommended 로 한 번, Newest 로 한 번 전체 수집한다.
SORT_SEQUENCE = ["Recommended", "Newest"]

# 디버깅/부분 실행용 (환경변수로 조절). 0 또는 미설정이면 전체.
MAX_CARDS = int(os.environ.get("SAMSUNG_MAX_CARDS", "0")) or None
# 카드당 색상 x 용량 조합 수 상한 (테스트용). 0/미설정이면 전체 조합.
MAX_COMBOS = int(os.environ.get("SAMSUNG_MAX_COMBOS", "0")) or None

# 특정 카테고리만 돌리고 싶을 때: SAMSUNG_CATEGORIES="Galaxy Watch,Galaxy Tab"
ONLY_CATEGORIES = [
    c.strip() for c in os.environ.get("SAMSUNG_CATEGORIES", "").split(",") if c.strip()
]

SKU_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-/]{4,}$")


def parse_price_save(text: str):
    if not text:
        return None
    m = re.match(r"\s*([^\d]+)\s*([\d,]+\.?\d*)", text)
    if not m:
        return {"currency": None, "price": None}
    currency, price = m.group(1).strip(), m.group(2).replace(",", "")
    return {"currency": currency, "price": float(price)}


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
    """현재 선택된 정렬 이름 (예: 'Recommended')."""
    el = first_or_none(page, "span.pd21-sort__opener-name")
    return el.inner_text().strip() if el else None


def set_sort(page, sort_name: str):
    """정렬 드롭다운을 열어 sort_name 옵션을 선택하고 그리드가 다시 그려질 때까지 대기."""
    current = read_current_sort(page)
    if current and current.strip().lower() == sort_name.lower():
        return current

    dismiss_consent(page)
    opener = page.locator("button.pd21-sort__opener").first
    opener.scroll_into_view_if_needed()
    opener.click()
    page.wait_for_timeout(500)

    code = sort_name.lower().replace(" ", "")
    option = page.locator(
        "label.pd21-sort__select-option-label"
        f"[data-sort-code='{code}'], "
        "label.pd21-sort__select-option-label"
        f"[data-sort-name='{sort_name}']"
    ).first
    if option.count() == 0:
        # 이 카테고리에는 해당 정렬 옵션이 없음
        page.keyboard.press("Escape")
        return current
    try:
        option.click(timeout=5000)
    except PWTimeout:
        # 라디오 input 이 시각적으로 숨겨져 있어 label 클릭이 막히면 강제 클릭
        option.click(force=True)

    # 모바일 레이아웃은 Apply 버튼을 눌러야 반영됨 (데스크톱은 즉시 반영)
    apply_btn = page.locator("button.pd21-sort__apply-cta-mob")
    if apply_btn.count() and apply_btn.first.is_visible():
        apply_btn.first.click()

    # 그리드 재렌더 대기
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PWTimeout:
        pass
    page.wait_for_timeout(1500)
    page.wait_for_selector(CARD_SELECTOR, timeout=30000)
    page.wait_for_timeout(1000)
    return read_current_sort(page)


# --------------------------------------------------------------------------- #
# 카드 단위 추출
# --------------------------------------------------------------------------- #
def extract_card_base(card):
    """색상/용량과 무관한 카드 공통 정보."""
    product_id = card.get_attribute("data-productidx")
    if product_id is None:
        cb = first_or_none(card, "input.pd21-product-card__compare-checkbox")
        product_id = cb.get_attribute("data-productidx") if cb else None

    badge_el = first_or_none(
        card, "span.badge-icon.badge-icon--label-v2.badge-icon--bg-color-blue"
    )
    badge_text = badge_el.inner_text().strip() if badge_el else None

    img_el = first_or_none(card, "div.pd21-product-card__image img")
    image_url = (
        (img_el.get_attribute("src") or img_el.get_attribute("data-desktop-src"))
        if img_el
        else None
    )

    name_el = first_or_none(card, "div.pd21-product-card__name-wrap")
    name_text = name_el.inner_text().strip() if name_el else None

    return {
        "product_id": product_id,
        "badge": badge_text,
        "image_url": image_url,
        "name": name_text,
    }


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
        return cb.get_attribute("data-model-code") or cb.get_attribute("data-modelcode")
    link = first_or_none(card, "a.pd21-product-card__name")
    return link.get_attribute("data-modelcode") if link else None


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


def extract_card_variants(page, card, base, sort_type):
    """카드의 모든 색상 x 용량(또는 사이즈) 조합을 순회하며 SKU 를 수집."""
    records = []
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

            rec = dict(base)
            rec.update(
                {
                    "sort_type": sort_type,
                    "color_name": color_name,
                    "capacity": capacity,
                    "price_save": read_price_save(card),
                    "modelcode": read_card_modelcode(card),
                    "sku": None,
                }
            )
            try:
                rec["sku"] = read_quick_view_sku(page, card)
            except Exception as e:  # noqa: BLE001 - 조합 하나 실패해도 계속 진행
                rec["error"] = f"{type(e).__name__}: {e}"
                _close_quick_view(page)

            records.append(rec)
    return records


def extract_all(page, sort_type):
    """현재 정렬 상태에서 활성 카드 전체를 순회."""
    page.wait_for_selector(CARD_SELECTOR, timeout=30000)
    page.wait_for_timeout(1200)

    cards = page.locator(CARD_SELECTOR)
    total = cards.count()
    if MAX_CARDS:
        total = min(total, MAX_CARDS)

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
                extract_card_variants(page, card, base, sort_type)
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
        out.push({ name: text.replace(/\s*NEW$/i, '').trim(), href: href });
    }
    return out;
}
"""


def discover_categories(page):
    """CATEGORY_MENU 플라이아웃을 열어 [{name, href}, ...] 를 반환."""
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


def navigate_to_category(page, cat):
    """Mobile 메뉴에 다시 hover 해서 해당 카테고리 링크를 클릭. 실패하면 URL 직접 이동."""
    href = cat["href"]
    clicked = False
    try:
        page.locator(
            "a.nv00-gnb-v4__l0-menu-link", has_text=CATEGORY_MENU
        ).first.hover()
        page.wait_for_timeout(900)
        link = page.locator(
            f".nv00-gnb-v4__l0-menu--show a.nv00-gnb-v4__l1-menu-link[href='{href}']"
        ).first
        if link.count():
            link.click(timeout=8000)
            clicked = True
    except Exception:  # noqa: BLE001
        clicked = False
    if not clicked:
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


# --------------------------------------------------------------------------- #
# 진입점
# --------------------------------------------------------------------------- #
def scan_category(page, cat):
    """한 카테고리에서 두 정렬 모두 전체 추출. 그리드가 없으면 skip 마커 1건 반환."""
    navigate_to_category(page, cat)
    if not wait_for_pf(page):
        return [
            {
                "category": cat["name"],
                "category_url": cat["href"],
                "status": "skipped: no product-finder grid",
            }
        ]

    out = []
    done_sorts = set()
    for sort_name in SORT_SEQUENCE:
        try:
            applied = set_sort(page, sort_name)
        except PWTimeout:
            applied = sort_name
        sort_type = (applied or sort_name).strip()
        # 이 카테고리에 해당 정렬이 없어 이전 패스와 같은 결과가 되면 건너뛴다.
        if sort_type.lower() in done_sorts:
            print(
                f"[info]   '{sort_name}' unavailable here -> skip duplicate pass",
                file=sys.stderr,
            )
            continue
        done_sorts.add(sort_type.lower())
        for rec in extract_all(page, sort_type):
            rec["category"] = cat["name"]
            rec["category_url"] = cat["href"]
            out.append(rec)
    return out


def main():
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            ),
        )
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        dismiss_consent(page)

        categories = discover_categories(page)
        print(
            f"[info] {CATEGORY_MENU}: {len(categories)} categories -> "
            + ", ".join(c["name"] for c in categories),
            file=sys.stderr,
        )

        for cat in categories:
            print(f"[info] scanning: {cat['name']} ({cat['href']})", file=sys.stderr)
            try:
                results.extend(scan_category(page, cat))
            except Exception as e:  # noqa: BLE001 - 한 카테고리 실패해도 계속
                results.append(
                    {
                        "category": cat["name"],
                        "category_url": cat["href"],
                        "status": f"error: {type(e).__name__}: {e}",
                    }
                )

        browser.close()

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return results


if __name__ == "__main__":
    main()
