"""
debug_scribblehub.py -- ScribbleHub chapter fetch diagnostics

Launches a headed Playwright browser, navigates to a ScribbleHub novel page,
and dumps the DOM state at three stages:
  Stage 1: Immediately after page load
  Stage 2: After calling toc_fic_show_all() (or reporting what IS available)
  Stage 3: After attempting the pagination fallback

Usage:
    python debug_scribblehub.py <url>

Example:
    python debug_scribblehub.py https://www.scribblehub.com/series/1857436/the-rusting-robots-and-revenge/

Output:
  Labelled [STAGE1/2/3] print lines for copy-pasting into a bug report.
  Three HTML snapshots saved to the current directory:
    debug_sh_stage1.html, debug_sh_stage2.html, debug_sh_stage3.html
"""

import sys
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

try:
    from playwright_stealth import stealth_sync
    _STEALTH = True
except ImportError:
    _STEALTH = False
    print("WARNING: playwright_stealth not installed -- running without stealth")

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# JS snippets -- kept as plain strings to avoid f-string/brace conflicts
# ---------------------------------------------------------------------------

JS_TOC_COUNT = "document.querySelectorAll('li.toc_w').length"

JS_FN_DEFINED = "typeof toc_fic_show_all === 'function'"

JS_MENU_EXISTS = "!!document.querySelector('#menu_icon_fic')"

JS_SHOW_CHAPTERS_EXISTS = "!!document.querySelector('select#show_chapters')"

JS_PAGINATION_EXISTS = "!!document.querySelector('ul#pagination-mesh-toc')"

JS_TOC_DIV_EXISTS = "!!document.querySelector('div.toc')"

JS_TOC_SECTION_EXISTS = "!!document.querySelector('#toc-section')"

JS_PAGINATION_TEXTS = (
    "[...document.querySelectorAll('ul#pagination-mesh-toc a.page-link')]"
    ".map(a => a.textContent.trim())"
)

JS_TOC_CLASSES = (
    "[...new Set("
    "  [...document.querySelectorAll('[class]')]"
    "  .map(el => [...el.classList])"
    "  .flat()"
    "  .filter(c => c.includes('toc') || c.includes('chapter') || c.includes('chap'))"
    ")].slice(0, 30)"
)

JS_TOC_HTML = (
    "document.querySelector('div.toc, #toc-section, .wi_fic_table')"
    "?.innerHTML || '(no toc container found)'"
)

JS_MENU_CLASS = (
    "document.querySelector('#menu_icon_fic')?.className || '(missing)'"
)

JS_MENU_HTML = (
    "document.querySelector('#menu_icon_fic')?.outerHTML || '(missing)'"
)

JS_PAGINATION_HTML = (
    "document.querySelector('ul#pagination-mesh-toc')?.outerHTML || '(no pagination bar)'"
)

JS_ACTIVE_PAGE = (
    "document.querySelector("
    "  'ul#pagination-mesh-toc li.active a, ul#pagination-mesh-toc li.active span'"
    ")?.textContent?.trim() || '(no active indicator)'"
)

JS_LOADING_INDICATOR = (
    "!!document.querySelector('.loading, .spinner, [class*=\"load\"]')"
)

JS_CHAPTER_BADGE = (
    "document.querySelector('span.cnt_toc')?.textContent?.trim() || ''"
)

JS_CALL_TOC_SHOW_ALL = "toc_fic_show_all()"

JS_CLICK_PAGE_2 = (
    "(() => {"
    "  const links = document.querySelectorAll('ul#pagination-mesh-toc a.page-link');"
    "  for (const a of links) {"
    "    if (a.textContent.trim() === '2') { a.click(); return true; }"
    "  }"
    "  return false;"
    "})()"
)

JS_GLOBAL_FNS_TOC = (
    "Object.getOwnPropertyNames(window)"
    ".filter(k => typeof window[k] === 'function' && k.toLowerCase().includes('toc'))"
    ".slice(0, 10)"
)

JS_GLOBAL_FNS_CHAPTER = (
    "Object.getOwnPropertyNames(window)"
    ".filter(k => typeof window[k] === 'function' && k.toLowerCase().includes('chapter'))"
    ".slice(0, 10)"
)

JS_GLOBAL_FNS_SHOW = (
    "Object.getOwnPropertyNames(window)"
    ".filter(k => typeof window[k] === 'function' && k.toLowerCase().includes('show'))"
    ".slice(0, 10)"
)

JS_GLOBAL_FNS_LOAD = (
    "Object.getOwnPropertyNames(window)"
    ".filter(k => typeof window[k] === 'function' && k.toLowerCase().includes('load'))"
    ".slice(0, 10)"
)

JS_GLOBAL_FNS_FIC = (
    "Object.getOwnPropertyNames(window)"
    ".filter(k => typeof window[k] === 'function' && k.toLowerCase().includes('fic'))"
    ".slice(0, 10)"
)

JS_LARGE_GLOBALS = (
    "Object.getOwnPropertyNames(window)"
    ".filter(k => {"
    "  try {"
    "    const v = window[k];"
    "    return (Array.isArray(v) && v.length > 10)"
    "      || (typeof v === 'object' && v !== null && !Array.isArray(v)"
    "          && Object.keys(v).length > 5);"
    "  } catch(e) { return false; }"
    "}).slice(0, 20)"
)

# Built dynamically in dump functions because they embed an index
def js_toc_order(index):
    return (
        "document.querySelectorAll('li.toc_w')[" + str(index) + "]"
        "?.getAttribute('order')"
    )

def js_toc_title(index):
    return (
        "document.querySelectorAll('li.toc_w')[" + str(index) + "]"
        "?.querySelector('a')?.textContent?.trim()"
    )

# Alternative selectors to probe after toc_fic_show_all
ALT_SELECTORS = [
    "div.chapter-list li",
    ".toc_w",
    "li[data-id]",
    ".wi_fic_table li",
    "table.table li",
    "#chpadd li",
]

def js_alt_count(selector):
    return "document.querySelectorAll('" + selector + "').length"


# ---------------------------------------------------------------------------
# Safe evaluation helpers
# ---------------------------------------------------------------------------

def js_bool(page, expression):
    """Evaluate JS and return bool. Returns False on error."""
    try:
        return bool(page.evaluate(expression))
    except Exception as e:
        print("[JS ERROR] " + expression[:60] + ": " + str(e))
        return False


def js_int(page, expression):
    """Evaluate JS and return int. Returns 0 on error."""
    try:
        result = page.evaluate(expression)
        return int(result) if result is not None else 0
    except Exception as e:
        print("[JS ERROR] " + expression[:60] + ": " + str(e))
        return 0


def js_list(page, expression):
    """Evaluate JS and return list. Returns [] on error."""
    try:
        result = page.evaluate(expression)
        return list(result) if result else []
    except Exception as e:
        print("[JS ERROR] " + expression[:60] + ": " + str(e))
        return []


def js_str(page, expression, truncate=500):
    """Evaluate JS and return string, truncated. Returns error message on failure."""
    try:
        result = page.evaluate(expression)
        s = str(result) if result is not None else "(null)"
        return s[:truncate] + ("..." if len(s) > truncate else "")
    except Exception as e:
        return "(JS error: " + str(e)[:80] + ")"


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def save_html(page, filename):
    """Save current page HTML to a file."""
    try:
        html = page.content()
        with open(filename, "w", encoding="utf-8") as f:
            f.write(html)
        print("[SAVED] " + filename + " (" + str(len(html)) + " bytes)")
    except Exception as e:
        print("[SAVE ERROR] " + filename + ": " + str(e))


# ---------------------------------------------------------------------------
# Stage 1
# ---------------------------------------------------------------------------

def dump_stage1(page):
    """Dumps DOM state immediately after page load."""
    print("\n" + "=" * 60)
    print("[STAGE1] === After page load ===")
    print("=" * 60)

    toc_count = js_int(page, JS_TOC_COUNT)
    print("[STAGE1] li.toc_w count: " + str(toc_count))
    print("[STAGE1] toc_fic_show_all defined: " + str(js_bool(page, JS_FN_DEFINED)))
    print("[STAGE1] #menu_icon_fic exists: " + str(js_bool(page, JS_MENU_EXISTS)))
    print("[STAGE1] select#show_chapters exists: " + str(js_bool(page, JS_SHOW_CHAPTERS_EXISTS)))
    print("[STAGE1] ul#pagination-mesh-toc exists: " + str(js_bool(page, JS_PAGINATION_EXISTS)))
    print("[STAGE1] div.toc exists: " + str(js_bool(page, JS_TOC_DIV_EXISTS)))
    print("[STAGE1] #toc-section exists: " + str(js_bool(page, JS_TOC_SECTION_EXISTS)))

    page_texts = js_list(page, JS_PAGINATION_TEXTS)
    print("[STAGE1] pagination link texts: " + str(page_texts))

    for i in range(min(3, toc_count)):
        order = js_str(page, js_toc_order(i), 50)
        title = js_str(page, js_toc_title(i), 80)
        print("[STAGE1] toc_w[" + str(i) + "] order attr: " + order)
        print("[STAGE1] toc_w[" + str(i) + "] title: " + title)

    toc_html = js_str(page, JS_TOC_HTML, 500)
    print("[STAGE1] TOC container HTML: " + toc_html)

    toc_classes = js_list(page, JS_TOC_CLASSES)
    print("[STAGE1] toc/chapter-related CSS classes in page: " + str(toc_classes))

    if js_bool(page, JS_MENU_EXISTS):
        print("[STAGE1] #menu_icon_fic class: " + js_str(page, JS_MENU_CLASS, 200))
        print("[STAGE1] #menu_icon_fic HTML: " + js_str(page, JS_MENU_HTML, 300))


# ---------------------------------------------------------------------------
# Stage 2a -- toc_fic_show_all IS defined
# ---------------------------------------------------------------------------

def dump_stage2_function_found(page, chapter_count):
    """Calls toc_fic_show_all() and dumps DOM state afterwards."""
    print("\n" + "=" * 60)
    print("[STAGE2] === Calling toc_fic_show_all() ===")
    print("=" * 60)

    try:
        page.evaluate(JS_CALL_TOC_SHOW_ALL)
        print("[STAGE2] toc_fic_show_all() called -- no immediate exception")
    except Exception as e:
        print("[STAGE2] toc_fic_show_all() threw: " + str(e))
        return

    print("[STAGE2] Waiting 5 seconds for DOM changes...")
    time.sleep(5)

    after_count = js_int(page, JS_TOC_COUNT)
    print("[STAGE2] li.toc_w count after call: " + str(after_count))
    print("[STAGE2] Expected (from badge): " + str(chapter_count))

    print("[STAGE2] #menu_icon_fic exists: " + str(js_bool(page, JS_MENU_EXISTS)))
    print("[STAGE2] #menu_icon_fic class: " + js_str(page, JS_MENU_CLASS, 200))
    print("[STAGE2] ul#pagination-mesh-toc exists: " + str(js_bool(page, JS_PAGINATION_EXISTS)))

    page_texts = js_list(page, JS_PAGINATION_TEXTS)
    print("[STAGE2] pagination link texts after call: " + str(page_texts))

    toc_html = js_str(page, JS_TOC_HTML, 500)
    print("[STAGE2] TOC container HTML after call: " + toc_html)

    for sel in ALT_SELECTORS:
        count = js_int(page, js_alt_count(sel))
        if count > 0:
            print("[STAGE2] Alternative selector '" + sel + "' found " + str(count) + " elements")

    loading = js_bool(page, JS_LOADING_INDICATOR)
    print("[STAGE2] Loading indicator visible: " + str(loading))


# ---------------------------------------------------------------------------
# Stage 2b -- toc_fic_show_all NOT defined
# ---------------------------------------------------------------------------

def dump_stage2_function_missing(page):
    """Lists alternative JS functions and data when toc_fic_show_all is absent."""
    print("\n" + "=" * 60)
    print("[STAGE2] === toc_fic_show_all NOT DEFINED ===")
    print("=" * 60)

    pairs = [
        ("toc", JS_GLOBAL_FNS_TOC),
        ("chapter", JS_GLOBAL_FNS_CHAPTER),
        ("show", JS_GLOBAL_FNS_SHOW),
        ("load", JS_GLOBAL_FNS_LOAD),
        ("fic", JS_GLOBAL_FNS_FIC),
    ]
    for keyword, js in pairs:
        fns = js_list(page, js)
        if fns:
            print("[STAGE2] Global functions containing '" + keyword + "': " + str(fns))

    js_vars = js_list(page, JS_LARGE_GLOBALS)
    print("[STAGE2] Large JS objects/arrays on window: " + str(js_vars))


# ---------------------------------------------------------------------------
# Stage 3
# ---------------------------------------------------------------------------

def dump_stage3(page):
    """Attempts the pagination fallback and dumps results."""
    print("\n" + "=" * 60)
    print("[STAGE3] === Pagination fallback attempt ===")
    print("=" * 60)

    current_count = js_int(page, JS_TOC_COUNT)
    print("[STAGE3] Current li.toc_w count: " + str(current_count))

    has_show_chapters = js_bool(page, JS_SHOW_CHAPTERS_EXISTS)
    print("[STAGE3] select#show_chapters exists: " + str(has_show_chapters))

    page_texts = js_list(page, JS_PAGINATION_TEXTS)
    print("[STAGE3] Available page link texts: " + str(page_texts))

    pagination_html = js_str(page, JS_PAGINATION_HTML, 600)
    print("[STAGE3] Pagination bar HTML: " + pagination_html)

    print("[STAGE3] Attempting to click page 2...")
    clicked = js_bool(page, JS_CLICK_PAGE_2)
    print("[STAGE3] Page 2 click result: " + ("clicked" if clicked else "NOT FOUND"))

    if clicked:
        print("[STAGE3] Waiting 3s after click...")
        time.sleep(3)
        after_click_count = js_int(page, JS_TOC_COUNT)
        print("[STAGE3] li.toc_w count after click: " + str(after_click_count))
        print("[STAGE3] Active page indicator text: " + js_str(page, JS_ACTIVE_PAGE, 50))
        print("[STAGE3] TOC container HTML after page 2: " + js_str(page, JS_TOC_HTML, 500))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python debug_scribblehub.py <url>")
        print("Example:")
        print("  python debug_scribblehub.py https://www.scribblehub.com/series/1857436/...")
        sys.exit(1)

    url = sys.argv[1]
    print("Target URL: " + url)
    print("Timestamp: " + datetime.now().isoformat())

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
        )
        page = context.new_page()

        if _STEALTH:
            stealth_sync(page)
            print("Stealth patches applied.")

        print("\nNavigating to: " + url)
        page.goto(url, wait_until="load", timeout=60_000)
        print("Page loaded. Waiting 3s for JS to settle...")
        time.sleep(3)

        # Stage 1
        dump_stage1(page)
        save_html(page, "debug_sh_stage1.html")

        # Read chapter count from badge
        chapter_count = None
        try:
            cnt_text = page.evaluate(JS_CHAPTER_BADGE)
            if cnt_text:
                chapter_count = int(cnt_text.replace(",", ""))
                print("\n[INFO] Chapter badge count: " + str(chapter_count))
        except Exception:
            pass

        # Stage 2
        fn_defined = js_bool(page, JS_FN_DEFINED)
        if fn_defined:
            dump_stage2_function_found(page, chapter_count)
        else:
            dump_stage2_function_missing(page)
        save_html(page, "debug_sh_stage2.html")

        # Stage 3
        dump_stage3(page)
        save_html(page, "debug_sh_stage3.html")

        print("\n" + "=" * 60)
        print("Debug complete. Browser stays open for 10 seconds.")
        print("=" * 60)
        time.sleep(10)

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
