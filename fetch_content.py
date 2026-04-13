import sqlite3
import time
import hashlib
import logging
from bs4 import BeautifulSoup
from adapters import get_adapter
from curl_cffi import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

FETCH_DELAY = 8  # seconds between requests
COMMIT_BATCH_SIZE = 10  # commit to DB every N chapters


def worker():
    conn = sqlite3.connect("novels.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, chapter_title, chapter_url FROM chapters WHERE plain_content IS NULL"
    )
    tasks = cursor.fetchall()

    if not tasks:
        logger.info("All chapters are up to date.")
        conn.close()
        return

    logger.info(f"Starting fetch for {len(tasks)} chapters...")

    pending_commits = 0

    for ch_id, title, url in tasks:
        try:
            logger.info(f"Fetching: {title}")
            adapter = get_adapter(url)

            response = requests.get(url, impersonate="chrome", timeout=30)

            if response.status_code != 200:
                logger.warning(f"HTTP {response.status_code} for {url}")
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            content_data = adapter.parse_chapter_content(soup)

            if (
                not content_data
                or "plain_text" not in content_data
                or "raw_html" not in content_data
            ):
                logger.error(
                    f"Adapter returned invalid content_data for {url}: {content_data}"
                )
                continue

            content_text = content_data["plain_text"]
            raw_html = content_data["raw_html"]

            if not content_text:
                logger.warning(f"Empty plain_text for {url}, skipping.")
                continue

            chapter_hash = hashlib.sha256(content_text.encode("utf-8")).hexdigest()

            cursor.execute(
                """
                UPDATE chapters
                SET plain_content = ?,
                    html_content = ?,
                    chapter_hash = ?,
                    last_updated = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (content_text, raw_html, chapter_hash, ch_id),
            )

            pending_commits += 1
            if pending_commits >= COMMIT_BATCH_SIZE:
                conn.commit()
                pending_commits = 0
                logger.debug("Batch committed.")

            logger.info(f"Saved '{title}'. Hash: {chapter_hash[:8]}")

        except Exception as e:
            logger.exception(f"Unexpected error processing {url}: {e}")

        finally:
            time.sleep(FETCH_DELAY)

    # Commit any remaining uncommitted rows
    if pending_commits > 0:
        conn.commit()

    conn.close()
    logger.info("Done.")


if __name__ == "__main__":
    worker()
