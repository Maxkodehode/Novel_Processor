"""
Deep diagnostic: find ALL chapter data embedded in the ScribbleHub page HTML.
Checks for JSON data, hidden elements, data attributes, etc.
"""

import sys
import re
import json
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
        print("Usage: python diag_deep.py <url>")
        sys.exit(1)

    url = sys.argv[1]
    print(f"Target: {url}\n")

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

        page.goto(url, wait_until="load", timeout=60000)
        time.sleep(3)

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")

        # 1. Check all script tags for chapter data
        print("=" * 60)
        print("[1] Searching all <script> tags for chapter data")
        print("=" * 60)

        for i, script in enumerate(soup.find_all("script")):
            text = script.string or ""

            # Look for arrays of objects with chapter-like keys
            for pattern_name, pattern in [
                ("chapter_data", r"chapter_data\s*=\s*(\[.*?\]);"),
                ("toc_chapters", r"toc_chapters\s*=\s*(\[.*?\]);"),
                ("chapters\s*=", r"chapters\s*=\s*(\[.*?\]);"),
                ("fic_chapters", r"fic_chapters\s*=\s*(\[.*?\]);"),
                ("all_chapters", r"all_chapters\s*=\s*(\[.*?\]);"),
                ("window.chapters", r"window\.chapters\s*=\s*(\[.*?\]);"),
            ]:
                m = re.search(pattern, text, re.DOTALL)
                if m:
                    try:
                        data = json.loads(m.group(1))
                        print(f"\n  Script #{i}: Found '{pattern_name}' with {len(data)} items")
                        if data:
                            print(f"    First item keys: {list(data[0].keys()) if isinstance(data[0], dict) else type(data[0])}")
                            print(f"    First item: {json.dumps(data[0], indent=2)[:200]}")
                    except json.JSONDecodeError:
                        print(f"\n  Script #{i}: Found '{pattern_name}' but JSON parse failed")
                        print(f"    Raw: {m.group(1)[:200]}")

            # Look for any large JSON arrays
            for m in re.finditer(r"\[[\s\S]{100,5000}\]", text):
                try:
                    data = json.loads(m.group(0))
                    if isinstance(data, list) and len(data) > 5:
                        if isinstance(data[0], dict):
                            keys = set()
                            for item in data[:3]:
                                keys.update(item.keys())
                            if any(k in keys for k in ["title", "chapter", "url", "order", "id", "name"]):
                                print(f"\n  Script #{i}: Large JSON array with {len(data)} items, keys: {keys}")
                except (json.JSONDecodeError, IndexError):
                    pass

        # 2. Check data attributes on TOC elements
        print(f"\n{'='*60}")
        print("[2] Checking data attributes on TOC elements")
        print("=" * 60)

        for li in soup.select("li.toc_w"):
            attrs = dict(li.attrs)
            print(f"  data attrs: {attrs}")
            link = li.select_one("a")
            if link:
                print(f"  link href: {link.get('href', '')}")
            break  # Just first one

        # 3. Check for hidden divs with chapter data
        print(f"\n{'='*60}")
        print("[3] Checking for hidden chapter containers")
        print("=" * 60)

        for sel in ["div.toc", "#toc-section", ".wi_fic_table", "#chpadd",
                     "div.chapter-list", "#chapter-list", ".fic_toc",
                     "[data-chapters]", "[data-toc]"]:
            els = soup.select(sel)
            if els:
                for el in els:
                    text_len = len(el.get_text())
                    html_len = len(str(el))
                    children = len(el.find_all(recursive=False))
                    print(f"  {sel}: text={text_len}b, html={html_len}b, children={children}")
                    if html_len < 5000:
                        print(f"    HTML: {str(el)[:500]}")

        # 4. Check the pagination JS to understand what it does
        print(f"\n{'='*60}")
        print("[4] Checking pagination element structure")
        print("=" * 60)

        pag = soup.select_one("ul#pagination-mesh-toc")
        if pag:
            print(f"  Pagination HTML:\n{pag.prettify()[:1000]}")

        # 5. Check for noscript fallback
        print(f"\n{'='*60}")
        print("[5] Checking <noscript> tags")
        print("=" * 60)

        for ns in soup.select("noscript"):
            text = ns.get_text(strip=True)
            if text:
                print(f"  noscript content ({len(text)} chars): {text[:200]}")

        # 6. Check all elements with data-id
        print(f"\n{'='*60}")
        print("[6] Elements with data-id attribute")
        print("=" * 60)

        data_id_els = soup.select("[data-id]")
        print(f"  Found {len(data_id_els)} elements with data-id")
        for el in data_id_els[:5]:
            print(f"    <{el.name} data-id='{el.get('data-id')}'> classes={el.get('class')}")

        # 7. Check for inline JSON in data attributes
        print(f"\n{'='*60}")
        print("[7] Elements with JSON in data attributes")
        print("=" * 60)

        for el in soup.select("[data-json], [data-chapters], [data-toc], [data-pages]"):
            for attr in el.attrs:
                if attr.startswith("data-") and len(el[attr]) > 20:
                    try:
                        data = json.loads(el[attr])
                        print(f"  <{el.name} {attr}> = {type(data).__name__} with {len(data) if hasattr(data, '__len__') else '?'} items")
                    except (json.JSONDecodeError, TypeError):
                        print(f"  <{el.name} {attr}> = string ({len(el[attr])} chars)")

        # 8. Look at the actual page source for any chapter URL patterns
        print(f"\n{'='*60}")
        print("[8] Chapter URL patterns in HTML")
        print("=" * 60)

        chapter_urls = set()
        for a in soup.select("a[href*='/chapter/'], a[href*='/read/'], a[href*='/fiction/']"):
            href = a.get("href", "")
            if href:
                chapter_urls.add(href)

        print(f"  Found {len(chapter_urls)} unique chapter-like URLs")
        for u in sorted(chapter_urls)[:20]:
            print(f"    {u}")

        # 9. Check if there's a "show all" or "load more" button
        print(f"\n{'='*60}")
        print("[9] Buttons and links for loading more chapters")
        print("=" * 60)

        for el in soup.select("button, a, [role='button'], .btn, [class*='load'], [class*='show'], [class*='more'], [class*='all']"):
            text = el.get_text(strip=True).lower()
            if any(word in text for word in ["all", "more", "load", "show", "chapter", "toc", "full"]):
                print(f"  <{el.name}> text='{el.get_text(strip=True)}' classes={el.get('class')} id={el.get('id')}")

        # 10. Check the select#show_chapters dropdown
        print(f"\n{'='*60}")
        print("[10] select#show_chapters dropdown")
        print("=" * 60)

        sel = soup.select_one("select#show_chapters")
        if sel:
            print(f"  Found! Options:")
            for opt in sel.select("option"):
                print(f"    value='{opt.get('value')}' text='{opt.get_text(strip=True)}'")
        else:
            print(f"  Not found")

        context.close()
        browser.close()


if __name__ == "__main__":
    import time
    main()
