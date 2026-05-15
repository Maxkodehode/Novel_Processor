#!/usr/bin/env python
"""Test ScribbleHub scraper on a 123-chapter novel."""
import sys
import os

# Write output to file directly, bypassing any shell redirection issues
log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_output.log")
log_file = open(log_path, "w", buffering=1)

def log(msg):
    line = f"{msg}\n"
    log_file.write(line)
    log_file.flush()
    # Also try stdout in case it works
    try:
        sys.stdout.write(line)
        sys.stdout.flush()
    except:
        pass

log("=== ScribbleHub Scraper Test ===")
log(f"PID: {os.getpid()}")

import logging
import json
import time

# Set up logging to file
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(log_file), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

log("Importing modules...")
from init_db import create_pure_schema
from core import DatabaseManager, NovelRepository, NetworkClient
from services import BrowserService, CoverManager, ScraperService
log("Imports done")

URL = "https://www.scribblehub.com/series/1711080/gray-tale-a-star-wars-rebels-story/"

log("Creating DB schema...")
create_pure_schema()
log("Initializing services...")
db_manager = DatabaseManager()
repository = NovelRepository(db_manager)
network_client = NetworkClient()
browser_service = BrowserService()
cover_manager = CoverManager(network_client, repository)
scraper = ScraperService(network_client, browser_service, repository, cover_manager)
log("Services initialized")

log(f"Scraping: {URL}")
start = time.time()

with browser_service:
    data = scraper.scrape_novel(url=URL, save_html="page.html")

elapsed = time.time() - start

if not data or not data.get("title"):
    log("ERROR: Scrape returned no usable data!")
    log_file.close()
    sys.exit(1)

chapters = data.get("chapters", [])
log(f"Scraped: '{data['title']}' — {len(chapters)} chapters in {elapsed:.1f}s")
expected = data.get("chapter_count", "?")
log(f"Expected: {expected}, Got: {len(chapters)}")

if len(chapters) == expected:
    log("SUCCESS: All chapters collected!")
else:
    log(f"MISMATCH: Missing {expected - len(chapters)} chapters")

with open("output.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
log("JSON saved to output.json")

for ch in chapters[:3]:
    log(f"  Ch {ch['order']}: {ch['title'][:60]}")
log("  ...")
for ch in chapters[-3:]:
    log(f"  Ch {ch['order']}: {ch['title'][:60]}")

log_file.close()
