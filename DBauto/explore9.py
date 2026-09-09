from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width":1440,"height":900})
    page.goto("https://www.samsung.com/us/", timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    html = page.eval_on_selector("#consent_blackbar", "e => e.outerHTML")
    print(len(html))
    idx = html.find("truste-button1")
    print(html[max(0,idx-200):idx+400] if idx>=0 else "not found")
    browser.close()
