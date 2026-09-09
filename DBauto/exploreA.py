from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width":1440,"height":900})
    page.goto("https://www.samsung.com/us/", timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    html = page.eval_on_selector("#consent_blackbar", "e => e.outerHTML")
    idx = html.find('id="truste-consent-button"')
    print("id-based:", idx)
    # print any element with onclick containing accept
    idx2 = html.lower().find("accept")
    print(html[max(0,idx2-300):idx2+100])
    browser.close()
