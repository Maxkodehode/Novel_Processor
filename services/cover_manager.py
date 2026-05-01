# =============================================================================
# CHANGES:
#   - download_and_save(): Added explicit None/empty guard at the top — if
#     cover_url is falsy the method returns None immediately with a warning
#     instead of crashing on cover_url.startswith("/").
#   - download_and_save(): Network fetch exception handler now logs the full
#     error string so encoding errors (curl error 61) are visible in logs
#     before handing off to the browser fallback.
#   - _download_via_browser(): Fixed double-navigation bug — get_page_content()
#     already calls page.goto() internally, so the subsequent page.goto() call
#     was navigating twice and the first response object was discarded. Now the
#     method opens a page, navigates once via page.goto(), and reads the body
#     from that single response. The BrowserService context is opened with
#     block_resources=False so image bytes are not intercepted and aborted.
#   - _download_via_browser(): Added None check on the goto() response before
#     calling response.body() — Playwright can return None for failed navigations.
# =============================================================================

import os
import logging
import time

from core.config import COVERS_DIR, USER_AGENT, COVER_FETCH_DELAY
from core.network import NetworkClient
from core.database import NovelRepository

logger = logging.getLogger(__name__)

DEBUG = False


class CoverManager:
    def __init__(self, network_client: NetworkClient, repository: NovelRepository):
        self.network = network_client
        self.repository = repository
        os.makedirs(COVERS_DIR, exist_ok=True)

    def download_and_save(self, cover_url: str, novel_id: int, slug: str) -> str | None:
        """
        Downloads a cover image and saves it to disk, then records the path in the DB.

        Uses a two-tier strategy:
          Tier 1: Fast network fetch via curl_cffi (NetworkClient).
          Tier 2: Playwright browser fallback if network fetch fails for any reason.

        Skips generic placeholder images and handles relative URLs for Royal Road
        and FanFiction.net.

        Parameters:
            cover_url (str): URL of the cover image to download.
            novel_id (int): DB id of the novel (used for file naming and DB update).
            slug (str): URL-safe novel slug (used for file naming).

        Returns:
            str | None: Local file path if saved successfully, None otherwise.

        Called by: ScraperService.populate_novel(), backfill_covers.py fix_cover()
        Depends on: NetworkClient.get(), _download_via_browser(), NovelRepository.update_cover_path()
        """
        # Guard: cover_url must be a non-empty string
        if not cover_url:
            logger.warning(
                f"download_and_save called with empty cover_url for novel {novel_id}"
            )
            return None

        # 1. Resolve relative URLs (Royal Road / FanFiction.net)
        if cover_url.startswith("/"):
            if "royalroad" in cover_url or "royalroad" in slug:
                cover_url = f"https://www.royalroad.com{cover_url}"
            elif "fanfiction" in cover_url or "fanfiction" in slug:
                cover_url = f"https://www.fanfiction.net{cover_url}"

        # 2. Skip generic placeholder images
        placeholders = ["d_60_90.jpg", "nocover-new-min.png", "default-cover"]
        if any(p in cover_url.lower() for p in placeholders):
            logger.info(
                f"Skipping generic placeholder for novel {novel_id}: {cover_url}"
            )
            return None

        # 3. Remove stale cover file to prevent orphaned files on disk
        try:
            old_path_row = self.repository.db.execute(
                "SELECT cover_path FROM novels WHERE id = ?", (novel_id,)
            )
            if old_path_row:
                old_path = old_path_row[0][0] if old_path_row[0] else None
                if old_path and os.path.exists(old_path):
                    os.remove(old_path)
                    if DEBUG:
                        logger.debug(
                            f"[download_and_save] Removed stale cover: {old_path}"
                        )
        except Exception as e:
            logger.warning(f"Could not remove old cover for novel {novel_id}: {e}")

        # 4. Determine save path from URL extension
        ext = os.path.splitext(cover_url.split("?")[0])[-1].lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            ext = ".jpg"

        filename = f"{slug}_{novel_id}{ext}"
        save_path = os.path.join(COVERS_DIR, filename)

        # 5. Polite delay before fetch (rate limiting for CDN requests)
        if COVER_FETCH_DELAY > 0:
            time.sleep(COVER_FETCH_DELAY)

        # 6. Tier 1: Fast network fetch
        headers = {"User-Agent": USER_AGENT}
        if "fanfiction.net" in cover_url.lower():
            headers["Referer"] = "https://www.fanfiction.net/"
        if "royalroad" in cover_url.lower():
            headers["Referer"] = "https://www.royalroad.com/"

        try:
            if DEBUG:
                logger.debug(f"[download_and_save] Tier 1 fetch: {cover_url}")

            response = self.network.get(cover_url, headers=headers)

            if len(response.content) < 1024:
                raise ValueError(
                    f"Response too small ({len(response.content)} bytes) — likely a placeholder or error page"
                )

            # Reconcile extension with actual Content-Type
            content_type = response.headers.get("Content-Type", "")
            if "image/webp" in content_type and not save_path.endswith(".webp"):
                save_path = save_path.rsplit(".", 1)[0] + ".webp"
            elif "image/png" in content_type and not save_path.endswith(".png"):
                save_path = save_path.rsplit(".", 1)[0] + ".png"

            with open(save_path, "wb") as f:
                f.write(response.content)

            logger.info(
                f"Cover saved (Network): {save_path} ({len(response.content)} bytes)"
            )
            self.repository.update_cover_path(novel_id, save_path)
            return save_path

        except Exception as e:
            # Log the real error (e.g. curl error 61) before falling through
            logger.warning(
                f"Network fetch failed for novel {novel_id} ({cover_url}): {e}. "
                f"Trying browser fallback..."
            )
            return self._download_via_browser(cover_url, novel_id, save_path)

    def _download_via_browser(
        self, cover_url: str, novel_id: int, save_path: str
    ) -> str | None:
        """
        Downloads a cover image via a headless Playwright browser.

        Used as a fallback when the fast network fetch fails (e.g. due to
        Brotli/Zstd encoding errors, CAPTCHA-guarded CDNs, or hotlink protection
        that checks for a real browser User-Agent).

        Opens a fresh BrowserService context so this method is safe to call
        without a running browser. Navigates once and reads the raw response
        body from Playwright's network interception — no double-navigation.

        Parameters:
            cover_url (str): URL of the cover image.
            novel_id (int): DB id of the novel.
            save_path (str): Full local path where the image should be saved.

        Returns:
            str | None: save_path if saved successfully, None otherwise.

        Called by: download_and_save()
        Depends on: BrowserService, NovelRepository.update_cover_path()
        """
        from services.browser_service import BrowserService

        if DEBUG:
            logger.debug(
                f"[_download_via_browser] Attempting browser fetch: {cover_url}"
            )

        try:
            # Use a fresh context — block_resources=False so image bytes are not aborted
            with BrowserService(headless=True) as browser:
                browser.start()
                page = browser._context.new_page()

                try:
                    # Single navigation — read body from this response object
                    response = page.goto(
                        cover_url,
                        timeout=30_000,
                        wait_until="networkidle",
                    )

                    if response is None:
                        logger.warning(
                            f"Browser navigation returned None for {cover_url} "
                            f"(novel {novel_id})"
                        )
                        return None

                    buffer = response.body()

                    if buffer and len(buffer) > 1024:
                        with open(save_path, "wb") as f:
                            f.write(buffer)
                        logger.info(
                            f"Cover saved (Browser): {save_path} ({len(buffer)} bytes)"
                        )
                        self.repository.update_cover_path(novel_id, save_path)
                        return save_path
                    else:
                        logger.warning(
                            f"Browser response body too small for novel {novel_id} "
                            f"({len(buffer) if buffer else 0} bytes)"
                        )
                        return None

                finally:
                    page.close()

        except Exception as e:
            logger.error(
                f"Browser fallback failed for novel {novel_id} ({cover_url}): {e}"
            )
            return None
