from playwright.sync_api import sync_playwright
import json

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width":1440,"height":900})
    page.goto("https://www.samsung.com/us/", timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    # dump top nav menu items
    items = page.eval_on_selector_all("nav a, header a", "els => els.map(e => ({text: e.innerText.trim(), href: e.href, cls: e.className})).filter(x => x.text)")
    print(json.dumps(items[:80], ensure_ascii=False, indent=2))
    browser.close()
