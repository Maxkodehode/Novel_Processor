"""
sh_debug_fetch.py

Fetches the ScribbleHub page AND one AJAX chapter-list response,
saves both to disk so we can inspect exactly what the site returns.

Usage:
    python sh_debug_fetch.py <url>

Example:
    python sh_debug_fetch.py https://www.scribblehub.com/series/1704374/dreams-of-joel/
"""

import sys
import re
import json
from urllib.parse import urlencode
from playwright.sync_api import sync_playwright

URL = (
    sys.argv[1]
    if len(sys.argv) > 1
    else "https://www.scribblehub.com/series/1704374/dreams-of-joel/"
)
PAGE_HTML_FILE = "sh_debug_page.html"
AJAX_RAW_FILE = "sh_ajax_page1_raw.json"
AJAX_HTML_FILE = "sh_ajax_page1_fragment.html"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent=USER_AGENT)
    page = ctx.new_page()

    print(f"[*] Loading {URL} ...")
    page.goto(URL, wait_until="networkidle", timeout=60_000)

    # Dismiss cookie banners
    for label in ("Accept", "Accept All", "I Agree", "OK"):
        try:
            btn = page.get_by_role("button", name=label)
            if btn.is_visible():
                btn.click()
                page.wait_for_timeout(1500)
                break
        except Exception:
            pass

    html = page.content()
    with open(PAGE_HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[*] Page HTML saved to {PAGE_HTML_FILE} ({len(html):,} bytes)")

    # Extract story ID from URL
    m = re.search(r"/series/(\d+)/", URL)
    story_id = m.group(1) if m else None
    print(f"[*] Story ID: {story_id}")

    if story_id:
        # Fire the AJAX request from inside the live browser session
        print("[*] Firing AJAX request for chapter page 1 (cnt=50) ...")
        body = urlencode(
            {
                "action": "wi_gettocchp",
                "pageid": story_id,
                "mypostid": story_id,
                "pagenum": 1,
                "cnt": 50,
            }
        )
        resp = page.request.post(
            "https://www.scribblehub.com/wp-admin/admin-ajax.php",
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": URL,
            },
            data=body,
        )
        print(f"[*] AJAX response status: {resp.status}")
        raw = resp.text()

        with open(AJAX_RAW_FILE, "w", encoding="utf-8") as f:
            f.write(raw)
        print(f"[*] Raw AJAX response saved to {AJAX_RAW_FILE} ({len(raw):,} bytes)")

        # Also extract and save just the HTML fragment if it's JSON-wrapped
        try:
            payload = json.loads(raw)
            html_frag = payload.get("data", raw)
            with open(AJAX_HTML_FILE, "w", encoding="utf-8") as f:
                f.write(html_frag)
            print(
                f"[*] HTML fragment saved to {AJAX_HTML_FILE} ({len(html_frag):,} bytes)"
            )
            print(f"[*] AJAX success field: {payload.get('success')}")
        except json.JSONDecodeError:
            print("[!] Response is not JSON — saved as-is in the raw file")

    browser.close()

print("\n[✓] Done. Please send these files:")
print(f"    {PAGE_HTML_FILE}")
print(f"    {AJAX_RAW_FILE}")
print(f"    {AJAX_HTML_FILE}  (if it was created)")
