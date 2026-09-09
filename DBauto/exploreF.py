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

    cards = page.locator(".js-pfv2-product-card.pd21-product-card__item--active")
    print("card count:", cards.count())
    first = cards.first
    print("data-productid:", first.get_attribute("data-productid"))
    html = first.inner_html()
    print(len(html))
    # save to file for inspection
    with open("/root/work/AA/DBauto/card_sample.html","w") as f:
        f.write(html)
    browser.close()
