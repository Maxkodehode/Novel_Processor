"""
Test: check what JS loads on ?toc=2 vs base page, and try the show_chapters dropdown approach.
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

        # Load base page
        print("[1] Loading base page...")
        page.goto(base_url, wait_until="load", timeout=60000)
        time.sleep(3)

        # Check what JS globals are available
        js_check = page.evaluate("""JSON.stringify({
            jQuery: typeof jQuery !== 'undefined' ? jQuery.fn.jquery : 'NOT LOADED',
            $: typeof $ !== 'undefined' ? 'defined' : 'NOT DEFINED',
            simplePagination: typeof $.fn.simplePagination !== 'undefined',
            toc_fic_show_all: typeof toc_fic_show_all !== 'undefined',
            ajaxurl: typeof ajaxurl !== 'undefined' ? ajaxurl : 'NOT DEFINED',
        })""")
        print(f"  JS globals: {js_check}")

        # Check the show_chapters dropdown
        show_chapters = page.evaluate("""JSON.stringify({
            exists: !!document.querySelector('select#show_chapters'),
            value: document.querySelector('select#show_chapters')?.value,
            options: [...(document.querySelector('select#show_chapters')?.options || [])].map(o => ({value: o.value, text: o.text})),
        })""")
        print(f"  show_chapters: {show_chapters}")

        # Try changing the dropdown to 50
        print(f"\n[2] Changing show_chapters dropdown to 50...")
        page.evaluate("""(() => {
            const sel = document.querySelector('select#show_chapters');
            if (sel) {
                sel.value = '50';
                sel.dispatchEvent(new Event('change', {bubbles: true}));
                return 'changed to 50';
            }
            return 'not found';
        })()""")
        time.sleep(5)

        count = page.evaluate("document.querySelectorAll('li.toc_w').length")
        print(f"  Chapters after dropdown change: {count}")

        # Check network requests triggered by dropdown
        print(f"\n[3] Checking if dropdown triggered any network requests...")

        # Try the dropdown with a full page reload approach
        print(f"\n[4] Trying direct navigation with show_chapters parameter...")
        # First go back to base
        page.goto(base_url, wait_until="load", timeout=60000)
        time.sleep(2)

        # Now try navigating to a URL that includes show_chapters
        # The form might submit via GET
        page.goto(f"{base_url}/?show_chapters=50", wait_until="load", timeout=60000)
        time.sleep(3)

        count = page.evaluate("document.querySelectorAll('li.toc_w').length")
        print(f"  Chapters at ?show_chapters=50: {count}")

        # Check the dropdown value
        val = page.evaluate("document.querySelector('select#show_chapters')?.value")
        print(f"  Dropdown value: {val}")

        # Try submitting the form
        print(f"\n[5] Trying form submit...")
        page.goto(base_url, wait_until="load", timeout=60000)
        time.sleep(2)

        # Check if show_chapters is inside a form
        form_info = page.evaluate("""JSON.stringify({
            formExists: !!document.querySelector('select#show_chapters')?.closest('form'),
            formAction: document.querySelector('select#show_chapters')?.closest('form')?.action,
            formMethod: document.querySelector('select#show_chapters')?.closest('form')?.method,
        })""")
        print(f"  Form info: {form_info}")

        # Try: use Playwright to select the option and wait for navigation
        print(f"\n[6] Using Playwright selectOption...")
        from playwright.sync_api import expect

        page.goto(base_url, wait_until="load", timeout=60000)
        time.sleep(2)

        sel_el = page.query_selector("select#show_chapters")
        if sel_el:
            print(f"  Found select element")
            # Get all options
            options = sel_el.query_selector_all("option")
            for opt in options:
                print(f"    option: value={evaluator(opt, 'el => el.value')} text={evaluator(opt, 'el => el.textContent')}")

            # Try selecting 50
            sel_el.select_option("50")
            print(f"  Selected 50, waiting 5s...")
            time.sleep(5)

            count = page.evaluate("document.querySelectorAll('li.toc_w').length")
            print(f"  Chapters after select: {count}")

            # Check URL
            print(f"  Current URL: {page.url}")

        context.close()
        browser.close()


def evaluator(element, expression):
    try:
        return element.evaluate(expression)
    except:
        return "?"


if __name__ == "__main__":
    main()
