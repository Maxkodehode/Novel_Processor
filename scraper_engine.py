import os
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from adapters import get_adapter

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def scrape(
    url: str, use_local: str | None = None, save_html: str | None = None
) -> dict:
    adapter = get_adapter(url)
    print(f"[*] Using adapter: {type(adapter).__name__}")

    if use_local and os.path.exists(use_local):
        with open(use_local, "r", encoding="utf-8") as f:
            html = f.read()
        soup = BeautifulSoup(html, "html.parser")
        return adapter.parse(soup, url)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=USER_AGENT)
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)

        # In-place wait for content
        try:
            page.wait_for_selector(
                "li.toc_w, div.fiction-stats, div#profile_top", timeout=15_000
            )
        except:
            pass

        html = page.content()
        if save_html:
            with open(save_html, "w", encoding="utf-8") as f:
                f.write(html)

        soup = BeautifulSoup(html, "html.parser")

        # Link the live page for adapters like ScribbleHub that need it
        if hasattr(adapter, "_pw_page"):
            adapter._pw_page = page

        result = adapter.parse(soup, url)
        browser.close()
        return result
