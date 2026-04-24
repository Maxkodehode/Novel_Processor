# =============================================================================
# CHANGES:
#   - Removed the broken Playwright browser block entirely.
#     It referenced self._browser (doesn't exist on CoverManager), used
#     `with self.browser` which would shut down the shared BrowserService
#     mid-run, and used TIMEOUT which was never imported. Cover images are
#     static CDN assets — the network client handles them correctly.
#   - Removed browser_service parameter from __init__ (was unused/broken).
#   - Added COVER_FETCH_DELAY sleep before each download so covers don't
#     fire in a tight loop during discovery runs.
#   - Added non-zero file check before skipping existing covers.
#   - Imported COVER_FETCH_DELAY and USER_AGENT from config at the top
#     instead of inline inside the method.
# =============================================================================

import os
import time
import logging

from core.config import COVERS_DIR, USER_AGENT, COVER_FETCH_DELAY
from core.network import NetworkClient
from core.database import NovelRepository

logger = logging.getLogger(__name__)

DEBUG = False


class CoverManager:
    def __init__(
        self,
        network_client: NetworkClient,
        repository: NovelRepository,
    ):
        """
        Manages downloading and storing novel cover images.

        Parameters:
            network_client (NetworkClient): Used for all HTTP requests.
            repository (NovelRepository): Used to persist the saved cover path.

        Called by: ScraperService.__init__(), discovery_service main block, main.py, sync_novels.py
        Depends on: NetworkClient, NovelRepository, COVERS_DIR
        """
        self.network = network_client
        self.repository = repository
        os.makedirs(COVERS_DIR, exist_ok=True)

    def download_and_save(self, cover_url: str, novel_id: int, slug: str) -> str | None:
        """
        Downloads a cover image and saves it to disk, then updates the DB.

        Removes any stale cover file before downloading. Skips download if a
        valid non-zero file already exists at the target path. Applies
        COVER_FETCH_DELAY before the request to avoid tight loops during
        discovery runs.

        Parameters:
            cover_url (str): Remote URL of the cover image.
            novel_id (int): DB ID of the novel, used in the filename.
            slug (str): Novel slug, used in the filename.

        Returns:
            str | None: Relative path to the saved file, or None on failure.

        Called by: ScraperService.populate_novel()
        Depends on: NetworkClient.get(), NovelRepository.update_cover_path(),
                    COVERS_DIR, COVER_FETCH_DELAY, USER_AGENT
        """
        if DEBUG:
            logger.debug(f"[download_and_save] novel_id={novel_id} url={cover_url}")

        # --- Remove stale cover if one exists ---
        try:
            old_cover = self.repository.db.execute(
                "SELECT cover_path FROM novels WHERE id = ?", (novel_id,)
            )
            if old_cover and old_cover[0][0]:
                old_path = old_cover[0][0]
                if os.path.exists(old_path):
                    logger.info(f"Removing old cover: {old_path}")
                    os.remove(old_path)
        except Exception as e:
            logger.warning(f"Failed to remove old cover for novel {novel_id}: {e}")

        # --- Determine output path ---
        ext = os.path.splitext(cover_url.split("?")[0])[-1].lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            ext = ".jpg"

        filename = f"{slug}_{novel_id}{ext}"
        save_path = os.path.join(COVERS_DIR, filename)

        # Skip if a valid file is already present
        if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
            logger.info(f"Cover already exists, skipping download: {save_path}")
            return save_path

        # --- Rate limit: small pause before firing the request ---
        if DEBUG:
            logger.debug(
                f"[download_and_save] sleeping {COVER_FETCH_DELAY}s before download"
            )
        time.sleep(COVER_FETCH_DELAY)

        # --- Download via network client ---
        try:
            headers = {}

            # FanFiction.net CDN requires a matching Referer to serve images
            if any(
                domain in cover_url.lower()
                for domain in ["fanfiction.net", "ff.net", "ffn"]
            ):
                headers = {
                    "Referer": "https://www.fanfiction.net/",
                    "User-Agent": USER_AGENT,
                }

            if DEBUG:
                logger.debug(f"[download_and_save] GET {cover_url} headers={headers}")

            response = self.network.get(cover_url, headers=headers)

            if response.status_code != 200:
                logger.warning(
                    f"Cover download returned HTTP {response.status_code} for {cover_url}"
                )
                return None

            if len(response.content) == 0:
                logger.warning(f"Downloaded 0-byte cover from {cover_url}, skipping.")
                return None

            with open(save_path, "wb") as f:
                f.write(response.content)

            # Final sanity check on the written file
            if os.path.getsize(save_path) == 0:
                logger.warning(f"Saved cover is 0 bytes, deleting: {save_path}")
                os.remove(save_path)
                return None

            logger.info(f"Cover saved: {save_path} ({len(response.content)} bytes)")
            self.repository.update_cover_path(novel_id, save_path)
            return save_path

        except Exception as e:
            logger.error(f"Failed to download cover from {cover_url}: {e}")
            return None
