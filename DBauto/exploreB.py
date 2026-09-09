from playwright.sync_api import sync_playwright
import json

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width":1440,"height":900})
    page.goto("https://www.samsung.com/us/", timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    page.click("button#truste-consent-button", force=True, timeout=5000)
    page.wait_for_timeout(1000)

    mobile = page.locator("a.nv00-gnb-v4__l0-menu-link", has_text="Mobile").first
    mobile.hover()
    page.wait_for_timeout(1000)
    items = page.eval_on_selector_all("a[href*='smartphone']", "els => els.map(e => ({text: e.innerText.trim(), href: e.href, cls: e.className}))")
    print(json.dumps(items, ensure_ascii=False, indent=2))
    browser.close()
