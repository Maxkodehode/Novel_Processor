import logging
from playwright.sync_api import sync_playwright
from core.config import USER_AGENT, TIMEOUT

logger = logging.getLogger(__name__)


class BrowserService:
    def __init__(self, headless=True):
        self.headless = headless
        self._playwright = None
        self._browser = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def start(self):
        if not self._playwright:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=self.headless)
            logger.info("Playwright browser started.")

    def stop(self):
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
        logger.info("Playwright browser stopped.")

    def get_page_content(self, url, wait_selector=None, timeout=TIMEOUT):
        if not self._browser:
            self.start()

        ctx = self._browser.new_context(user_agent=USER_AGENT)
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=15000)
                except Exception:
                    logger.debug(
                        f"Selector {wait_selector} wait timed out, continuing."
                    )

            content = page.content()
            return content, page
        except Exception as e:
            logger.error(f"Playwright error for {url}: {e}")
            page.close()
            ctx.close()
            raise
        # Note: In some cases we might want to keep the page open for the adapter,
        # but the adapter should probably just take the content or the page object should be managed carefully.
