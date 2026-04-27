# =============================================================================
# CHANGES:
#   - Persistent context: _context is now created once in start() and reused
#     across all get_page_content() calls. Previously a new context was created
#     per request, which discarded cookies/session state every time and made
#     every request look like a brand-new user — a classic bot signal.
#   - Stealth: playwright-stealth is applied to every new page via stealth_sync().
#     This masks navigator.webdriver, canvas fingerprint, and other headless
#     browser artifacts that WAFs check for.
#   - Realistic viewport: context is launched with 1920x1080 instead of the
#     default headless size (often 800x600), which is a known bot indicator.
#   - Resource blocking: images, media, fonts, and stylesheets are blocked by
#     default. These are not needed for HTML scraping and blocking them reduces
#     bandwidth, speeds up page loads, and removes ad/tracking network calls
#     that can trigger "ad-blocker detected" responses. Pass
#     block_resources=False to disable for pages that need full rendering.
#   - Page lifecycle: get_page_content() now always closes the page in a
#     finally block for non-ScribbleHub callers. ScribbleHub adapter needs the
#     live page reference for JS evaluation — caller (scraper_service) is
#     responsible for closing those pages explicitly.
#   - stop(): also closes the persistent context before stopping the browser.
# =============================================================================

import logging
import sys

print(f"DEBUG: Python executable: {sys.executable}")
print(f"DEBUG: sys.path: {sys.path}")
from playwright.sync_api import sync_playwright

# In browser_service.py
# In browser_service.py
try:
    from playwright_stealth import stealth_sync

    _STEALTH_AVAILABLE = True
except Exception as e:
    _STEALTH_AVAILABLE = False
    print(f"DEBUG: Stealth import failed: {e}")

from core.config import USER_AGENT, TIMEOUT

logger = logging.getLogger(__name__)

DEBUG = False

# Resource types to block during scraping — not needed for HTML content
_BLOCKED_RESOURCES = {"image", "media", "font", "stylesheet"}


class BrowserService:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._context = None  # Persistent context — reused across all requests

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def start(self):
        """
        Launches the browser and creates a single persistent context.

        The context is reused for all subsequent get_page_content() calls so
        that cookies and session state are preserved across requests, making
        the scraper look like a returning user rather than a new one each time.

        Called by: __enter__(), get_page_content() (auto-start)
        Depends on: playwright, USER_AGENT
        """
        if self._playwright:
            return  # Already started

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
        )
        logger.info("Playwright browser and persistent context started.")
        if not _STEALTH_AVAILABLE:
            logger.warning(
                "playwright-stealth not installed — navigator.webdriver will be visible. "
                "Run: pip install playwright-stealth"
            )

    def stop(self):
        """
        Closes the persistent context, browser, and Playwright instance.

        Called by: __exit__(), manual teardown
        Depends on: _context, _browser, _playwright
        """
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
        logger.info("Playwright browser stopped.")

    def get_page_content(
        self,
        url: str,
        wait_selector: str = None,
        timeout: int = TIMEOUT,
        block_resources: bool = True,
        keep_page_open: bool = False,
    ) -> tuple[str, object]:
        """
        Fetches a URL using the persistent browser context.

        Applies stealth patches to hide headless browser artifacts. Blocks
        images, media, fonts, and stylesheets by default to reduce bandwidth
        and avoid triggering tracking/ad networks.

        Parameters:
            url (str): The URL to navigate to.
            wait_selector (str | None): Optional CSS selector to wait for after load.
            timeout (int): Navigation timeout in seconds.
            block_resources (bool): If True, block images/media/fonts/CSS.
                                    Set False for pages that need full rendering.
            keep_page_open (bool): If True, the caller is responsible for closing
                                   the returned page. Used by ScribbleHub adapter
                                   which needs the live page for JS evaluation.
                                   If False, the page is closed before returning
                                   and the returned page object must not be used.

        Returns:
            tuple[str, Page]: (html_content, playwright_page). If keep_page_open
                              is False, the page is already closed — only the html
                              string is usable.

        Called by: ScraperService.scrape_novel()
        Depends on: _context, stealth_sync, _BLOCKED_RESOURCES
        """
        if not self._context:
            self.start()

        page = self._context.new_page()

        # Apply stealth patches before any navigation
        if _STEALTH_AVAILABLE:
            stealth_sync(page)
            if DEBUG:
                logger.debug(f"[get_page_content] stealth applied for {url}")

        # Block unnecessary resource types to reduce footprint
        if block_resources:

            def _block_handler(route):
                if route.request.resource_type in _BLOCKED_RESOURCES:
                    route.abort()
                else:
                    route.continue_()

            page.route("**/*", _block_handler)

        try:
            if DEBUG:
                logger.debug(f"[get_page_content] navigating to {url}")

            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)

            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=15_000)
                except Exception:
                    logger.debug(
                        f"Selector '{wait_selector}' wait timed out, continuing."
                    )

            content = page.content()

            if keep_page_open:
                # Caller is responsible for closing this page
                return content, page

            # Close the page now — caller only needs the HTML string
            page.close()
            return content, None

        except Exception as e:
            logger.error(f"Playwright error for {url}: {e}")
            try:
                page.close()
            except Exception:
                pass
            raise
