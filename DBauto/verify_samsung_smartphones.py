import json
import os
import re

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.samsung.com/us/"
CARD_SELECTOR = ".js-pfv2-product-card.pd21-product-card__item--active"

# Recommended 로 한 번, Newest 로 한 번 전체 수집한다.
SORT_SEQUENCE = ["Recommended", "Newest"]

# 디버깅/부분 실행용 (환경변수로 조절). 0 또는 미설정이면 전체.
MAX_CARDS = int(os.environ.get("SAMSUNG_MAX_CARDS", "0")) or None

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
    try:
        btn.scroll_into_view_if_needed(timeout=3000)
        btn.click(timeout=5000)
    except PWTimeout:
        try:
            btn.click(force=True)
        except PWTimeout:
            return False
    page.wait_for_timeout(700)
    return True


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


def _open_quick_view_once(page, card, prev_sku):
    btn = card.locator("button.pd21-product-card__quickview_btn").first
    if btn.count() == 0:
        return None
    try:
        btn.scroll_into_view_if_needed(timeout=3000)
        btn.click(timeout=5000)
    except PWTimeout:
        btn.click(force=True)

    sku_loc = page.locator("p.pd21-quick-view__sku:visible").first
    try:
        page.wait_for_function(
            """(prev) => {
                const els = document.querySelectorAll('p.pd21-quick-view__sku');
                for (const el of els) {
                    if (el.offsetParent === null) continue;
                    const t = (el.textContent || '').trim();
                    if (t.length > 0 && t !== prev) return true;
                }
                return false;
            }""",
            arg=prev_sku or "",
            timeout=10000,
        )
    except PWTimeout:
        pass

    if sku_loc.count():
        return (sku_loc.inner_text().strip() or None)
    any_loc = page.locator("p.pd21-quick-view__sku").first
    return (any_loc.inner_text().strip() or None) if any_loc.count() else None


def read_quick_view_sku(page, card, prev_sku):
    """Quick view 슬라이드를 열어 p.pd21-quick-view__sku 값을 읽고 다시 닫는다.

    콜드 상태의 첫 조합에서 패널 렌더가 늦어 빈 값이 나오는 경우가 있어 한 번 재시도한다.
    """
    sku = None
    for attempt in range(2):
        sku = _open_quick_view_once(page, card, prev_sku)
        _close_quick_view(page)
        if sku and SKU_RE.match(sku) and sku != prev_sku:
            break
        page.wait_for_timeout(600)
    return sku


def extract_card_variants(page, card, base, sort_type, state):
    """카드의 모든 색상 x 용량 조합을 순회하며 SKU 를 수집."""
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
                sku = read_quick_view_sku(page, card, state.get("prev_sku"))
                rec["sku"] = sku
                if sku and SKU_RE.match(sku):
                    state["prev_sku"] = sku
            except Exception as e:  # noqa: BLE001 - 조합 하나 실패해도 계속 진행
                rec["error"] = f"{type(e).__name__}: {e}"

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

    state = {"prev_sku": None}
    results = []
    for i in range(total):
        card = cards.nth(i)
        try:
            card.scroll_into_view_if_needed(timeout=3000)
        except PWTimeout:
            pass
        base = extract_card_base(card)
        results.extend(extract_card_variants(page, card, base, sort_type, state))
    return results


# --------------------------------------------------------------------------- #
# 진입점
# --------------------------------------------------------------------------- #
def main():
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)

        # 쿠키 동의 배너가 상단 메뉴 hover / 클릭을 가로채는 것을 방지
        dismiss_consent(page)

        page.locator("a.nv00-gnb-v4__l0-menu-link", has_text="Mobile").first.hover()
        page.wait_for_timeout(800)
        page.locator(
            "a.nv00-gnb-v4__l1-menu-link", has_text="Galaxy Smartphones"
        ).first.click()

        page.wait_for_selector(CARD_SELECTOR, timeout=30000)
        page.wait_for_timeout(1500)
        dismiss_consent(page)

        for sort_name in SORT_SEQUENCE:
            applied = set_sort(page, sort_name)
            sort_type = (applied or sort_name).strip()
            results.extend(extract_all(page, sort_type))

        browser.close()

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return results


if __name__ == "__main__":
    main()
