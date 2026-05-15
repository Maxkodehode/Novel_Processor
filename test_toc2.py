"""
Test: navigate to ?toc=2 and wait longer, check if JS pagination loads chapters.
Also check what the pagination JS actually does.
"""

import sys
import time
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

try:
    from playwright_stealth import stealth_sync
    _STEALTH = True
except ImportError:
    _STEALTH = False

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.scribblehub.com/series/1857436/the-rusting-robots-and-revenge/"
    base_url = url.rstrip("/")
    print(f"URL: {base_url}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
        )
        page = context.new_page()
        if _STEALTH:
            stealth_sync(page)

        # Track ALL network requests
        requests_log = []
        responses_log = []

        def on_req(req):
            if "admin-ajax" in req.url or "toc" in req.url.lower() or "chapter" in req.url.lower():
                requests_log.append(f"{req.method} {req.url[:150]}")

        def on_resp(resp):
            if "admin-ajax" in resp.url or "toc" in resp.url.lower():
                try:
                    body = resp.text()[:200]
                except:
                    body = "(error reading body)"
                responses_log.append(f"{resp.status} {resp.url[:150]} body={body}")

        page.on("request", on_req)
        page.on("response", on_resp)

        # Load base page first
        print("[1] Loading base page...")
        page.goto(base_url, wait_until="load", timeout=60000)
        time.sleep(3)
        count = page.evaluate("document.querySelectorAll('li.toc_w').length")
        print(f"  Chapters: {count}")

        # Now navigate to ?toc=2
        print(f"\n[2] Navigating to ?toc=2...")
        page.goto(f"{base_url}/?toc=2", wait_until="load", timeout=60000)
        time.sleep(5)  # Wait longer

        toc_count = page.evaluate("document.querySelectorAll('li.toc_w').length")
        print(f"  Chapters after 5s: {toc_count}")

        # Wait even longer
        time.sleep(10)
        toc_count = page.evaluate("document.querySelectorAll('li.toc_w').length")
        print(f"  Chapters after 15s total: {toc_count}")

        # Check what the pagination JS is doing
        print(f"\n[3] Checking pagination JS state...")

        # Check if simplePagination is initialized
        pag_state = page.evaluate("""JSON.stringify({
            simplePagination: typeof $.fn.simplePagination !== 'undefined',
            toc_ol: document.querySelector('.toc_ol')?.innerHTML?.slice(0, 200),
            pagination_element: document.querySelector('#pagination-mesh-toc')?.outerHTML?.slice(0, 300),
            show_chapters_val: document.querySelector('select#show_chapters')?.value,
        })""")
        print(f"  State: {pag_state}")

        # Check for any error messages on the page
        errors = page.evaluate("""[...document.querySelectorAll('.error, .alert, [class*="error"], [class*="notice"]')]
            .map(el => el.textContent.trim())
            .filter(t => t.length > 0)
            .join(' | ')
        """)
        if errors:
            print(f"  Page errors: {errors}")

        # Check console errors
        print(f"\n[4] Network log:")
        for r in requests_log:
            print(f"  REQ: {r}")
        for r in responses_log:
            print(f"  RESP: {r}")

        # Try clicking page 2 via JS (simulating what the pagination does)
        print(f"\n[5] Trying JS click on page 2 link...")
        result = page.evaluate("""(() => {
            const links = document.querySelectorAll('ul#pagination-mesh-toc a.page-link');
            for (const a of links) {
                if (a.textContent.trim() === '2') {
                    a.click();
                    return 'clicked: ' + a.href;
                }
            }
            return 'not found';
        })()""")
        print(f"  Click result: {result}")

        time.sleep(10)
        toc_count = page.evaluate("document.querySelectorAll('li.toc_w').length")
        print(f"  Chapters after click + 10s: {toc_count}")

        # Check the TOC content
        toc_html = page.evaluate("document.querySelector('.toc_ol')?.innerHTML?.slice(0, 500) || '(no toc_ol)'")
        print(f"  TOC content: {toc_html}")

        # Check network again
        print(f"\n[6] Network log after click:")
        for r in requests_log:
            print(f"  REQ: {r}")
        for r in responses_log:
            print(f"  RESP: {r}")

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
