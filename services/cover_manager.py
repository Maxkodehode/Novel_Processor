# =============================================================================
# CHANGES:
#   - download_and_save(): Removed the "skip if file already exists" guard.
#     Previously, any existing cover file (including 0-byte files from failed
#     prior downloads) would block a fresh download. Now the old file is always
#     deleted before downloading, so covers are refreshed on every populate
#     call and bad/empty files are automatically replaced.
#   - The stale-cover removal block was already present but only ran for covers
#     recorded in the DB. It now also removes any file at the target save_path
#     before downloading, catching cases where the DB path and file path differ.
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

        Called by: ScraperService.__init__(), discovery_service main block,
                   main.py, sync_novels.py, server.run_background_fetch()
        Depends on: NetworkClient, NovelRepository, COVERS_DIR
        """
        self.network = network_client
        self.repository = repository
        os.makedirs(COVERS_DIR, exist_ok=True)

    def download_and_save(self, cover_url: str, novel_id: int, slug: str) -> str | None:
        """
        Downloads a cover image, replacing any existing cover for this novel.

        Always removes the old cover (both the DB-recorded path and any file
        at the computed save path) before downloading, so covers are always
        refreshed and 0-byte or stale files are never left in place.

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

        # --- Remove DB-recorded cover if one exists ---
        try:
            old_cover = self.repository.db.execute(
                "SELECT cover_path FROM novels WHERE id = ?", (novel_id,)
            )
            if old_cover and old_cover[0][0]:
                old_path = old_cover[0][0]
                if os.path.exists(old_path):
                    logger.info(f"Removing old cover (DB path): {old_path}")
                    os.remove(old_path)
        except Exception as e:
            logger.warning(f"Failed to remove old cover for novel {novel_id}: {e}")

        # --- Determine output path ---
        ext = os.path.splitext(cover_url.split("?")[0])[-1].lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            ext = ".jpg"

        filename = f"{slug}_{novel_id}{ext}"
        save_path = os.path.join(COVERS_DIR, filename)

        # Remove any file already at the target path (e.g. from a prior failed download)
        if os.path.exists(save_path):
            try:
                os.remove(save_path)
                if DEBUG:
                    logger.debug(
                        f"[download_and_save] Removed existing file at {save_path}"
                    )
            except Exception as e:
                logger.warning(f"Could not remove existing cover at {save_path}: {e}")

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
