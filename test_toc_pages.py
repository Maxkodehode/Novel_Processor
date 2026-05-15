"""
Test the ?toc=N pagination approach to get all chapters.
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
    if len(sys.argv) < 2:
        print("Usage: python test_toc_pages.py <url>")
        sys.exit(1)

    url = sys.argv[1]
    base_url = url.rstrip("/")
    print(f"Base URL: {base_url}\n")

    all_chapters = []

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

        # First, get the base page to find total pages
        print("[Page 1] Loading base page...")
        page.goto(base_url, wait_until="load", timeout=60000)
        time.sleep(2)

        # Get chapter badge count
        badge = page.evaluate(
            "document.querySelector('span.cnt_toc')?.textContent?.trim() || ''"
        )
        print(f"  Chapter badge: {badge}")

        # Get total TOC pages from pagination
        last_page = 1
        page_links = page.evaluate(
            "[...document.querySelectorAll('ul#pagination-mesh-toc a.page-link')]"
            ".map(a => a.textContent.trim())"
        )
        print(f"  Pagination links: {page_links}")

        for txt in page_links:
            if txt.isdigit():
                last_page = max(last_page, int(txt))

        # Also check: does the URL have a ?toc= parameter we can use?
        print(f"  Last page number: {last_page}")

        # Extract chapters from page 1
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        chapters = soup.select("li.toc_w")
        print(f"  Chapters on page 1: {len(chapters)}")
        for ch in chapters:
            link = ch.select_one("a")
            order = ch.get("order")
            title = link.get_text(strip=True) if link else "?"
            href = link.get("href", "") if link else ""
            all_chapters.append({"order": order, "title": title, "url": href})
            print(f"    [{order}] {title}")

        # Now navigate to each ?toc=N page
        for toc_page in range(2, last_page + 1):
            toc_url = f"{base_url}/?toc={toc_page}"
            print(f"\n[Page {toc_page}] Loading {toc_page}/{last_page}...")
            print(f"  URL: {toc_url}")

            try:
                page.goto(toc_url, wait_until="load", timeout=60000)
                time.sleep(1)

                html = page.content()
                soup = BeautifulSoup(html, "html.parser")
                chapters = soup.select("li.toc_w")
                print(f"  Chapters on page {toc_page}: {len(chapters)}")

                for ch in chapters:
                    link = ch.select_one("a")
                    order = ch.get("order")
                    title = link.get_text(strip=True) if link else "?"
                    href = link.get("href", "") if link else ""
                    all_chapters.append({"order": order, "title": title, "url": href})
                    print(f"    [{order}] {title}")

            except Exception as e:
                print(f"  ERROR: {e}")

        # Also try the show_chapters=all approach
        print(f"\n[EXTRA] Trying ?show_chapters=50&toc=1 ...")
        try:
            page.goto(f"{base_url}/?show_chapters=50&toc=1", wait_until="load", timeout=60000)
            time.sleep(1)
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            chapters_50 = soup.select("li.toc_w")
            print(f"  Chapters with show_chapters=50: {len(chapters_50)}")
        except Exception as e:
            print(f"  ERROR: {e}")

        print(f"\n[EXTRA] Trying ?show_chapters=50 (no toc) ...")
        try:
            page.goto(f"{base_url}/?show_chapters=50", wait_until="load", timeout=60000)
            time.sleep(1)
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            chapters_50b = soup.select("li.toc_w")
            print(f"  Chapters with show_chapters=50 (no toc): {len(chapters_50b)}")
        except Exception as e:
            print(f"  ERROR: {e}")

        context.close()
        browser.close()

    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print("=" * 60)
    print(f"Total chapters collected: {len(all_chapters)}")

    # Deduplicate by order
    seen = set()
    unique = []
    for ch in all_chapters:
        if ch["order"] not in seen:
            seen.add(ch["order"])
            unique.append(ch)
    print(f"Unique chapters: {len(unique)}")

    if unique:
        orders = sorted([int(c["order"]) for c in unique if c["order"] and str(c["order"]).isdigit()])
        if orders:
            print(f"Order range: {min(orders)} to {max(orders)}")
            # Check for gaps
            expected = set(range(min(orders), max(orders) + 1))
            actual = set(orders)
            gaps = expected - actual
            if gaps:
                print(f"Gaps: {sorted(gaps)}")
            else:
                print(f"No gaps detected!")


if __name__ == "__main__":
    main()
