"""
ScribbleHub chapter-loading diagnostic.

Tests 4 approaches to get all chapters from a ScribbleHub novel page:
  1. Static HTML (what's in the DOM after page load)
  2. toc_fic_show_all() JS function
  3. Pagination click + AJAX capture (current approach)
  4. Direct admin-ajax.php POST (brute force)

Usage:
    python diag_sh.py <url>

Example:
    python diag_sh.py https://www.scribblehub.com/series/1857436/the-rusting-robots-and-revenge/
"""

import sys
import time
import json
import requests
from playwright.sync_api import sync_playwright

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
        print("Usage: python diag_sh.py <scribblehub_novel_url>")
        sys.exit(1)

    url = sys.argv[1]
    print(f"Target: {url}")
    print(f"Stealth available: {_STEALTH}")
    print("=" * 70)

    # ── Approach 0: curl first to get cookie + check raw HTML ──
    print("\n[APPROACH 0] curl_cffi GET - check raw HTML chapter count")
    try:
        from curl_cffi import requests as curl_requests
        resp = curl_requests.get(url, impersonate="chrome", timeout=30)
        print(f"  Status: {resp.status_code}")
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        toc_count = len(soup.select("li.toc_w"))
        print(f"  li.toc_w count in raw HTML: {toc_count}")
        badge = soup.select_one("span.cnt_toc")
        if badge:
            print(f"  Chapter badge: {badge.get_text(strip=True)}")
        pag = soup.select_one("ul#pagination-mesh-toc")
        if pag:
            links = [a.get_text(strip=True) for a in pag.select("a.page-link")]
            print(f"  Pagination links: {links}")
        else:
            print(f"  No pagination bar found in raw HTML")

        # Check for toc_fic_show_all reference
        for script in soup.find_all("script"):
            text = script.string or ""
            if "toc_fic_show_all" in text:
                # Find the function definition
                idx = text.find("toc_fic_show_all")
                snippet = text[max(0,idx-50):idx+200]
                print(f"\n  FOUND toc_fic_show_all in script:")
                print(f"  ...{snippet}...")
                break
        else:
            print(f"\n  toc_fic_show_all NOT found in any <script> tag")

        # Check for AJAX-related JS
        for script in soup.find_all("script"):
            text = script.string or ""
            if "admin-ajax" in text:
                idx = text.find("admin-ajax")
                snippet = text[max(0,idx-100):idx+100]
                print(f"\n  FOUND admin-ajax reference:")
                print(f"  ...{snippet}...")
                break

        # List all script src URLs
        print(f"\n  External script sources:")
        for script in soup.find_all("script", src=True):
            src = script["src"]
            if "scribblehub" in src or "wp-content" in src:
                print(f"    {src}")

    except Exception as e:
        print(f"  curl approach failed: {e}")

    # ── Playwright-based approaches ──
    print(f"\n{'='*70}")
    print("[PLAYWRIGHT] Launching browser...")
    print("=" * 70)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
        )

        # Capture ALL network responses for analysis
        ajax_responses = []

        page = context.new_page()
        if _STEALTH:
            stealth_sync(page)

        # Log all network requests/responses for analysis
        def on_request(request):
            if "admin-ajax" in request.url or "toc" in request.url.lower():
                print(f"  [NET REQ] {request.method} {request.url[:120]}")

        def on_response(response):
            if "admin-ajax" in response.url or "toc" in response.url.lower():
                try:
                    body_preview = response.text()[:300]
                except:
                    body_preview = "(could not read body)"
                entry = {
                    "url": response.url,
                    "status": response.status,
                    "body_preview": body_preview,
                }
                ajax_responses.append(entry)
                print(f"  [NET RESP] {response.status} {response.url[:120]}")
                print(f"    Body preview: {body_preview[:200]}")

        page.on("request", on_request)
        page.on("response", on_response)

        print(f"\nNavigating to: {url}")
        page.goto(url, wait_until="load", timeout=60000)
        print("Page loaded. Waiting 3s for JS to settle...")
        time.sleep(3)

        # ── Approach 1: Static DOM ──
        print(f"\n{'='*70}")
        print("[APPROACH 1] Static DOM - li.toc_w count")
        print("=" * 70)

        toc_count = page.evaluate("document.querySelectorAll('li.toc_w').length")
        badge_text = page.evaluate(
            "document.querySelector('span.cnt_toc')?.textContent?.trim() || ''"
        )
        print(f"  li.toc_w elements: {toc_count}")
        print(f"  Chapter badge: {badge_text}")

        pag_exists = page.evaluate("!!document.querySelector('ul#pagination-mesh-toc')")
        if pag_exists:
            page_links = page.evaluate(
                "[...document.querySelectorAll('ul#pagination-mesh-toc a.page-link')]"
                ".map(a => a.textContent.trim())"
            )
            print(f"  Pagination links: {page_links}")
        else:
            print(f"  No pagination bar")

        # ── Approach 2: toc_fic_show_all() ──
        print(f"\n{'='*70}")
        print("[APPROACH 2] toc_fic_show_all() JS function")
        print("=" * 70)

        fn_exists = page.evaluate("typeof toc_fic_show_all === 'function'")
        print(f"  toc_fic_show_all exists: {fn_exists}")

        if fn_exists:
            try:
                page.evaluate("toc_fic_show_all()")
                print("  Called toc_fic_show_all()")
                print("  Waiting 8 seconds for DOM changes...")
                time.sleep(8)

                after_count = page.evaluate("document.querySelectorAll('li.toc_w').length")
                print(f"  li.toc_w after call: {after_count}")

                # Check for loading indicators
                loading = page.evaluate(
                    "!!document.querySelector('.loading, .spinner, [class*=\"load\"]')"
                )
                print(f"  Loading indicator visible: {loading}")

                # Check new pagination state
                page_links_after = page.evaluate(
                    "[...document.querySelectorAll('ul#pagination-mesh-toc a.page-link')]"
                    ".map(a => a.textContent.trim())"
                )
                print(f"  Pagination links after: {page_links_after}")

                # Check for new pagination that might have appeared
                all_pag = page.evaluate(
                    "[...document.querySelectorAll('[id*=pagination], [class*=pagination')]"
                    ".map(el => el.outerHTML.slice(0,100))"
                )
                if all_pag:
                    print(f"  All pagination elements: {all_pag[:5]}")

            except Exception as e:
                print(f"  toc_fic_show_all() failed: {e}")
        else:
            # Probe for alternative functions
            alt_fns = page.evaluate(
                "Object.getOwnPropertyNames(window)"
                ".filter(k => typeof window[k] === 'function' && "
                "(k.toLowerCase().includes('toc') || k.toLowerCase().includes('chapter') || "
                "k.toLowerCase().includes('fic') || k.toLowerCase().includes('load') || "
                "k.toLowerCase().includes('show')))"
                ".slice(0, 20)"
            )
            print(f"  Alternative functions: {alt_fns}")

            # Check for large data objects on window
            large_objs = page.evaluate(
                "Object.getOwnPropertyNames(window)"
                ".filter(k => {"
                "  try {"
                "    const v = window[k];"
                "    if (Array.isArray(v) && v.length > 5) return true;"
                "    if (typeof v === 'object' && v !== null && !Array.isArray(v)"
                "        && Object.keys(v).length > 5) return true;"
                "    return false;"
                "  } catch(e) { return false; }"
                "}).slice(0, 15)"
            )
            print(f"  Large JS objects on window: {large_objs}")

            # Check for ScribbleHub's newer AJAX pagination
            js_check = page.evaluate(
                "JSON.stringify({"
                "  wpAjax: typeof wpAjaxUrl !== 'undefined' ? wpAjaxUrl : null,"
                "  ajaxurl: typeof ajaxurl !== 'undefined' ? ajaxurl : null,"
                "  fic_slug: typeof fic_slug !== 'undefined' ? fic_slug : null,"
                "  chicp_count: typeof chicp_count !== 'undefined' ? chicp_count : null,"
                "  toc_chapters: typeof toc_chapters !== 'undefined' ? toc_chapters.length : null,"
                "  toc_pages: typeof toc_pages !== 'undefined' ? toc_pages : null,"
                "  toc_paged: typeof toc_paged !== 'undefined' ? toc_paged : null,"
                "  toc_order: typeof toc_order !== 'undefined' ? toc_order : null,"
                "  toc_show_all: typeof toc_show_all !== 'undefined' ? toc_show_all : null,"
                "  toc_fic_show_all: typeof toc_fic_show_all !== 'undefined' ? 'exists' : 'missing',"
                "  jQuery: typeof jQuery !== 'undefined' ? jQuery.fn.jquery : 'not loaded',"
                "})"
            )
            print(f"  ScribbleHub JS globals: {js_check}")

        # ── Approach 3: Pagination click ──
        print(f"\n{'='*70}")
        print("[APPROACH 3] Pagination click + AJAX capture")
        print("=" * 70)

        # Reset captured responses
        ajax_responses.clear()

        # Re-register a targeted response listener
        captured = {}

        def on_resp(response):
            if "admin-ajax.php" not in response.url:
                return
            try:
                body = response.body()
                captured["body"] = body
                captured["status"] = response.status
                print(f"  [AJAX CAPTURED] status={response.status} size={len(body)}")
            except Exception as e:
                captured["error"] = str(e)
                print(f"  [AJAX ERROR] {e}")

        page.on("response", on_resp)

        # Try clicking page 2
        clicked = page.evaluate(
            "(() => {"
            "  const links = document.querySelectorAll('ul#pagination-mesh-toc a.page-link');"
            "  for (const a of links) {"
            "    if (a.textContent.trim() === '2') { a.click(); return true; }"
            "  }"
            "  return false;"
            "})()"
        )
        print(f"  Clicked page 2: {clicked}")

        if clicked:
            print("  Waiting 10 seconds for AJAX response...")
            time.sleep(10)

            if "body" in captured:
                try:
                    html_frag = captured["body"].decode("utf-8", errors="replace")
                    print(f"  Response body length: {len(html_frag)}")
                    print(f"  Response preview: {html_frag[:300]}")

                    frag_soup = BeautifulSoup(html_frag, "html.parser")
                    frag_chapters = frag_soup.select("li.toc_w")
                    print(f"  Chapters in response: {len(frag_chapters)}")
                except Exception as e:
                    print(f"  Failed to parse response: {e}")
            elif "error" in captured:
                print(f"  Error capturing: {captured['error']}")
            else:
                print(f"  No AJAX response captured (timeout)")

            # Check DOM state after click
            after_click_count = page.evaluate("document.querySelectorAll('li.toc_w').length")
            print(f"  li.toc_w count after click: {after_click_count}")

        # ── Approach 4: Direct admin-ajax.php POST ──
        print(f"\n{'='*70}")
        print("[APPROACH 4] Direct admin-ajax.php POST")
        print("=" * 70)

        # Try to discover the AJAX URL and parameters
        ajax_url = page.evaluate(
            "(() => {"
            "  if (typeof ajaxurl !== 'undefined') return ajaxurl;"
            "  // Try to find it in script tags"
            "  const scripts = document.querySelectorAll('script');"
            "  for (const s of scripts) {"
            "    const text = s.textContent || '';"
            "    const m = text.match(/ajaxurl\\s*=\\s*['\"]([^'\"]+)['\"]/);"
            "    if (m) return m[1];"
            "    const m2 = text.match(/ajax_url\\s*[:=]\\s*['\"]([^'\"]+)['\"]/);"
            "    if (m2) return m2[1];"
            "  }"
            "  return 'https://www.scribblehub.com/wp-admin/admin-ajax.php';"
            "})()"
        )
        print(f"  AJAX URL: {ajax_url}")

        # Try to get the nonce
        nonce = page.evaluate(
            "(() => {"
            "  // Try various nonce variable names"
            "  if (typeof toc_fic_nonce !== 'undefined') return toc_fic_nonce;"
            "  if (typeof fic_ajax_nonce !== 'undefined') return fic_ajax_nonce;"
            "  if (typeof ajax_nonce !== 'undefined') return ajax_nonce;"
            "  // Try from script tags"
            "  const scripts = document.querySelectorAll('script');"
            "  for (const s of scripts) {"
            "    const text = s.textContent || '';"
            "    const m = text.match(/nonce['\"\\s:=]+['\"]([a-f0-9]{10,})['\"]/i);"
            "    if (m) return m[1];"
            "  }"
            "  return null;"
            "})()"
        )
        print(f"  Nonce: {nonce}")

        # Try direct POST with various action names
        cookies = context.cookies()
        cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

        actions_to_try = [
            "toc_fic_show_all",
            "toc_fic_pagination",
            "load_toc_chapters",
            "fic_toc_load",
            "toc_load_more",
            "show_all_chapters",
            "get_toc",
            "load_chapters",
        ]

        for action in actions_to_try:
            try:
                post_data = {
                    "action": action,
                    "page": "2",
                }
                if nonce:
                    post_data["nonce"] = nonce
                    post_data["security"] = nonce

                headers = {
                    "User-Agent": USER_AGENT,
                    "Cookie": cookie_str,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": url,
                    "X-Requested-With": "XMLHttpRequest",
                }

                resp = requests.post(
                    ajax_url,
                    data=post_data,
                    headers=headers,
                    timeout=15,
                )
                body_text = resp.text.strip()
                print(f"\n  Action='{action}' -> HTTP {resp.status_code}, body length={len(body_text)}")
                if body_text and len(body_text) > 5:
                    print(f"    Preview: {body_text[:200]}")
                    # Check if it contains chapter data
                    if "toc_w" in body_text or "li" in body_text:
                        print(f"    *** CONTAINS HTML CHAPTER DATA ***")
                        frag_soup = BeautifulSoup(body_text, "html.parser")
                        ch_count = len(frag_soup.select("li.toc_w"))
                        print(f"    Chapters found: {ch_count}")
                    elif body_text.startswith("{") or body_text.startswith("["):
                        try:
                            data = json.loads(body_text)
                            print(f"    JSON keys: {list(data.keys()) if isinstance(data, dict) else f'array[{len(data)}]'}")
                        except:
                            pass
            except Exception as e:
                print(f"  Action='{action}' -> ERROR: {e}")

        # ── Summary ──
        print(f"\n{'='*70}")
        print("[SUMMARY]")
        print("=" * 70)
        print(f"  Static HTML chapters: {toc_count}")
        print(f"  Chapter badge says: {badge_text}")
        print(f"  toc_fic_show_all exists: {fn_exists}")
        if fn_exists:
            print(f"  After toc_fic_show_all(): {after_count} chapters")
        print(f"  Pagination click worked: {clicked}")
        if clicked and "body" in captured:
            print(f"  AJAX response captured: yes ({len(captured['body'])} bytes)")
        elif clicked:
            print(f"  AJAX response captured: NO")

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
