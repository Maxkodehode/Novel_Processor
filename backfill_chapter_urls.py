# =============================================================================
# backfill_chapter_urls.py
#
# PURPOSE:
#   Finds all novels in the DB that have no chapter rows at all (i.e. the
#   discovery pipeline ran before the chapter-URL fix was applied) and re-scrapes
#   each novel's landing page to populate chapter titles and URLs.
#
#   This does NOT download chapter content — it only fills in the chapter list
#   (titles + URLs) that should have been saved during discovery. After running
#   this script, you can use the reader UI's "Download Chapters" button or
#   run sync_novels.py --fetch-content to get the actual text.
#
# USAGE:
#   python backfill_chapter_urls.py            # backfill all novels with 0 chapters
#   python backfill_chapter_urls.py --dry-run  # just show which novels would be fixed
#   python backfill_chapter_urls.py --id 42    # backfill a single novel by DB id
#
# SAFE TO RE-RUN:
#   upsert_chapters() uses ON CONFLICT(chapter_url) DO UPDATE, so running this
#   multiple times will not create duplicate chapters.
# =============================================================================

import argparse
import logging
import random
import sys
import time

from core import DatabaseManager, NetworkClient, NovelRepository
from core.config import DISCOVERY_NOVEL_DELAY_MIN, DISCOVERY_NOVEL_DELAY_MAX
from services import BrowserService, CoverManager, ScraperService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

DEBUG = False


def get_novels_missing_chapters(db_manager: DatabaseManager) -> list[tuple]:
    """
    Returns all novels that have zero chapter rows in the chapters table.

    Parameters:
        db_manager (DatabaseManager): Active DB manager instance.

    Returns:
        list[tuple]: List of (id, title, source_url) for novels with no chapters.

    Called by: main()
    Depends on: DatabaseManager.execute()
    """
    query = """
            SELECT n.id, n.title, n.source_url
            FROM novels n
            WHERE n.source_url IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM chapters c WHERE c.novel_id = n.id
            )
            ORDER BY n.id ASC \
            """
    rows = db_manager.execute(query)
    return rows


def get_single_novel(db_manager: DatabaseManager, novel_id: int) -> tuple | None:
    """
    Returns (id, title, source_url) for a single novel by ID.

    Parameters:
        db_manager (DatabaseManager): Active DB manager instance.
        novel_id (int): The DB id of the novel to look up.

    Returns:
        tuple | None: (id, title, source_url) or None if not found.

    Called by: main()
    Depends on: DatabaseManager.execute()
    """
    rows = db_manager.execute(
        "SELECT id, title, source_url FROM novels WHERE id = ?", (novel_id,)
    )
    return rows[0] if rows else None


def backfill_novel(
    novel_id: int,
    title: str,
    source_url: str,
    scraper: ScraperService,
    repo: NovelRepository,
) -> bool:
    """
    Re-scrapes a single novel's landing page and saves chapter titles + URLs.

    Does not download chapter text content. Sets content_status back to
    'metadata' after saving chapters so the reader UI stays consistent.

    Parameters:
        novel_id (int): DB id of the novel.
        title (str): Novel title (for logging only).
        source_url (str): The novel's landing page URL to re-scrape.
        scraper (ScraperService): Initialised scraper service.
        repo (NovelRepository): Initialised repository.

    Returns:
        bool: True if chapters were successfully saved, False on any error.

    Called by: main()
    Depends on: ScraperService.scrape_novel(), NovelRepository.upsert_chapters(),
                NovelRepository.update_content_status()
    """
    logger.info(f"  Scraping: {source_url}")
    try:
        data = scraper.scrape_novel(source_url)
    except Exception as e:
        logger.error(f"  scrape_novel() raised: {e}")
        return False

    if not data:
        logger.warning(f"  scrape_novel() returned no data for '{title}'")
        return False

    chapters = data.get("chapters", [])
    if not chapters:
        logger.warning(f"  Scrape succeeded but found 0 chapters for '{title}'")
        return False

    if DEBUG:
        logger.debug(f"  [backfill_novel] {len(chapters)} chapters scraped")
        for ch in chapters[:3]:
            logger.debug(
                f"    order={ch['order']} title='{ch['title']}' url={ch['url']}"
            )

    try:
        repo.upsert_chapters(novel_id, chapters)
        repo.update_content_status(novel_id, "metadata")
        logger.info(f"  Saved {len(chapters)} chapters for '{title}'")
        return True
    except Exception as e:
        logger.error(f"  upsert_chapters() raised: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Backfill chapter titles and URLs for novels that have none."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List affected novels without making any changes",
    )
    parser.add_argument(
        "--id",
        type=int,
        default=None,
        metavar="NOVEL_ID",
        help="Backfill a single novel by its DB id instead of all missing ones",
    )
    args = parser.parse_args()

    # --- Initialise infrastructure ---
    db_manager = DatabaseManager()
    repo = NovelRepository(db_manager)
    network = NetworkClient()
    browser = BrowserService()
    cover_manager = CoverManager(network, repo)
    scraper = ScraperService(network, browser, repo, cover_manager)

    # --- Find target novels ---
    if args.id is not None:
        row = get_single_novel(db_manager, args.id)
        if not row:
            logger.error(f"No novel found with id={args.id}")
            sys.exit(1)
        targets = [row]
    else:
        targets = get_novels_missing_chapters(db_manager)

    if not targets:
        logger.info("No novels found that are missing chapters. Nothing to do.")
        sys.exit(0)

    logger.info(f"Found {len(targets)} novel(s) with no chapter rows:")
    for novel_id, title, source_url in targets:
        logger.info(f"  [{novel_id}] {title}  ({source_url})")

    if args.dry_run:
        logger.info("--dry-run: no changes made.")
        sys.exit(0)

    # --- Backfill each novel ---
    ok_count = 0
    fail_count = 0

    for i, (novel_id, title, source_url) in enumerate(targets):
        logger.info(f"[{i + 1}/{len(targets)}] Processing: '{title}' (id={novel_id})")

        success = backfill_novel(novel_id, title, source_url, scraper, repo)

        if success:
            ok_count += 1
        else:
            fail_count += 1

        # Rate-limited delay between novels (skip after the last one)
        if i < len(targets) - 1:
            delay = random.uniform(DISCOVERY_NOVEL_DELAY_MIN, DISCOVERY_NOVEL_DELAY_MAX)
            logger.info(f"  Waiting {delay:.1f}s before next novel...")
            time.sleep(delay)

    logger.info("=" * 50)
    logger.info(f"Backfill complete — OK: {ok_count}  Failed: {fail_count}")
    if fail_count > 0:
        logger.info("Re-run the script to retry failed novels (safe to re-run).")


if __name__ == "__main__":
    main()
