import re
import time
import random
import logging
import argparse
from bs4 import BeautifulSoup
from rapidfuzz import fuzz, utils

from core.database import DatabaseManager, NovelRepository
from core.network import NetworkClient
from services.browser_service import BrowserService
from services.cover_manager import CoverManager
from services.scraper_service import ScraperService
from adapters.discovery_adapters import (
    RoyalRoadDiscoveryAdapter,
    ScribbleHubDiscoveryAdapter,
)
from utils.text import slugify

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


class DiscoveryService:
    def __init__(
        self,
        db_manager: DatabaseManager,
        network_client: NetworkClient,
        browser_service: BrowserService,
        scraper_service: ScraperService,
    ):
        self.db = db_manager
        self.repo = NovelRepository(db_manager)
        self.network = network_client
        self.browser = browser_service
        self.scraper = scraper_service
        self.adapters = {
            "royalroad": RoyalRoadDiscoveryAdapter(),
            "scribblehub": ScribbleHubDiscoveryAdapter(),
        }

    def _normalize_title(self, title: str) -> str:
        # Strip bracket tags like [LitRPG], (Complete), etc.
        title = re.sub(r"[\[\(].*?[\]\)]", "", title)
        return utils.default_process(title)

    def discover(self, site: str, start_page: int, end_page: int):
        adapter = self.adapters.get(site)
        if not adapter:
            logger.error(f"No discovery adapter for site: {site}")
            return

        total_new = 0
        total_exact_skipped = 0
        total_fuzzy_merged = 0
        total_errors = 0

        # Load existing novels for fuzzy matching
        existing_novels = self.repo.get_all_novels_for_fuzzy()
        # Pre-process titles for fuzzy matching
        processed_existing = [
            (nid, self._normalize_title(title)) for nid, title in existing_novels
        ]

        for page in range(start_page, end_page + 1):
            logger.info(f"Processing {site} page {page}...")
            url = adapter.get_list_url(page)

            html = None
            try:
                response = self.network.get(url)
                if response.status_code == 200:
                    html = response.text
                else:
                    logger.warning(
                        f"Fast fetch failed with status {response.status_code}. Trying browser..."
                    )
            except Exception as e:
                logger.warning(f"Fast fetch failed: {e}. Trying browser...")

            if not html:
                try:
                    html, _ = self.browser.get_page_content(url)
                except Exception as e:
                    logger.error(f"Browser fetch failed for {url}: {e}")
                    total_errors += 1
                    continue

            if not html:
                logger.error(f"Failed to fetch {url}")
                total_errors += 1
                continue

            soup = BeautifulSoup(html, "html.parser")
            found_novels = adapter.parse_list_page(soup)

            page_new = 0
            page_exact_skipped = 0
            page_fuzzy_merged = 0

            for novel in found_novels:
                title = novel["title"]
                source_url = novel["url"]

                # Tier 1: Exact URL match
                if self.repo.is_url_known(source_url):
                    page_exact_skipped += 1
                    continue

                # Tier 2: Fuzzy title match
                norm_title = self._normalize_title(title)
                match_found = False
                for nid, ex_norm in processed_existing:
                    if fuzz.ratio(norm_title, ex_norm) >= 95.0:
                        logger.info(
                            f"Fuzzy match found: '{title}' matches existing novel ID {nid}. Adding source URL."
                        )
                        self.repo.add_novel_source(nid, site, source_url)
                        page_fuzzy_merged += 1
                        match_found = True
                        break

                if match_found:
                    continue

                # New novel
                try:
                    novel_id = self.repo.insert_discovered_novel(
                        title, source_url, slugify(title)
                    )
                    logger.info(
                        f"Inserted discovered novel: '{title}' (ID: {novel_id})"
                    )

                    # Hydrate metadata
                    logger.info(f"Hydrating metadata for '{title}'...")
                    scrape_data = self.scraper.scrape_novel(source_url)
                    if scrape_data:
                        self.scraper.populate_novel(scrape_data, metadata_only=True)
                        logger.info(f"Metadata hydrated for '{title}'.")
                    else:
                        logger.warning(f"Failed to hydrate metadata for '{title}'.")

                    # Add to fuzzy list for subsequent matches in the same run
                    processed_existing.append((novel_id, norm_title))
                    page_new += 1
                except Exception as e:
                    logger.error(f"Error inserting novel '{title}': {e}")
                    total_errors += 1

            total_new += page_new
            total_exact_skipped += page_exact_skipped
            total_fuzzy_merged += page_fuzzy_merged

            logger.info(
                f"Page {page} Summary: {page_new} new, {page_exact_skipped} exact skipped, {page_fuzzy_merged} fuzzy merged."
            )

            if page < end_page:
                delay = random.uniform(2, 5)
                time.sleep(delay)

        logger.info("Discovery Run Final Summary:")
        logger.info(f"New novels inserted: {total_new}")
        logger.info(f"Exact duplicates skipped: {total_exact_skipped}")
        logger.info(f"Fuzzy/cross-platform merges: {total_fuzzy_merged}")
        logger.info(f"Errors: {total_errors}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Mass Discovery Pipeline for Novel_Processor"
    )
    parser.add_argument(
        "--site",
        choices=["royalroad", "scribblehub"],
        required=True,
        help="Site to discover from",
    )
    parser.add_argument("--start", type=int, default=1, help="Start page")
    parser.add_argument("--end", type=int, default=50, help="End page")

    args = parser.parse_args()

    db_manager = DatabaseManager()
    network = NetworkClient()
    browser = BrowserService()
    repo = NovelRepository(db_manager)
    cover = CoverManager(network, repo)
    scraper = ScraperService(network, browser, repo, cover)

    service = DiscoveryService(db_manager, network, browser, scraper)

    try:
        service.discover(args.site, args.start, args.end)
    finally:
        browser.stop()
