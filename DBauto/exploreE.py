from playwright.sync_api import sync_playwright
import json

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width":1440,"height":900})
    page.goto("https://www.samsung.com/us/", timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    page.evaluate("document.getElementById('consent_blackbar')?.remove()")
    page.wait_for_timeout(300)

    mobile = page.locator("a.nv00-gnb-v4__l0-menu-link", has_text="Mobile").first
    mobile.hover()
    page.wait_for_timeout(800)
    link = page.locator("a.nv00-gnb-v4__l1-menu-link", has_text="Galaxy Smartphones").first
    link.click()
    page.wait_for_load_state("domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    print("URL:", page.url)

    count_active = page.locator("div.pd21-product-card__item--active").count()
    count_card = page.locator(".js-pfv2-product-card").count()
    print("active count:", count_active, "card count:", count_card)

    # dump class list of first few product-card-like elements
    classes = page.eval_on_selector_all("[class*='pd21-product-card']", "els => [...new Set(els.map(e=>e.className))]")
    print(json.dumps(classes[:40], ensure_ascii=False, indent=2))
    browser.close()
