import logging
import os
import time
import hashlib
from bs4 import BeautifulSoup
from adapters import get_adapter
from core.network import NetworkClient
from core.database import NovelRepository
from core.config import FETCH_DELAY, TIMEOUT, FETCH_MAX_RETRIES
from core.run_logger import RunLogger
from services import BrowserService, CoverManager
from utils import slugify

logger = logging.getLogger(__name__)


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
        from adapters.scribblehub import ScribbleHubAdapter

        adapter = get_adapter(url)
        logger.info(f"Using adapter: {type(adapter).__name__}")

        html = None
        if use_local and os.path.exists(use_local):
            with open(use_local, "r", encoding="utf-8") as f:
                html = f.read()

        if not html and isinstance(adapter, ScribbleHubAdapter):
            logger.info(f"Forcing Playwright for ScribbleHub: {url}")
            html, pw_page = self.browser.get_page_content(url)
            adapter._pw_page = pw_page
            try:
                soup = BeautifulSoup(html, "html.parser")
                data = adapter.parse(soup, url)
                return data
            finally:
                adapter._pw_page = None

        if not html:
            logger.info(f"Attempting fast fetch: {url}")
            try:
                response = self.network.get(url)
                if response.status_code == 200:
                    html = response.text
            except Exception as e:
                logger.warning(f"Fast fetch failed: {e}. Falling back to Browser...")

        if not html:
            html, pw_page = self.browser.get_page_content(url)
            adapter._pw_page = pw_page
            if save_html:
                with open(save_html, "w", encoding="utf-8") as f:
                    f.write(html)
                logger.info(f"Saved raw HTML to: {save_html}")

        if not html:
            logger.error(f"Failed to get content for {url}")
            return None

        try:
            soup = BeautifulSoup(html, "html.parser")
            data = adapter.parse(soup, url)
            return data
        finally:
            adapter._pw_page = None

    def populate_novel(self, data: dict, metadata_only: bool = False) -> int | None:
        slug = data.get("slug") or slugify(data["title"])
        novel_id = self.repository.upsert_novel(data, slug)
        if novel_id:
            if not metadata_only:
                self.repository.upsert_chapters(novel_id, data.get("chapters", []))

            self.repository.link_tags(novel_id, data.get("tags", []))

            # Download cover
            cover_url = data.get("cover_url")
            if cover_url:
                self.cover_manager.download_and_save(cover_url, novel_id, slug)

        if novel_id and metadata_only:
            self.repository.update_content_status(novel_id, "metadata")

        return novel_id

    def refresh_metadata(self, novel_id: int) -> bool:
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

                for attempt in range(
                    1, FETCH_MAX_RETRIES + 2
                ):  # +1 for initial try, then retries
                    try:
                        logger.info(f"Fetching: {title} (Attempt {attempt})")
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

                        # Memory cleanup
                        del soup
                        del response
                        del content_data
                        break

                    except Exception as e:
                        error_msg = str(e)
                        if attempt <= FETCH_MAX_RETRIES:
                            logger.warning(f"Retry {attempt} for {title}: {error_msg}")
                            log.retry(ch_id, title, attempt, error_msg)
                            # Exponential backoff: 5s, 15s
                            backoff = 5 if attempt == 1 else 15
                            time.sleep(backoff)
                        else:
                            logger.error(
                                f"Failed to fetch {title} after {attempt} attempts: {error_msg}"
                            )
                            log.fail(ch_id, title, error_msg)

                if not success:
                    # Final attempt failed
                    pass

                time.sleep(FETCH_DELAY)
