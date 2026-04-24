import logging
import random
import time
from bs4 import BeautifulSoup
from adapters import get_adapter
from core.network import NetworkClient
from core.database import NovelRepository
from core.config import FETCH_DELAY
from services.scraper_service import ScraperService

logger = logging.getLogger(__name__)


class NovelUpdateService:
    def __init__(
        self,
        network_client: NetworkClient,
        repository: NovelRepository,
        scraper_service: ScraperService,
    ):
        self.network = network_client
        self.repository = repository
        self.scraper = scraper_service

    def sync_all(self):
        """Orchestrates the sync process for all active novels."""
        novels = self.repository.get_active_novels()
        logger.info(f"Starting sync for {len(novels)} active novels...")

        for novel_id, title, url, last_updated in novels:
            try:
                logger.info(f"Checking updates for: {title}")
                self.sync_novel(novel_id, url)

                # Randomized sleep between novels to avoid rate limiting
                delay = random.uniform(FETCH_DELAY, FETCH_DELAY * 1.5)
                time.sleep(delay)

            except Exception as e:
                logger.error(f"Failed to sync '{title}': {e}", exc_info=True)

    def sync_novel(self, novel_id: int, url: str):
        """Syncs a single novel by comparing chapter lists."""
        time.sleep(FETCH_DELAY)

        adapter = get_adapter(url)

        # 1. Fetch current data from source
        response = self.network.get(url)
        soup = BeautifulSoup(response.text, "html.parser")
        source_data = adapter.parse(soup, url)

        source_chapters = source_data.get("chapters", [])
        if not source_chapters:
            logger.warning(f"No chapters found for {url}")
            return

        # 2. Get existing chapters from DB
        db_chapters = self.repository.get_novel_chapters(novel_id)

        new_chapters = []
        updated_count = 0

        # 3. Compare and identify changes
        for source_ch in source_chapters:
            order = source_ch["order"]
            source_url = source_ch["url"]

            if order in db_chapters:
                # Check if URL changed
                if db_chapters[order]["url"] != source_url:
                    logger.info(f"URL changed for chapter {order}: {source_url}")
                    new_chapters.append(source_ch)
                    updated_count += 1
            else:
                # New chapter
                logger.info(
                    f"New chapter found at order {order}: {source_ch.get('title')}"
                )
                new_chapters.append(source_ch)
                updated_count += 1

        # 4. Perform updates if needed
        if new_chapters:
            logger.info(
                f"Syncing {len(new_chapters)} changes/new chapters for novel {novel_id}"
            )
            self.repository.upsert_chapters(novel_id, new_chapters)
            self.repository.update_novel_timestamp(novel_id)
            logger.info(f"Successfully updated '{source_data['title']}'")
        else:
            logger.info(f"No changes for '{source_data['title']}'")
