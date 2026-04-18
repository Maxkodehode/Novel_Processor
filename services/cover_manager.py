import os
import logging
from core.config import COVERS_DIR
from core.network import NetworkClient
from core.database import NovelRepository

logger = logging.getLogger(__name__)


class CoverManager:
    def __init__(self, network_client: NetworkClient, repository: NovelRepository):
        self.network = network_client
        self.repository = repository
        os.makedirs(COVERS_DIR, exist_ok=True)

    def download_and_save(self, cover_url: str, novel_id: int, slug: str) -> str | None:
        # Cleanup old cover
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

        ext = os.path.splitext(cover_url.split("?")[0])[-1].lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            ext = ".jpg"

        filename = f"{slug}_{novel_id}{ext}"
        relative_path = os.path.join(COVERS_DIR, filename)

        if os.path.exists(relative_path):
            # Even if it exists, we might have just deleted it if it was the same path
            # But os.path.exists would return False then.
            # If it still exists, it means cleanup didn't delete it (maybe same filename but already there?)
            # Actually, the task says "delete it with os.remove() ... Then proceed with downloading"
            # So if it existed and was deleted, we should download it again to ensure it's fresh.
            pass

        try:
            headers = {}
            if any(
                domain in cover_url.lower()
                for domain in ["fanfiction.net", "ff.net", "ffn"]
            ):
                from core.config import USER_AGENT

                headers = {
                    "Referer": "https://www.fanfiction.net/",
                    "User-Agent": USER_AGENT,
                }

            response = self.network.get(cover_url, headers=headers)
            if response.status_code == 200:
                if len(response.content) == 0:
                    logger.warning(
                        f"Downloaded 0-byte cover from {cover_url}, skipping."
                    )
                    return None

                with open(relative_path, "wb") as f:
                    f.write(response.content)

                if os.path.getsize(relative_path) == 0:
                    logger.warning(
                        f"Saved 0-byte cover file: {relative_path}, deleting."
                    )
                    os.remove(relative_path)
                    return None

                logger.info(f"Cover saved: {relative_path}")
                self.repository.update_cover_path(novel_id, relative_path)
                return relative_path
        except Exception as e:
            logger.error(f"Failed to download cover from {cover_url}: {e}")

        return None
