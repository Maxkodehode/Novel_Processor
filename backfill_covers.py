# =============================================================================
# backfill_covers.py
#
# PURPOSE:
#   Audits every non-ABANDONED novel in the database for a valid cover image
#   and fetches one if any of the following conditions are true:
#     1. cover_path is NULL or empty — cover was never downloaded.
#     2. cover_path points to a file that no longer exists on disk.
#     3. The cover file exists but is smaller than MIN_VALID_COVER_BYTES (1 KB
#        by default) — indicates a failed/placeholder download.
#
#   For novels that need a cover, the script uses the cover_url already stored
#   in the DB. If cover_url is also missing, the novel is skipped unless
#   --re-scrape is passed, in which case the novel landing page is re-scraped
#   to obtain a fresh URL before downloading.
#
# USAGE:
#   python backfill_covers.py                  # fix all novels missing valid covers
#   python backfill_covers.py --dry-run        # preview affected novels, no changes
#   python backfill_covers.py --id 42          # fix a single novel by DB id
#   python backfill_covers.py --re-scrape      # re-scrape landing pages for novels
#                                              # where cover_url is NULL or download fails
#   python backfill_covers.py --min-size 2048  # treat files < 2 KB as invalid
#   python backfill_covers.py --delay-min 4 --delay-max 8  # override inter-novel delay
#
# SAFE TO RE-RUN:
#   CoverManager.download_and_save() always replaces the existing file before
#   writing, so re-running this script is non-destructive.
#
# RATE LIMITING:
#   A jittered sleep of COVER_BACKFILL_DELAY_MIN–MAX seconds is applied between
#   each cover download. An additional COVER_FETCH_DELAY (from config.py) is
#   applied inside CoverManager before each HTTP request. Together these ensure
#   downloads are spaced out enough to avoid triggering CDN rate limits.
# =============================================================================

import argparse
import logging
import os
import random
import sys
import time

from core import DatabaseManager, NetworkClient, NovelRepository
from core.database import NOVEL_STATUS_ABANDONED
from services import BrowserService, CoverManager, ScraperService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

DEBUG = False

# ---------------------------------------------------------------------------
# Configurable defaults (overridable via CLI flags)
# ---------------------------------------------------------------------------

# Files below this size (in bytes) are treated as invalid covers
MIN_VALID_COVER_BYTES = 1024  # 1 KB

# Inter-novel delay range (seconds) — applied between each cover download
# Keep these conservative; CDNs share rate-limit budgets across novels.
COVER_BACKFILL_DELAY_MIN = 5  # seconds
COVER_BACKFILL_DELAY_MAX = 10  # seconds


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def get_all_novels(db_manager: DatabaseManager) -> list[tuple]:
    """
    Returns all non-ABANDONED novels with their cover metadata.

    Parameters:
        db_manager (DatabaseManager): Active DB manager instance.

    Returns:
        list[tuple]: List of (id, title, slug, source_url, cover_path, cover_url).

    Called by: main()
    Depends on: DatabaseManager.execute(), NOVEL_STATUS_ABANDONED
    """
    query = """
            SELECT id, title, slug, source_url, cover_path, cover_url
            FROM novels
            WHERE status != ?
            ORDER BY id ASC \
            """
    return db_manager.execute(query, (NOVEL_STATUS_ABANDONED,))


def get_single_novel(db_manager: DatabaseManager, novel_id: int) -> tuple | None:
    """
    Returns cover metadata for a single novel by DB id.

    Parameters:
        db_manager (DatabaseManager): Active DB manager instance.
        novel_id (int): The DB id of the novel to look up.

    Returns:
        tuple | None: (id, title, slug, source_url, cover_path, cover_url) or None.

    Called by: main()
    Depends on: DatabaseManager.execute()
    """
    rows = db_manager.execute(
        "SELECT id, title, slug, source_url, cover_path, cover_url FROM novels WHERE id = ?",
        (novel_id,),
    )
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# Cover validity check
# ---------------------------------------------------------------------------


def cover_is_valid(cover_path: str | None, min_size: int) -> bool:
    """
    Determines whether a novel's cover file meets validity requirements.

    A cover is considered invalid if:
      - cover_path is None or an empty string.
      - The file at cover_path does not exist on disk.
      - The file exists but its size is below min_size bytes.

    Parameters:
        cover_path (str | None): Relative or absolute path to the cover file.
        min_size (int): Minimum acceptable file size in bytes.

    Returns:
        bool: True if the cover is present and valid, False otherwise.

    Called by: audit_novels()
    Depends on: os.path.exists(), os.path.getsize()
    """
    if not cover_path:
        if DEBUG:
            logger.debug("[cover_is_valid] cover_path is empty — invalid")
        return False

    # Resolve relative paths against the current working directory
    abs_path = cover_path if os.path.isabs(cover_path) else os.path.abspath(cover_path)

    if not os.path.exists(abs_path):
        if DEBUG:
            logger.debug(f"[cover_is_valid] file not found: {abs_path}")
        return False

    size = os.path.getsize(abs_path)
    if size < min_size:
        if DEBUG:
            logger.debug(
                f"[cover_is_valid] file too small: {abs_path} ({size} bytes < {min_size})"
            )
        return False

    return True


# ---------------------------------------------------------------------------
# Per-novel cover fix logic
# ---------------------------------------------------------------------------


def fix_cover(
    novel_id: int,
    title: str,
    slug: str,
    source_url: str | None,
    cover_url: str | None,
    cover_manager: CoverManager,
    scraper: ScraperService | None,
    repo: NovelRepository,
    re_scrape: bool,
    delay_min: float,
    delay_max: float,
) -> str:
    """
    Attempts to download a valid cover for a single novel.

    Strategy:
      1. If cover_url is available, attempt download immediately.
      2. If cover_url is NULL and re_scrape=True, re-scrape the landing page
         to get a fresh cover_url, then attempt download.
      3. If cover_url is NULL and re_scrape=False, skip with a warning.
      4. If the download fails and re_scrape=True, re-scrape and retry once.

    A jittered delay of delay_min–delay_max seconds is applied after each
    download attempt (success or failure) to rate-limit CDN requests.

    Parameters:
        novel_id (int): DB id of the novel.
        title (str): Novel title (for logging).
        slug (str): Novel slug (used in filename by CoverManager).
        source_url (str | None): Novel landing page URL (for re-scraping).
        cover_url (str | None): Current cover_url from the DB.
        cover_manager (CoverManager): Initialized cover manager.
        scraper (ScraperService | None): Initialized scraper (needed for re-scrape).
        repo (NovelRepository): Initialized repository.
        re_scrape (bool): Whether to re-scrape the landing page if cover_url is
                          missing or the download fails.
        delay_min (float): Minimum inter-novel delay in seconds.
        delay_max (float): Maximum inter-novel delay in seconds.

    Returns:
        str: 'ok', 'skipped', or 'failed'.

    Called by: main()
    Depends on: CoverManager.download_and_save(), ScraperService.scrape_novel(),
                NovelRepository.db.execute()
    """
    if DEBUG:
        logger.debug(
            f"[fix_cover] novel_id={novel_id} cover_url={cover_url} "
            f"re_scrape={re_scrape}"
        )

    active_cover_url = cover_url

    # --- Step 1: If no cover_url in DB, optionally re-scrape to get one ---
    if not active_cover_url:
        if not re_scrape:
            logger.warning(
                f"  '{title}' — no cover_url in DB and --re-scrape not set. Skipping."
            )
            return "skipped"

        if not source_url:
            logger.warning(f"  '{title}' — no source_url, cannot re-scrape. Skipping.")
            return "skipped"

        if not scraper:
            logger.warning(
                f"  '{title}' — scraper not available for re-scrape. Skipping."
            )
            return "skipped"

        logger.info(f"  '{title}' — cover_url missing, re-scraping: {source_url}")
        try:
            data = scraper.scrape_novel(source_url)
            if data and data.get("cover_url"):
                active_cover_url = data["cover_url"]
                # Persist the fresh cover_url back to the DB
                repo.db.execute(
                    "UPDATE novels SET cover_url = ? WHERE id = ?",
                    (active_cover_url, novel_id),
                    commit=True,
                )
                logger.info(f"  Updated cover_url for '{title}': {active_cover_url}")
            else:
                logger.warning(
                    f"  Re-scrape for '{title}' returned no cover_url. Skipping."
                )
                return "skipped"
        except Exception as e:
            logger.error(f"  Re-scrape failed for '{title}': {e}")
            return "failed"

    # --- Step 2: Attempt cover download ---
    logger.info(f"  Downloading cover for '{title}' from: {active_cover_url}")
    result_path = None
    try:
        result_path = cover_manager.download_and_save(active_cover_url, novel_id, slug)
    except Exception as e:
        logger.error(f"  cover_manager.download_and_save() raised: {e}")

    # --- Step 3: If download failed and re_scrape is enabled, get a fresh URL ---
    if not result_path and re_scrape and source_url and scraper:
        logger.info(
            f"  Download failed for '{title}', re-scraping for fresh cover_url..."
        )
        try:
            data = scraper.scrape_novel(source_url)
            fresh_url = data.get("cover_url") if data else None
            if fresh_url and fresh_url != active_cover_url:
                # Persist the refreshed URL
                repo.db.execute(
                    "UPDATE novels SET cover_url = ? WHERE id = ?",
                    (fresh_url, novel_id),
                    commit=True,
                )
                logger.info(
                    f"  Retrying with fresh cover_url for '{title}': {fresh_url}"
                )
                result_path = cover_manager.download_and_save(fresh_url, novel_id, slug)
            else:
                logger.warning(
                    f"  Re-scrape did not yield a new cover_url for '{title}'."
                )
        except Exception as e:
            logger.error(f"  Re-scrape retry failed for '{title}': {e}")

    # --- Apply inter-novel rate-limit delay ---
    delay = random.uniform(delay_min, delay_max)
    if DEBUG:
        logger.debug(f"[fix_cover] sleeping {delay:.1f}s after '{title}'")
    time.sleep(delay)

    if result_path:
        logger.info(f"  ✓ Cover saved for '{title}': {result_path}")
        return "ok"
    else:
        logger.warning(f"  ✗ Failed to obtain cover for '{title}'.")
        return "failed"


# ---------------------------------------------------------------------------
# Audit pass — classify all novels
# ---------------------------------------------------------------------------


def audit_novels(
    novels: list[tuple],
    min_size: int,
) -> tuple[list[tuple], list[tuple]]:
    """
    Splits novels into those that need a cover and those that are already valid.

    Parameters:
        novels (list[tuple]): Full list of
            (id, title, slug, source_url, cover_path, cover_url) tuples.
        min_size (int): Minimum valid cover file size in bytes.

    Returns:
        tuple[list[tuple], list[tuple]]:
            (needs_cover, already_valid) — each entry is the original tuple.

    Called by: main()
    Depends on: cover_is_valid()
    """
    needs_cover = []
    already_valid = []

    for row in novels:
        novel_id, title, slug, source_url, cover_path, cover_url = row
        if cover_is_valid(cover_path, min_size):
            already_valid.append(row)
            if DEBUG:
                logger.debug(f"[audit] VALID cover for '{title}' at {cover_path}")
        else:
            reason = _invalid_reason(cover_path, min_size)
            logger.info(f"  Needs cover [{reason}]: '{title}' (id={novel_id})")
            needs_cover.append(row)

    return needs_cover, already_valid


def _invalid_reason(cover_path: str | None, min_size: int) -> str:
    """
    Returns a human-readable reason why a cover is considered invalid.

    Parameters:
        cover_path (str | None): Path to the cover file.
        min_size (int): Minimum valid size in bytes.

    Returns:
        str: Short description of the invalidity reason.

    Called by: audit_novels()
    Depends on: os.path.exists(), os.path.getsize()
    """
    if not cover_path:
        return "no cover_path"
    abs_path = cover_path if os.path.isabs(cover_path) else os.path.abspath(cover_path)
    if not os.path.exists(abs_path):
        return "file missing"
    size = os.path.getsize(abs_path)
    if size < min_size:
        return f"file too small ({size} bytes)"
    return "unknown"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Audit and backfill missing or invalid novel cover images."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List novels that need covers without downloading anything",
    )
    parser.add_argument(
        "--id",
        type=int,
        default=None,
        metavar="NOVEL_ID",
        help="Fix a single novel by its DB id instead of all invalid ones",
    )
    parser.add_argument(
        "--re-scrape",
        action="store_true",
        help=(
            "Re-scrape the novel landing page to get a fresh cover_url when "
            "cover_url is NULL in the DB, or when a download fails with the "
            "existing cover_url. Costs one extra page request per affected novel."
        ),
    )
    parser.add_argument(
        "--min-size",
        type=int,
        default=MIN_VALID_COVER_BYTES,
        metavar="BYTES",
        help=f"Minimum valid cover file size in bytes (default: {MIN_VALID_COVER_BYTES})",
    )
    parser.add_argument(
        "--delay-min",
        type=float,
        default=COVER_BACKFILL_DELAY_MIN,
        metavar="SECONDS",
        help=f"Minimum inter-novel delay in seconds (default: {COVER_BACKFILL_DELAY_MIN})",
    )
    parser.add_argument(
        "--delay-max",
        type=float,
        default=COVER_BACKFILL_DELAY_MAX,
        metavar="SECONDS",
        help=f"Maximum inter-novel delay in seconds (default: {COVER_BACKFILL_DELAY_MAX})",
    )
    args = parser.parse_args()

    # --- Initialise infrastructure ---
    db_manager = DatabaseManager()
    repo = NovelRepository(db_manager)
    network = NetworkClient()
    browser = BrowserService()
    cover_manager = CoverManager(network, repo)

    # Scraper is only needed when --re-scrape is active
    scraper = None
    if args.re_scrape:
        scraper = ScraperService(network, browser, repo, cover_manager)
        logger.info(
            "Re-scrape mode enabled — will scrape landing pages for missing URLs."
        )

    # --- Find target novels ---
    if args.id is not None:
        row = get_single_novel(db_manager, args.id)
        if not row:
            logger.error(f"No novel found with id={args.id}")
            sys.exit(1)
        all_novels = [row]
    else:
        all_novels = get_all_novels(db_manager)

    logger.info(f"Auditing {len(all_novels)} novel(s) for valid covers...")
    logger.info(f"Minimum valid cover size: {args.min_size} bytes")
    logger.info(f"Inter-novel delay: {args.delay_min}–{args.delay_max}s")

    needs_cover, already_valid = audit_novels(all_novels, args.min_size)

    logger.info(
        f"\nAudit complete: {len(already_valid)} valid, {len(needs_cover)} need covers."
    )

    if not needs_cover:
        logger.info("All covers are valid. Nothing to do.")
        sys.exit(0)

    if args.dry_run:
        logger.info("--dry-run: no downloads will be performed.")
        logger.info(f"\nNovels that would be fixed ({len(needs_cover)}):")
        for novel_id, title, slug, source_url, cover_path, cover_url in needs_cover:
            has_url = "has cover_url" if cover_url else "NO cover_url"
            logger.info(f"  [{novel_id}] {title} ({has_url})")
        sys.exit(0)

    # --- Fix each novel that needs a cover ---
    ok_count = 0
    skipped_count = 0
    fail_count = 0

    total = len(needs_cover)
    for i, (novel_id, title, slug, source_url, cover_path, cover_url) in enumerate(
        needs_cover, start=1
    ):
        logger.info(f"[{i}/{total}] Processing: '{title}' (id={novel_id})")

        result = fix_cover(
            novel_id=novel_id,
            title=title,
            slug=slug,
            source_url=source_url,
            cover_url=cover_url,
            cover_manager=cover_manager,
            scraper=scraper,
            repo=repo,
            re_scrape=args.re_scrape,
            delay_min=args.delay_min,
            delay_max=args.delay_max,
        )

        if result == "ok":
            ok_count += 1
        elif result == "skipped":
            skipped_count += 1
        else:
            fail_count += 1

    # --- Summary ---
    logger.info("=" * 60)
    logger.info(
        f"Cover backfill complete — "
        f"Fixed: {ok_count}  "
        f"Skipped (no URL): {skipped_count}  "
        f"Failed: {fail_count}"
    )
    if skipped_count > 0:
        logger.info(
            f"  {skipped_count} novels had no cover_url in the DB. "
            f"Re-run with --re-scrape to fetch fresh URLs from their source pages."
        )
    if fail_count > 0:
        logger.info(
            f"  {fail_count} downloads failed. "
            f"Re-run this script to retry, or use --re-scrape if the stored "
            f"cover_url may be stale."
        )

    # Stop browser if it was started for re-scraping
    if args.re_scrape:
        try:
            browser.stop()
        except Exception as e:
            logger.warning(f"Browser stop failed: {e}")


if __name__ == "__main__":
    main()
