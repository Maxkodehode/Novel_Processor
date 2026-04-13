import re
import logging

from bs4 import BeautifulSoup

from .base import BaseAdapter
from utils import slugify

logger = logging.getLogger(__name__)


class ScribbleHubAdapter(BaseAdapter):
    HOSTS = ["scribblehub.com"]

    # Playwright page reference — injected by scrape() for live fetches
    _pw_page = None

    def parse(self, soup: BeautifulSoup, url: str) -> dict:
        # --- Basic metadata ---
        title = self._text(soup.select_one("div.fic_title"))
        author = self._text(soup.select_one("span.auth_name_fic"))
        cover = soup.select_one("div.fic_image img")
        cover_url = cover["src"] if cover else None

        tags = [self._text(a) for a in soup.select("a.fic_genre")]
        tags += [self._text(a) for a in soup.select("a.stag")]
        tags = [t for t in tags if t]

        status = None
        status_tag = soup.select_one(
            "span.ss-completed, span.ss-ongoing, span.ss-hiatus"
        )
        if status_tag:
            status = status_tag.get_text(strip=True).upper()

        syn = soup.select_one("div.wi_fic_desc")
        synopsis = syn.get_text(separator="\n", strip=True) if syn else None

        stats = {}
        for item in soup.select("div.widget_fic_similar li"):
            spans = item.select("span")
            if len(spans) >= 2:
                k = spans[0].get_text(strip=True).lower().replace(" ", "_").rstrip(":")
                v = spans[1].get_text(strip=True)
                stats[k] = v

        scores = {}
        rating_tag = soup.select_one("span#ratig-count")
        if rating_tag:
            try:
                scores["overall"] = float(rating_tag.get_text(strip=True))
            except ValueError:
                pass

        story_id = None
        m = re.search(r"/series/(\d+)/", url)
        if m:
            story_id = m.group(1)

        # --- Chapter count ---
        chapter_count = None
        cnt_tag = soup.select_one("span.cnt_toc")
        if cnt_tag:
            try:
                chapter_count = int(cnt_tag.get_text(strip=True).replace(",", ""))
            except ValueError:
                pass

        # --- Last TOC page number ---
        last_page = 1
        for a in soup.select("ul#pagination-mesh-toc a.page-link"):
            txt = a.get_text(strip=True)
            if txt.isdigit():
                last_page = max(last_page, int(txt))

        # --- Chapter scraping ---
        chapters_by_order = {}

        def _extract_chapters(s):
            for li in s.select("li.toc_w"):
                link = li.select_one("a")
                time_tag = li.select_one("span.fic_date_pub")
                if not link:
                    continue
                order_attr = li.get("order")
                order_val = (
                    int(order_attr) if order_attr and order_attr.isdigit() else None
                )
                published = None
                if time_tag:
                    published = time_tag.get("title") or time_tag.get_text(strip=True)
                ch = {
                    "id": li.get("data-id"),
                    "order": order_val,
                    "title": link.get_text(strip=True),
                    "url": link.get("href", ""),
                    "published": published,
                }
                if order_val is not None:
                    chapters_by_order[order_val] = ch

        _extract_chapters(soup)

        if self._pw_page and last_page > 1:
            pw = self._pw_page

            # Step 1: set display to 50 chapters/page via dropdown
            try:
                pw.select_option("select#show_chapters", value="50")
                pw.wait_for_function(
                    "document.querySelectorAll('li.toc_w').length > 15", timeout=10_000
                )
                page1_soup = BeautifulSoup(pw.content(), "html.parser")
                chapters_by_order.clear()
                _extract_chapters(page1_soup)

                new_last = 1
                for a in page1_soup.select("ul#pagination-mesh-toc a.page-link"):
                    txt = a.get_text(strip=True)
                    if txt.isdigit():
                        new_last = max(new_last, int(txt))
                last_page = new_last
                logger.info(f"[SH] Display set to 50/page — {last_page} pages to fetch")
            except Exception as e:
                logger.warning(f"[SH] Could not set display count: {e}")

            # Step 2: click pagination links in-page (avoids full reload / CF challenge)
            for page_num in range(2, last_page + 1):
                logger.info(f"[SH] TOC page {page_num}/{last_page}")
                try:
                    clicked = pw.evaluate(f"""
                        (() => {{
                            const links = document.querySelectorAll('ul#pagination-mesh-toc a.page-link');
                            for (const a of links) {{
                                if (a.textContent.trim() === '{page_num}') {{
                                    a.click();
                                    return true;
                                }}
                            }}
                            const next = document.querySelector('ul#pagination-mesh-toc a.page-link.next');
                            if (next) {{ next.click(); return 'next'; }}
                            return false;
                        }})()
                    """)
                    if not clicked:
                        logger.warning(
                            f"[SH] Page {page_num} link not found in pagination bar, stopping"
                        )
                        break

                    pw.wait_for_function(
                        f"""
                        (() => {{
                            const active = document.querySelector(
                                'ul#pagination-mesh-toc li.active a, '
                                'ul#pagination-mesh-toc li.active span'
                            );
                            return active && active.textContent.trim() === '{page_num}';
                        }})()
                        """,
                        timeout=15_000,
                    )
                    pw.wait_for_timeout(500)
                    page_soup = BeautifulSoup(pw.content(), "html.parser")
                    _extract_chapters(page_soup)

                except Exception as e:
                    logger.warning(f"[SH] Page {page_num} failed ({e}), skipping")
                    continue

        elif last_page > 1:
            logger.warning(
                f"[SH] {chapter_count} chapters across {last_page} pages but only page 1 loaded "
                "(--use-local mode). Run live to fetch all."
            )

        chapters = sorted(chapters_by_order.values(), key=lambda c: c["order"])
        for i, ch in enumerate(chapters):
            ch["order"] = i

        return {
            "site": "scribblehub",
            "url": url,
            "title": title,
            "slug": slugify(title) if title else None,
            "author": author,
            "cover_url": cover_url,
            "status": status,
            "tags": tags,
            "synopsis": synopsis,
            "language": "en",
            "scores": scores,
            "stats": stats,
            "chapter_count": chapter_count or len(chapters),
            "chapters": chapters,
        }

    def parse_chapter_content(self, soup: BeautifulSoup) -> dict:
        content_tag = soup.select_one("#chp_raw")
        return {
            "plain_text": content_tag.get_text(separator="\n", strip=True)
            if content_tag
            else "",
            "raw_html": str(content_tag) if content_tag else "",
        }
