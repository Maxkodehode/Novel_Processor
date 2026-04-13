"""
main.py — Novel scraper pipeline orchestrator

Usage:
    # Full pipeline (scrape → populate DB → fetch chapter content)
    python main.py --url https://www.royalroad.com/fiction/12345/some-novel

    # Scrape and populate only (skip chapter content fetching)
    python main.py --url https://www.royalroad.com/fiction/12345/some-novel --no-fetch

    # Save a debug copy of the raw HTML and parsed JSON
    python main.py --url https://www.royalroad.com/fiction/12345/some-novel --debug

    # Use a locally saved HTML file instead of fetching (dev mode)
    python main.py --url https://www.royalroad.com/fiction/12345/some-novel --use-local page.html
"""

import argparse
import json
import logging
import sys

from init_db import create_pure_schema
from scraper_engine import scrape
from populate_metadata import populate
from fetch_content import worker as fetch_chapters

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Novel scraper pipeline")
    parser.add_argument("--url", required=True, help="Novel landing page URL")
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="Skip chapter content fetching after metadata insert",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Save raw HTML (page.html) and parsed JSON (output.json) for inspection",
    )
    parser.add_argument(
        "--use-local",
        metavar="FILE",
        default=None,
        help="Load HTML from a local file instead of fetching (dev mode)",
    )
    args = parser.parse_args()

    # ── Step 1: Ensure DB schema exists ──────────────────────────────────────
    logger.info("Initialising database schema...")
    create_pure_schema()

    # ── Step 2: Scrape the novel landing page ────────────────────────────────
    logger.info(f"Scraping: {args.url}")
    save_html = "page.html" if args.debug else None

    data = scrape(
        url=args.url,
        use_local=args.use_local,
        save_html=save_html,
        # novel_id is not known yet — cover download happens after populate()
    )

    if not data or not data.get("title"):
        logger.error("Scrape returned no usable data. Check the URL or adapter.")
        sys.exit(1)

    logger.info(
        f"Scraped: '{data['title']}' — {len(data.get('chapters', []))} chapters found"
    )

    if args.debug:
        with open("output.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("Debug JSON saved to output.json")

    # ── Step 3: Populate DB and get the novel_id ─────────────────────────────
    logger.info("Inserting metadata into database...")
    novel_id = populate(data)

    if novel_id is None:
        logger.error("DB populate failed — aborting.")
        sys.exit(1)

    # ── Step 4: Download cover now that we have the novel_id ─────────────────
    cover_url = data.get("cover_url")
    if cover_url:
        from scraper_engine import download_cover, save_cover_to_db

        slug = data.get("slug") or f"novel_{novel_id}"
        cover_path = download_cover(cover_url, novel_id, slug)
        if cover_path:
            save_cover_to_db(novel_id, cover_path)
    else:
        logger.warning("No cover URL found for this novel.")

    # ── Step 5: Fetch chapter content ────────────────────────────────────────
    if args.no_fetch:
        logger.info("--no-fetch set: skipping chapter content fetching.")
    else:
        logger.info("Starting chapter content fetch...")
        fetch_chapters()

    logger.info("Pipeline complete.")


if __name__ == "__main__":
    main()
