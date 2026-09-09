from playwright.sync_api import sync_playwright
import json

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width":1440,"height":900})
    page.goto("https://www.samsung.com/us/", timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    buttons = page.eval_on_selector_all("#consent_blackbar button, #consent_blackbar a", "els => els.map(e => ({text: e.innerText.trim(), id: e.id, cls: e.className}))")
    print(json.dumps(buttons, ensure_ascii=False, indent=2))
    browser.close()
