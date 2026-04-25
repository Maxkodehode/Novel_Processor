# =============================================================================
# CHANGES:
#   - scrape_novel(): Updated all browser.get_page_content() calls to pass
#     keep_page_open=True only for ScribbleHub (which needs the live page for
#     JS evaluation). All other browser fallbacks pass keep_page_open=False so
#     the page is closed immediately after HTML is captured.
#   - scrape_novel(): ScribbleHub finally block now explicitly closes pw_page
#     since keep_page_open=True means the caller owns the lifecycle.
#   - scrape_novel(): Removed ctx.close() calls — context is now persistent and
#     lives on BrowserService. Closing it here would break subsequent requests.
#   - All other methods unchanged.
# =============================================================================

import hashlib
import logging
import os
import random
import time

from bs4 import BeautifulSoup

from adapters import get_adapter
from core.config import FETCH_DELAY, FETCH_DELAY_JITTER, FETCH_MAX_RETRIES, TIMEOUT
from core.database import NovelRepository
from core.network import NetworkClient
from core.run_logger import RunLogger
from services import BrowserService, CoverManager
from utils import slugify

logger = logging.getLogger(__name__)

DEBUG = False


class ScraperService:
    def __init__(
        self,
        network_client: NetworkClient,
        browser_service: BrowserService,
        repository: NovelRepository,
        cover_manager: CoverManager,
    ):
        self.network = network_client
        self.browser = browser_service
        self.repository = repository
        self.cover_manager = cover_manager

    def scrape_novel(
        self, url: str, use_local: str = None, save_html: str = None
    ) -> dict | None:
        """
        Fetches and parses a novel landing page.

        For ScribbleHub, always uses Playwright with keep_page_open=True so the
        adapter can call JS functions on the live page. The page is explicitly
        closed in a finally block here after the adapter is done with it.
        For all other sites, tries fast network fetch first with Playwright as
        fallback. Playwright fallback uses keep_page_open=False so the page is
        closed inside get_page_content() immediately after HTML capture.

        Parameters:
            url (str): The novel's landing page URL.
            use_local (str): Path to a local HTML file to use instead of fetching.
            save_html (str): If set, saves the raw fetched HTML to this path.

        Returns:
            dict | None: Parsed novel data, or None on failure.

        Called by: main.py, discovery_service.py, refresh_metadata()
        Depends on: get_adapter(), NetworkClient.get(), BrowserService.get_page_content()
        """
        from adapters.scribblehub import ScribbleHubAdapter

        adapter = get_adapter(url)
        logger.info(f"Using adapter: {type(adapter).__name__}")
        if DEBUG:
            logger.debug(f"[scrape_novel] url={url} use_local={use_local}")

        # --- Local file mode (dev/debug) ---
        if use_local and os.path.exists(use_local):
            with open(use_local, "r", encoding="utf-8") as f:
                html = f.read()
            soup = BeautifulSoup(html, "html.parser")
            return adapter.parse(soup, url)

        # --- ScribbleHub: always Playwright, keep page open for JS evaluation ---
        if isinstance(adapter, ScribbleHubAdapter):
            logger.info(f"[SH] Forcing Playwright for ScribbleHub: {url}")
            html, pw_page = self.browser.get_page_content(url, keep_page_open=True)
            adapter._pw_page = pw_page
            try:
                soup = BeautifulSoup(html, "html.parser")
                data = adapter.parse(soup, url)
                return data
            except Exception as e:
                logger.error(f"Failed to parse ScribbleHub novel {url}: {e}")
                return None
            finally:
                adapter._pw_page = None
                # We own this page — close it now that the adapter is done
                if pw_page:
                    try:
                        pw_page.close()
                    except Exception:
                        pass

        # --- All other sites: try fast network fetch first ---
        html = None

        logger.info(f"Attempting fast fetch: {url}")
        try:
            response = self.network.get(url)
            if response.status_code == 200:
                html = response.text
            else:
                logger.warning(
                    f"Fast fetch returned HTTP {response.status_code}, trying browser..."
                )
        except Exception as e:
            logger.warning(f"Fast fetch failed: {e}. Trying browser...")

        # --- Playwright fallback for non-ScribbleHub sites ---
        if not html:
            try:
                # keep_page_open=False — we only need the HTML, page closes inside
                html, _ = self.browser.get_page_content(url, keep_page_open=False)
            except Exception as e:
                logger.error(f"Browser fetch also failed for {url}: {e}")
                return None

        if not html:
            logger.error(f"Failed to get any content for {url}")
            return None

        if save_html:
            with open(save_html, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info(f"Saved raw HTML to: {save_html}")

        try:
            soup = BeautifulSoup(html, "html.parser")
            return adapter.parse(soup, url)
        except Exception as e:
            logger.error(f"Failed to parse novel {url}: {e}")
            return None

    def populate_novel(self, data: dict, metadata_only: bool = False) -> int | None:
        """
        Inserts or updates a novel and its chapters/tags in the database.

        Parameters:
            data (dict): Parsed novel data from scrape_novel().
            metadata_only (bool): If True, skips chapter upsert and marks
                                  content_status as 'metadata'. Used by
                                  discovery runs where chapter content is not
                                  yet downloaded.

        Returns:
            int | None: The novel's database ID, or None on failure.

        Called by: main.py, discovery_service.py
        Depends on: NovelRepository, CoverManager
        """
        slug = data.get("slug") or slugify(data["title"])
        novel_id = self.repository.upsert_novel(data, slug)

        if novel_id:
            if not metadata_only:
                self.repository.upsert_chapters(novel_id, data.get("chapters", []))

            self.repository.link_tags(novel_id, data.get("tags", []))

            cover_url = data.get("cover_url")
            if cover_url:
                self.cover_manager.download_and_save(cover_url, novel_id, slug)

        if novel_id and metadata_only:
            self.repository.update_content_status(novel_id, "metadata")

        return novel_id

    def refresh_metadata(self, novel_id: int) -> bool:
        """
        Re-scrapes and updates metadata for a novel already in the database.

        Parameters:
            novel_id (int): The database ID of the novel to refresh.

        Returns:
            bool: True if refresh succeeded, False otherwise.

        Called by: reader API, server.run_background_fetch()
        Depends on: scrape_novel(), populate_novel()
        """
        rows = self.repository.db.execute(
            "SELECT source_url FROM novels WHERE id = ?", (novel_id,)
        )
        if not rows:
            logger.warning(f"Metadata refresh: Novel {novel_id} not found in DB")
            return False

        url = rows[0][0]
        if not url:
            logger.warning(f"Metadata refresh: No source_url for novel {novel_id}")
            return False

        logger.info(f"Refreshing metadata for novel {novel_id}: {url}")
        data = self.scrape_novel(url)
        if not data:
            logger.warning(f"Metadata refresh: Failed to scrape {url}")
            return False

        self.populate_novel(data, metadata_only=True)
        return True

    def fetch_chapters(self, novel_id: int = None):
        """
        Downloads plain text + HTML content for all pending (unfetched) chapters.

        Applies a jittered sleep between each chapter to avoid rate-limiting.
        Retries up to FETCH_MAX_RETRIES times with exponential backoff on failure.

        Parameters:
            novel_id (int | None): If set, only fetches chapters for this novel.
                                   If None, fetches all pending chapters globally.

        Returns:
            None

        Called by: main.py, sync_novels.py, backfill_chapters.py
        Depends on: NovelRepository.get_pending_chapters(),
                    NovelRepository.update_chapter_content(),
                    get_adapter(), NetworkClient.get(), RunLogger
        """
        tasks = self.repository.get_pending_chapters(novel_id)
        if not tasks:
            logger.info("All chapters are up to date.")
            return

        logger.info(f"Starting fetch for {len(tasks)} chapters...")

        with RunLogger(total_pending=len(tasks)) as log:
            for ch_id, title, url in tasks:
                start_time = time.time()
                success = False
                error_msg = ""

                for attempt in range(1, FETCH_MAX_RETRIES + 2):
                    try:
                        logger.info(f"Fetching: {title} (Attempt {attempt})")
                        if DEBUG:
                            logger.debug(f"[fetch_chapters] ch_id={ch_id} url={url}")

                        adapter = get_adapter(url)
                        response = self.network.get(url, timeout=TIMEOUT)

                        if response.status_code != 200:
                            raise Exception(f"HTTP {response.status_code}")

                        soup = BeautifulSoup(response.text, "html.parser")
                        content_data = adapter.parse_chapter_content(soup)

                        if not content_data or "plain_text" not in content_data:
                            raise Exception("Invalid content parsed")

                        content_text = content_data["plain_text"]
                        raw_html = content_data.get("raw_html", "")
                        chapter_hash = hashlib.sha256(
                            content_text.encode("utf-8")
                        ).hexdigest()

                        self.repository.update_chapter_content(
                            ch_id, content_text, raw_html, chapter_hash
                        )

                        elapsed = time.time() - start_time
                        word_count = len(content_text.split())
                        log.ok(ch_id, title, word_count, elapsed)
                        logger.info(f"Saved '{title}'.")
                        success = True
                        break

                    except Exception as e:
                        error_msg = str(e)
                        if attempt <= FETCH_MAX_RETRIES:
                            backoff = 5 if attempt == 1 else 15
                            logger.warning(
                                f"Retry {attempt} for '{title}': {error_msg} "
                                f"— waiting {backoff}s"
                            )
                            log.retry(ch_id, title, attempt, error_msg)
                            time.sleep(backoff)
                        else:
                            logger.error(
                                f"Failed to fetch '{title}' after {attempt} attempts: "
                                f"{error_msg}"
                            )
                            log.fail(ch_id, title, error_msg)

                # Jittered sleep between chapters — never a predictable fixed interval
                jittered_delay = random.uniform(
                    FETCH_DELAY, FETCH_DELAY + FETCH_DELAY_JITTER
                )
                if DEBUG:
                    logger.debug(
                        f"[fetch_chapters] sleeping {jittered_delay:.1f}s before next"
                    )
                time.sleep(jittered_delay)
