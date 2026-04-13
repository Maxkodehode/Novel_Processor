import os
import sqlite3
import logging
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from adapters import get_adapter
from curl_cffi import requests as cur_requests

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

COVERS_DIR = "covers"


def download_cover(cover_url: str, novel_id: int, slug: str) -> str | None:
    os.makedirs(COVERS_DIR, exist_ok=True)

    ext = os.path.splitext(cover_url.split("?")[0])[-1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        ext = ".jpg"

    filename = f"{slug}_{novel_id}{ext}"
    relative_path = os.path.join(COVERS_DIR, filename)

    if os.path.exists(relative_path):
        logger.info(f"Cover already on disk, skipping: {relative_path}")
        return relative_path

    try:
        response = cur_requests.get(cover_url, impersonate="chrome", timeout=30)
        if response.status_code == 200:
            with open(relative_path, "wb") as f:
                f.write(response.content)
            logger.info(f"Cover saved: {relative_path}")
            return relative_path
        else:
            logger.warning(
                f"Cover fetch returned HTTP {response.status_code}: {cover_url}"
            )
            return None
    except Exception as e:
        logger.error(f"Failed to download cover from {cover_url}: {e}")
        return None


def save_cover_to_db(novel_id: int, cover_path: str) -> None:
    conn = sqlite3.connect("novels.db")
    try:
        conn.execute(
            "UPDATE novels SET cover_path = ? WHERE id = ?",
            (cover_path, novel_id),
        )
        conn.commit()
        logger.info(f"DB updated — novel {novel_id} cover_path: {cover_path}")
    except Exception as e:
        logger.error(f"Failed to write cover_path to DB for novel {novel_id}: {e}")
    finally:
        conn.close()


def _parse_and_handle_cover(
    adapter, soup: BeautifulSoup, url: str, novel_id: int | None
) -> dict:
    result = adapter.parse(soup, url)

    cover_url = result.get("cover_url")
    if cover_url and novel_id is not None:
        slug = result.get("slug") or f"novel_{novel_id}"
        cover_path = download_cover(cover_url, novel_id, slug)
        if cover_path:
            save_cover_to_db(novel_id, cover_path)
            result["cover_path"] = cover_path

    return result


def scrape(
    url: str,
    novel_id: int | None = None,
    use_local: str | None = None,
    save_html: str | None = None,
) -> dict:

    adapter = get_adapter(url)
    logger.info(f"Using adapter: {type(adapter).__name__}")

    if use_local and os.path.exists(use_local):
        with open(use_local, "r", encoding="utf-8") as f:
            html = f.read()
        soup = BeautifulSoup(html, "html.parser")
        return _parse_and_handle_cover(adapter, soup, url, novel_id)

    logger.info(f"Attempting fast fetch: {url}")
    try:
        response = cur_requests.get(url, impersonate="chrome", timeout=30)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            return _parse_and_handle_cover(adapter, soup, url, novel_id)

        logger.warning(
            f"curl_cffi returned {response.status_code}. Falling back to Playwright..."
        )

    except Exception as e:
        logger.warning(f"curl_cffi failed: {e}. Falling back to Playwright...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(user_agent=USER_AGENT)
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)

            try:
                page.wait_for_selector(
                    "li.toc_w, div.fiction-stats, div#profile_top", timeout=15_000
                )
            except Exception:
                logger.debug("Selector wait timed out, continuing anyway.")

            html = page.content()

            if save_html:
                with open(save_html, "w", encoding="utf-8") as f:
                    f.write(html)
                logger.info(f"Saved raw HTML to: {save_html}")

            soup = BeautifulSoup(html, "html.parser")

            if hasattr(adapter, "_pw_page"):
                adapter._pw_page = page

            return _parse_and_handle_cover(adapter, soup, url, novel_id)

        finally:
            browser.close()
