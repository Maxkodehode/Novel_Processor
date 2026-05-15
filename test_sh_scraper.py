#!/usr/bin/env python
"""Test script to run ScribbleHub scraper on a 123-chapter novel."""
import json
import logging
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

from init_db import create_pure_schema
from core import DatabaseManager, NovelRepository, NetworkClient
from services import BrowserService, CoverManager, ScraperService

URL = "https://www.scribblehub.com/series/1711080/gray-tale-a-star-wars-rebels-story/"

logger.info("Creating DB schema...")
create_pure_schema()

logger.info("Initializing services...")
db_manager = DatabaseManager()
repository = NovelRepository(db_manager)
network_client = NetworkClient()
browser_service = BrowserService()
cover_manager = CoverManager(network_client, repository)
scraper = ScraperService(network_client, browser_service, repository, cover_manager)

logger.info(f"Scraping: {URL}")
start = time.time()

with browser_service:
    data = scraper.scrape_novel(url=URL, save_html="page.html")

elapsed = time.time() - start

if not data or not data.get("title"):
    logger.error("Scrape returned no usable data!")
    sys.exit(1)

chapters = data.get("chapters", [])
logger.info(f"Scraped: '{data['title']}' — {len(chapters)} chapters in {elapsed:.1f}s")

# Save JSON
with open("output.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
logger.info("JSON saved to output.json")

# Print chapter summary
expected = data.get("chapter_count", "?")
logger.info(f"Expected: {expected} chapters, Got: {len(chapters)} chapters")
if len(chapters) == expected:
    logger.info("SUCCESS: All chapters collected!")
else:
    logger.warning(f"MISMATCH: Missing {expected - len(chapters)} chapters")

# Print first and last few chapters
for ch in chapters[:3]:
    logger.info(f"  Ch {ch['order']}: {ch['title'][:60]}")
logger.info("  ...")
for ch in chapters[-3:]:
    logger.info(f"  Ch {ch['order']}: {ch['title'][:60]}")
