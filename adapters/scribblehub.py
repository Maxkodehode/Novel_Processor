# =============================================================================
# CHANGES:
#   - parse(): Added a wait-for-readiness block before calling toc_fic_show_all().
#     The page is now in "load" state (controlled by scraper_service passing
#     wait_until="load" to get_page_content), but ScribbleHub's JS bundle can
#     still be attaching globals at that point. We now wait for either
#     #menu_icon_fic to exist in the DOM (the Show-All button container, only
#     present after scripts run) or a 2000ms fallback timeout before evaluating,
#     whichever comes first. This prevents the ReferenceError when evaluate()
#     fires before the site's bundle has run.
#   - parse(): Strategy 2 (pagination fallback) now also waits for the TOC
#     container selector before attempting to read last_page from the DOM,
#     so it does not silently return 0 chapters when show_all fails.
#   - parse(): Improved failure logging — when toc_fic_show_all fails the log
#     now distinguishes between "function not defined yet" (timing) vs other
#     errors, making it easier to diagnose re-occurrences.
#   - All other logic (90% threshold check, re-indexing, _extract_chapters)
#     unchanged.
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

        IMPORTANT: scraper_service must call get_page_content() with
        wait_until="load" for ScribbleHub so the site's JS bundle is fully
        executed before this method receives the page. Without that, Strategy 1
        will always fail with ReferenceError.

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

            # ── Wait for JS bundle readiness ──────────────────────────────────
            # toc_fic_show_all() is defined by ScribbleHub's own JS bundle.
            # Even after "load" state, the function may not be attached yet if
            # the bundle is deferred. We wait for #menu_icon_fic (the Show-All
            # button's container) which only appears after scripts run, then
            # add a small extra pause for any async module initialisation.
            try:
                pw.wait_for_selector("#menu_icon_fic", timeout=15_000)
                pw.wait_for_timeout(1500)
                if DEBUG:
                    logger.debug("[parse] #menu_icon_fic found — JS bundle ready")
            except Exception:
                # Selector never appeared — extra pause as last resort
                logger.warning(
                    "[parse] #menu_icon_fic did not appear within 15s; "
                    "proceeding anyway (toc_fic_show_all may fail)"
                )
                pw.wait_for_timeout(2000)

            # ── Strategy 1: toc_fic_show_all() ───────────────────────────────
            # Calls the same JS function as the "Show All Chapters" button.
            # NOTE: 'isdisabled' is added to #menu_icon_fic at the START of
            # loading, not the end — waiting for it fires too early and returns
            # only the initially-rendered chapters (typically 15).
            # Instead we wait until li.toc_w count matches the known
            # chapter_count from the badge. Timeout is generous (60s) to
            # accommodate novels with hundreds of chapters.
            show_all_success = False
            try:
                logger.info("[SH] Calling toc_fic_show_all() to load all chapters...")
                if DEBUG:
                    logger.debug("[SH] evaluate('toc_fic_show_all()')")

                pw.evaluate("toc_fic_show_all()")

                if chapter_count and chapter_count > 0:
                    # Wait until the DOM has at least as many li.toc_w elements
                    # as the badge says there should be chapters.
                    logger.info(
                        f"[SH] Waiting for {chapter_count} chapters to render..."
                    )
                    pw.wait_for_function(
                        f"() => document.querySelectorAll('li.toc_w').length >= {chapter_count}",
                        timeout=60_000,
                    )
                else:
                    # No known count — fall back to waiting for isdisabled
                    # plus a generous fixed pause
                    pw.wait_for_function(
                        """
                        () => {
                            const icon = document.querySelector('#menu_icon_fic');
                            return icon && icon.classList.contains('isdisabled');
                        }
                        """,
                        timeout=30_000,
                    )
                    pw.wait_for_timeout(2000)

                # Extra small pause for any final DOM settling
                pw.wait_for_timeout(500)

                full_soup = BeautifulSoup(pw.content(), "html.parser")
                chapters_by_order.clear()
                _extract_chapters(full_soup)

                found = len(chapters_by_order)
                logger.info(f"[SH] show_all complete — {found} chapters found.")

                # Cross-check: if we got significantly fewer than expected,
                # don't trust the result — fall through to pagination loop.
                if chapter_count and found < chapter_count * 0.9:
                    logger.warning(
                        f"[SH] show_all returned {found}/{chapter_count} chapters "
                        f"— below 90% threshold, falling back to pagination."
                    )
                else:
                    show_all_success = True

            except Exception as e:
                error_str = str(e)
                if "ReferenceError" in error_str and "toc_fic_show_all" in error_str:
                    logger.warning(
                        "[SH] toc_fic_show_all() is not defined — JS bundle may not "
                        "have attached its globals yet. Falling back to pagination loop."
                    )
                else:
                    logger.warning(
                        f"[SH] toc_fic_show_all() failed ({e}), "
                        f"falling back to pagination loop."
                    )

            # ── Strategy 2: Pagination loop (fallback) ────────────────────────
            # Used when show_all fails or returns too few chapters.
            # Also used for single-page TOCs when show_all is unavailable.
            if not show_all_success:
                # Re-read last_page from live DOM in case static HTML was stale
                try:
                    pw.wait_for_selector(
                        "ul#pagination-mesh-toc, li.toc_w", timeout=10_000
                    )
                    live_soup = BeautifulSoup(pw.content(), "html.parser")
                    for a in live_soup.select("ul#pagination-mesh-toc a.page-link"):
                        txt = a.get_text(strip=True)
                        if txt.isdigit():
                            last_page = max(last_page, int(txt))
                    if DEBUG:
                        logger.debug(f"[parse] live DOM last_page re-read: {last_page}")
                except Exception as e:
                    logger.warning(
                        f"[SH] Could not re-read pagination from live DOM: {e}"
                    )

                if last_page > 1:
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
                        for a in page1_soup.select(
                            "ul#pagination-mesh-toc a.page-link"
                        ):
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
                                    const links = document.querySelectorAll(
                                        'ul#pagination-mesh-toc a.page-link'
                                    );
                                    for (const a of links) {{
                                        if (a.textContent.trim() === '{page_num}') {{
                                            a.click();
                                            return true;
                                        }}
                                    }}
                                    const next = document.querySelector(
                                        'ul#pagination-mesh-toc a.page-link.next'
                                    );
                                    if (next) {{ next.click(); return 'next'; }}
                                    return false;
                                }})()
                            """)
                            if not clicked:
                                logger.warning(
                                    f"[SH] Page {page_num} link not found in "
                                    f"pagination bar, stopping."
                                )
                                break

                            pw.wait_for_function(
                                f"""
                                (() => {{
                                    const active = document.querySelector(
                                        'ul#pagination-mesh-toc li.active a, '
                                        'ul#pagination-mesh-toc li.active span'
                                    );
                                    return active &&
                                        active.textContent.trim() === '{page_num}';
                                }})()
                                """,
                                timeout=15_000,
                            )
                            pw.wait_for_timeout(500)
                            page_soup = BeautifulSoup(pw.content(), "html.parser")
                            _extract_chapters(page_soup)

                        except Exception as e:
                            logger.warning(
                                f"[SH] Page {page_num} failed ({e}), skipping."
                            )
                            continue
                else:
                    # Single-page TOC — extract from current live DOM
                    try:
                        pw.wait_for_selector("li.toc_w", timeout=10_000)
                        single_soup = BeautifulSoup(pw.content(), "html.parser")
                        chapters_by_order.clear()
                        _extract_chapters(single_soup)
                        logger.info(
                            f"[SH] Single-page TOC — "
                            f"{len(chapters_by_order)} chapters extracted from live DOM."
                        )
                    except Exception as e:
                        logger.warning(f"[SH] Could not extract single-page TOC: {e}")

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
