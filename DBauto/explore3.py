from playwright.sync_api import sync_playwright
import json

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width":1440,"height":900})
    page.goto("https://www.samsung.com/us/", timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    # accept cookie consent
    try:
        btn = page.locator("#truste-consent-button")
        if btn.count() > 0:
            btn.click(timeout=5000)
            print("clicked consent")
    except Exception as e:
        print("consent err", e)
    page.wait_for_timeout(1000)

    mobile = page.locator("a.nv00-gnb-v4__l0-menu-link", has_text="Mobile").first
    mobile.hover()
    page.wait_for_timeout(1000)
    items = page.eval_on_selector_all("a[class*='l2-menu'], a[class*='l1-menu-link']", "els => els.map(e => ({text: e.innerText.trim(), href: e.href, cls: e.className}))")
    print(json.dumps(items, ensure_ascii=False, indent=2))
    browser.close()
