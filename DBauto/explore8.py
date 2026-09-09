from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width":1440,"height":900})
    page.goto("https://www.samsung.com/us/", timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    html = page.eval_on_selector("#consent_blackbar", "e => e.outerHTML")
    idx = html.rfind("truste-button1")
    print(html[max(0,idx-200):idx+400])
    print("=====")
    idx2 = html.find("</style>")
    print(len(html))
    print(html[idx2:idx2+2000])
    browser.close()
