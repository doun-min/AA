import json
import re

from playwright.sync_api import sync_playwright

BASE_URL = "https://www.samsung.com/us/"


def parse_price_save(text: str):
    if not text:
        return None
    m = re.match(r"\s*([^\d]+)\s*([\d,]+\.?\d*)", text)
    if not m:
        return {"currency": None, "price": None}
    currency, price = m.group(1).strip(), m.group(2).replace(",", "")
    return {"currency": currency, "price": float(price)}


def first_or_none(card, selector):
    loc = card.locator(selector).first
    return loc if loc.count() > 0 else None


def extract_card(card):
    product_id = card.get_attribute("data-productidx")

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

    price_save_el = first_or_none(
        card,
        "div.price-ux__wrap.price-ux__wrap--ux-v2 "
        "p.price-ux__price-save span.price-ux__price-save-was",
    )
    price_save_text = price_save_el.inner_text().strip() if price_save_el else None

    color_el = first_or_none(
        card,
        "div.option-selector-v2.option-selector-v2__color-text "
        "div.option-selector-v2__color-name > span",
    )
    color_name = color_el.inner_text().strip() if color_el else None

    return {
        "product_id": product_id,
        "badge": badge_text,
        "image_url": image_url,
        "name": name_text,
        "price_save": parse_price_save(price_save_text),
        "color_name": color_name,
    }


def main():
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)

        # 쿠키 동의 배너가 상단 메뉴 hover를 가로채는 것을 방지
        page.evaluate("document.getElementById('consent_blackbar')?.remove()")

        page.locator("a.nv00-gnb-v4__l0-menu-link", has_text="Mobile").first.hover()
        page.wait_for_timeout(800)
        page.locator(
            "a.nv00-gnb-v4__l1-menu-link", has_text="Galaxy Smartphones"
        ).first.click()

        page.wait_for_selector(
            ".js-pfv2-product-card.pd21-product-card__item--active", timeout=30000
        )
        page.wait_for_timeout(1500)

        cards = page.locator(
            ".js-pfv2-product-card.pd21-product-card__item--active"
        )
        for i in range(cards.count()):
            results.append(extract_card(cards.nth(i)))

        browser.close()

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return results


if __name__ == "__main__":
    main()
