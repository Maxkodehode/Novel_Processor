# =============================================================================
# CHANGES:
#   - parse(): The old logic only ran the Playwright block when last_page > 1,
#     meaning novels with all chapters on one page (no pagination) never
#     triggered any JS — so chapter links were never loaded from the DOM.
#     ScribbleHub renders chapter <li> elements client-side regardless of
#     page count, so Playwright is always needed.
#   - parse(): Added Strategy 1 — call toc_fic_show_all() via pw.evaluate().
#     This mirrors the "Show All Chapters" button. The site signals completion
#     by adding 'isdisabled' to #menu_icon_fic. One JS call replaces the
#     entire pagination loop for most novels.
#   - parse(): Kept the old pagination loop as Strategy 2 (fallback) in case
#     toc_fic_show_all() fails or is unavailable.
#   - parse(): Playwright block now triggers whenever _pw_page is set,
#     not only when last_page > 1.
#   - _extract_chapters(): Unchanged — selector logic is correct.
# =============================================================================

import re
import logging

from bs4 import BeautifulSoup

from .base import BaseAdapter
from utils.text import slugify

logger = logging.getLogger(__name__)

DEBUG = False


class ScribbleHubAdapter(BaseAdapter):
    HOSTS = ["scribblehub.com"]

    # Playwright page reference — injected by ScraperService for live fetches
    _pw_page = None

    def parse(self, soup: BeautifulSoup, url: str) -> dict:
        """
        Parses a ScribbleHub novel landing page into a structured data dict.

        ScribbleHub renders chapter links client-side via JavaScript, so a
        Playwright page reference must be injected via _pw_page for live runs.
        Strategy 1 calls toc_fic_show_all() to load all chapters at once.
        Strategy 2 (fallback) clicks through paginated TOC pages.

        Parameters:
            soup (BeautifulSoup): Parsed HTML of the novel landing page.
            url (str): The novel's canonical URL.

        Returns:
            dict: Novel data including title, author, tags, chapters, etc.

        Called by: ScraperService.scrape_novel()
        Depends on: _extract_chapters(), slugify(), Playwright page (optional)
        """
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

        # --- Chapter count (from the counter badge) ---
        chapter_count = None
        cnt_tag = soup.select_one("span.cnt_toc")
        if cnt_tag:
            try:
                chapter_count = int(cnt_tag.get_text(strip=True).replace(",", ""))
            except ValueError:
                pass

        # --- Last TOC page number (from initial static HTML) ---
        last_page = 1
        for a in soup.select("ul#pagination-mesh-toc a.page-link"):
            txt = a.get_text(strip=True)
            if txt.isdigit():
                last_page = max(last_page, int(txt))

        # --- Chapter scraping ---
        chapters_by_order = {}

        def _extract_chapters(s):
            """
            Extracts chapter entries from a parsed TOC soup object.

            Parameters:
                s (BeautifulSoup): Soup of the current page state to extract from.

            Returns:
                None — writes directly into chapters_by_order.

            Called by: parse() (multiple times across strategies)
            Depends on: BeautifulSoup selector 'li.toc_w'
            """
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
                    if DEBUG:
                        logger.debug(
                            f"[_extract_chapters] order={order_val} "
                            f"title='{ch['title']}' url={ch['url']}"
                        )

        # Always extract from the initial static HTML first (may get page 1)
        _extract_chapters(soup)

        if self._pw_page:
            # Playwright is available — chapters are rendered by JS so we must
            # use the browser to get the full list regardless of page count.
            pw = self._pw_page

            # ── Strategy 1: toc_fic_show_all() ───────────────────────────────
            # Calls the same JS function as the "Show All Chapters" button.
            # The site signals completion by adding 'isdisabled' to #menu_icon_fic.
            show_all_success = False
            try:
                logger.info("[SH] Calling toc_fic_show_all() to load all chapters...")
                if DEBUG:
                    logger.debug("[SH] evaluate('toc_fic_show_all()')")

                pw.evaluate("toc_fic_show_all()")

                # Wait for the icon to gain 'isdisabled' — the site's own "done" signal
                pw.wait_for_function(
                    """
                    () => {
                        const icon = document.querySelector('#menu_icon_fic');
                        return icon && icon.classList.contains('isdisabled');
                    }
                    """,
                    timeout=20_000,
                )

                # Brief pause for DOM to finish rendering all <li> elements
                pw.wait_for_timeout(800)

                full_soup = BeautifulSoup(pw.content(), "html.parser")
                chapters_by_order.clear()
                _extract_chapters(full_soup)

                logger.info(
                    f"[SH] show_all succeeded — {len(chapters_by_order)} chapters found."
                )
                show_all_success = True

            except Exception as e:
                logger.warning(
                    f"[SH] toc_fic_show_all() failed ({e}), falling back to pagination loop."
                )

            # ── Strategy 2: Pagination loop (fallback) ────────────────────────
            # Used when show_all fails. Iterates TOC pages by clicking page links.
            if not show_all_success and last_page > 1:
                try:
                    pw.select_option("select#show_chapters", value="50")
                    pw.wait_for_function(
                        "document.querySelectorAll('li.toc_w').length > 15",
                        timeout=10_000,
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
                    logger.info(
                        f"[SH] Pagination fallback — {last_page} pages to iterate."
                    )
                except Exception as e:
                    logger.warning(f"[SH] Could not set display count: {e}")

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
                                f"[SH] Page {page_num} link not found in pagination bar, stopping."
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
                        logger.warning(f"[SH] Page {page_num} failed ({e}), skipping.")
                        continue

        elif last_page > 1:
            logger.warning(
                f"[SH] {chapter_count} chapters across {last_page} pages but only page 1 "
                "loaded (--use-local mode or no browser). Run live to fetch all."
            )

        # Re-index chapters sequentially so order values are contiguous
        chapters = sorted(chapters_by_order.values(), key=lambda c: c["order"])
        for i, ch in enumerate(chapters):
            ch["order"] = i

        if DEBUG:
            logger.debug(f"[parse] Final chapter count: {len(chapters)}")

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
        """
        Extracts plain text and raw HTML from a ScribbleHub chapter page.

        Parameters:
            soup (BeautifulSoup): Parsed HTML of the chapter page.

        Returns:
            dict: {'plain_text': str, 'raw_html': str}

        Called by: ScraperService.fetch_chapters()
        Depends on: BeautifulSoup selector '#chp_raw'
        """
        content_tag = soup.select_one("#chp_raw")
        return {
            "plain_text": content_tag.get_text(separator="\n", strip=True)
            if content_tag
            else "",
            "raw_html": str(content_tag) if content_tag else "",
        }
