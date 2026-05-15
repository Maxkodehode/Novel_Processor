"""
Test: Can we construct chapter URLs from the pattern we see?
The chapters we have show a pattern:
  /read/1857436-the-rusting-robots-and-revenge/chapter/2328763/
  
The chapter IDs don't match the order numbers. But maybe we can find
all chapter IDs from the page somehow.

Also test: can we use the ScribbleHub API or RSS feed?
"""

import sys
import re
import json
import requests
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
    series_id = re.search(r'/series/(\d+)/', base_url)
    series_id = series_id.group(1) if series_id else "1857436"
    print(f"URL: {base_url}")
    print(f"Series ID: {series_id}\n")

    # 1. Try RSS feed
    print("=" * 60)
    print("[1] Trying RSS feed")
    print("=" * 60)

    rss_urls = [
        f"https://www.scribblehub.com/feed/?post_type=fiction&series_id={series_id}",
        f"https://www.scribblehub.com/feed/?series={series_id}",
        f"{base_url}/feed/",
    ]

    for rss_url in rss_urls:
        try:
            resp = requests.get(rss_url, headers={"User-Agent": USER_AGENT}, timeout=10)
            print(f"  {rss_url} -> {resp.status_code} ({len(resp.text)} bytes)")
            if resp.status_code == 200 and len(resp.text) > 100:
                soup = BeautifulSoup(resp.text, "xml")
                items = soup.find_all("item")
                print(f"    RSS items: {len(items)}")
                if items:
                    print(f"    First item: {items[0].title.text if items[0].title else '?'}")
                    # Extract chapter links from RSS
                    for item in items[:5]:
                        link = item.link.text if item.link else "?"
                        title = item.title.text if item.title else "?"
                        print(f"    - {title}: {link}")
        except Exception as e:
            print(f"  {rss_url} -> ERROR: {e}")

    # 2. Try the ScribbleHub API
    print(f"\n{'='*60}")
    print("[2] Trying ScribbleHub API endpoints")
    print("=" * 60)

    api_urls = [
        f"https://www.scribblehub.com/wp-json/wp/v2/fiction?series={series_id}",
        f"https://www.scribblehub.com/wp-json/wp/v2/chapter?series={series_id}",
        f"https://www.scribblehub.com/wp-json/sh/v1/series/{series_id}",
        f"https://www.scribblehub.com/wp-json/sh/v1/chapters/{series_id}",
    ]

    for api_url in api_urls:
        try:
            resp = requests.get(api_url, headers={"User-Agent": USER_AGENT}, timeout=10)
            print(f"  {api_url} -> {resp.status_code} ({len(resp.text)} bytes)")
            if resp.status_code == 200 and len(resp.text) > 100:
                try:
                    data = json.loads(resp.text)
                    print(f"    JSON type: {type(data).__name__}")
                    if isinstance(data, list):
                        print(f"    Items: {len(data)}")
                        if data:
                            print(f"    First item keys: {list(data[0].keys())[:10]}")
                    elif isinstance(data, dict):
                        print(f"    Keys: {list(data.keys())[:10]}")
                except json.JSONDecodeError:
                    print(f"    Not JSON: {resp.text[:100]}")
        except Exception as e:
            print(f"  {api_url} -> ERROR: {e}")

    # 3. Try curl_cffi with cookies from a fresh session
    print(f"\n{'='*60}")
    print("[3] Trying curl_cffi with fresh session + cookies")
    print("=" * 60)

    try:
        from curl_cffi import requests as curl_requests

        # First get the page to collect cookies
        session = curl_requests.Session()
        resp = session.get(base_url, impersonate="chrome", timeout=30)
        print(f"  Initial GET: {resp.status_code}")
        print(f"  Cookies: {list(session.cookies.keys())}")

        # Now try admin-ajax.php with those cookies
        ajax_url = "https://www.scribblehub.com/wp-admin/admin-ajax.php"

        # Try various action names
        for action in ["toc_fic_show_all", "toc_fic_pagination", "load_toc_chapters"]:
            for page in [1, 2]:
                try:
                    post_data = {
                        "action": action,
                        "page": str(page),
                        "post_id": series_id,
                    }
                    resp = session.post(
                        ajax_url,
                        data=post_data,
                        headers={
                            "User-Agent": USER_AGENT,
                            "X-Requested-With": "XMLHttpRequest",
                            "Referer": base_url,
                        },
                        timeout=15,
                    )
                    body = resp.text.strip()
                    print(f"  action={action} page={page} -> {resp.status_code} ({len(body)} bytes)")
                    if body and len(body) > 10 and not body.startswith("<!DOCTYPE"):
                        print(f"    Preview: {body[:200]}")
                        if "toc_w" in body or "<li" in body:
                            print(f"    *** CONTAINS CHAPTER HTML ***")
                            frag_soup = BeautifulSoup(body, "html.parser")
                            ch = frag_soup.select("li.toc_w")
                            print(f"    Chapters: {len(ch)}")
                except Exception as e:
                    print(f"  action={action} page={page} -> ERROR: {e}")

    except ImportError:
        print("  curl_cffi not available")

    # 4. Check if we can find chapter IDs in the page source
    print(f"\n{'='*60}")
    print("[4] Searching page source for chapter ID patterns")
    print("=" * 60)

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

        page.goto(base_url, wait_until="load", timeout=60000)
        time.sleep(3)

        html = page.content()

        # Find all chapter URLs
        chapter_urls = re.findall(
            r'href="https://www\.scribblehub\.com/read/\d+-[^/]+/chapter/(\d+)/"',
            html
        )
        print(f"  Chapter IDs found in HTML: {len(chapter_urls)}")
        if chapter_urls:
            print(f"  IDs: {chapter_urls}")

        # Find any data attributes with chapter info
        data_ids = re.findall(r'data-(?:id|chapter|order|toc)="([^"]+)"', html)
        print(f"  data-id/chapter/order/toc attrs: {data_ids[:20]}")

        # Look for any JSON with chapter IDs
        for m in re.finditer(r'"chapter[^"]*"\s*:\s*(\[.*?\]|\{.*?\})', html, re.DOTALL):
            try:
                data = json.loads(m.group(1))
                print(f"  Found chapter JSON: {str(data)[:200]}")
            except json.JSONDecodeError:
                pass

        # Look for post meta or other data sources
        post_meta = re.findall(r'<meta[^>]+content="([^"]*chapter[^"]*)"', html, re.I)
        print(f"  Chapter meta tags: {post_meta}")

        context.close()
        browser.close()


if __name__ == "__main__":
    import time
    main()
