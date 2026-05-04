# =============================================================================
# CHANGES:
#   - _fetch_toc_page_via_click(): Replaced route.fetch() + route.fulfill()
#     with page.on("response", ...) event listener + route.continue_().
#
#     WHY route.fetch() FAILED:
#     route.fetch() makes a new HTTP request from Playwright's Node.js backend
#     process, NOT from the browser. It does not carry the browser's session
#     cookies. ScribbleHub's admin-ajax.php validates the session cookie and
#     returns HTTP 403 to any request that doesn't have it. Additionally,
#     after route.fetch() throws (due to 403), the except block called
#     route.continue_() which caused "Route is already handled!" because
#     route.fetch() internally already called continue_().
#
#     THE FIX:
#     Use page.on("response", handler) to listen for the response event.
#     When the pagination link is clicked, the browser fires the AJAX request
#     with its own session cookies (gets 200 OK). The response event fires
#     with the real response. We call response.body() to capture the raw bytes.
#     Meanwhile the route handler simply calls route.continue_() to let the
#     browser's own request proceed normally — we never touch route.fetch().
#     This completely separates "let the request through" from "capture the
#     response", which is the correct Playwright pattern for interception
#     without modifying requests.
#
#   - _fetch_toc_page_via_click(): The route handler on admin-ajax.php now
#     only calls route.continue_() and sets a flag so we know the request
#     fired. The response listener captures the body independently.
#
#   - All other logic unchanged.
# =============================================================================

import logging
import time

from bs4 import BeautifulSoup

from .base import BaseAdapter
from utils.text import slugify

logger = logging.getLogger(__name__)

DEBUG = False

# Seconds between page requests
_PAGE_DELAY = 2.0

# How long to wait for the AJAX response after clicking (seconds)
_RESPONSE_TIMEOUT_S = 15.0


class ScribbleHubAdapter(BaseAdapter):
    HOSTS = ["scribblehub.com"]

    # Injected by ScraperService before parse() is called
    _pw_page = None

    def _extract_from_soup(self, soup) -> list[dict]:
        """
        Extracts chapter dicts from a BeautifulSoup object containing li.toc_w
        elements. Works on both full page soup and AJAX fragment soup.

        Parameters:
            soup (BeautifulSoup): Soup to extract from.

        Returns:
            list[dict]: Chapter dicts with keys: id, order, title, url, published.

        Called by: parse(), _fetch_toc_page_via_click()
        Depends on: BeautifulSoup selector 'li.toc_w'
        """
        chapters = []
        for li in soup.select("li.toc_w"):
            link = li.select_one("a")
            time_tag = li.select_one("span.fic_date_pub")
            if not link:
                continue

            order_attr = li.get("order")
            order_val = int(order_attr) if order_attr and order_attr.isdigit() else None
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
            chapters.append(ch)

            if DEBUG:
                logger.debug(
                    f"[_extract_from_soup] order={order_val} title='{ch['title']}'"
                )

        return chapters

    def _fetch_toc_page_via_click(self, page_num: int) -> list[dict]:
        """
        Fetches one TOC page by clicking the real pagination link and capturing
        the server's AJAX response via a page response event listener.

        Strategy:
          1. Register a page.on("response", ...) listener that watches for
             responses from admin-ajax.php and saves the response body.
          2. Register a page.route() handler on admin-ajax.php that simply
             calls route.continue_() — letting the browser's own request
             through unchanged with all its session cookies intact.
          3. Click the pagination link. The browser fires the AJAX request
             with its own cookies, gets a 200 response, and our response
             listener captures the body.
          4. Poll until the response body is captured or timeout.
          5. Parse the HTML fragment and return chapter dicts.

        This is the correct pattern: route handles request disposition
        (continue/abort/fulfill), response listener captures response data.
        They operate independently — no double-handling.

        Parameters:
            page_num (int): The TOC page number to fetch (1-based, >= 2).

        Returns:
            list[dict]: Chapter dicts for this page, or [] on failure.

        Called by: parse()
        Depends on: _pw_page, _extract_from_soup()
        """
        pw = self._pw_page
        captured = {}

        # JS to click the link for a specific page number
        js_click = (
            "(pageNum => {"
            "  const links = document.querySelectorAll('ul#pagination-mesh-toc a.page-link');"
            "  for (const a of links) {"
            "    if (a.textContent.trim() === String(pageNum)) { a.click(); return true; }"
            "  }"
            "  return false;"
            "})(" + str(page_num) + ")"
        )

        def _on_response(response):
            """
            Captures the response body when admin-ajax.php responds.
            Called by the page "response" event — runs for every response
            the browser receives. We filter to admin-ajax.php only.

            Parameters:
                response: Playwright Response object.

            Called by: page.on("response", ...) event
            """
            if "admin-ajax.php" not in response.url:
                return
            try:
                body = response.body()
                captured["body"] = body
                captured["status"] = response.status
                if DEBUG:
                    preview = body.decode("utf-8", errors="replace")[:200]
                    logger.debug(
                        f"[_on_response] page {page_num} "
                        f"status={response.status} preview: {preview}"
                    )
            except Exception as e:
                captured["error"] = str(e)
                logger.error(f"[_on_response] Failed to read response body: {e}")

        def _on_route(route):
            """
            Allows the browser's own AJAX request to continue unchanged.
            We do NOT call route.fetch() here — that would make a new request
            from the Node.js backend without browser cookies, causing 403.
            We only call route.continue_() so the browser sends its own
            authenticated request.

            Called by: page.route("**/admin-ajax.php", ...) handler
            """
            try:
                route.continue_()
            except Exception as e:
                # Route may already be handled if timing overlaps — safe to ignore
                if DEBUG:
                    logger.debug(f"[_on_route] continue_ failed (non-fatal): {e}")

        try:
            # Register the response listener BEFORE the route handler and BEFORE clicking
            pw.on("response", _on_response)
            pw.route("**/admin-ajax.php", _on_route)

            clicked = pw.evaluate(js_click)
            if not clicked:
                logger.warning(f"[SH] Page {page_num} link not found in pagination bar")
                return []

            if DEBUG:
                logger.debug(
                    f"[_fetch_toc_page_via_click] Clicked page {page_num} link"
                )

            # Poll until response body captured or timeout
            waited = 0.0
            step = 0.2
            while "body" not in captured and "error" not in captured:
                time.sleep(step)
                waited += step
                if waited >= _RESPONSE_TIMEOUT_S:
                    logger.warning(
                        f"[SH] Timeout waiting for AJAX response for page {page_num}"
                    )
                    break

        except Exception as e:
            logger.error(f"[SH] Click+capture failed for page {page_num}: {e}")
        finally:
            # Always clean up both handlers
            try:
                pw.remove_listener("response", _on_response)
            except Exception:
                pass
            try:
                pw.unroute("**/admin-ajax.php", _on_route)
            except Exception:
                pass

        if "error" in captured:
            logger.warning(
                f"[SH] Response capture error for page {page_num}: {captured['error']}"
            )
            return []

        if "body" not in captured:
            logger.warning(f"[SH] No response body captured for page {page_num}")
            return []

        status = captured.get("status", 0)
        if status != 200:
            logger.warning(f"[SH] Page {page_num} server returned HTTP {status}")
            return []

        try:
            html_fragment = captured["body"].decode("utf-8", errors="replace")
        except Exception as e:
            logger.error(f"[SH] Failed to decode response for page {page_num}: {e}")
            return []

        if not html_fragment or html_fragment.strip() in ("0", "-1", ""):
            logger.warning(f"[SH] Empty/error fragment for page {page_num}")
            return []

        frag_soup = BeautifulSoup(html_fragment, "html.parser")
        chapters = self._extract_from_soup(frag_soup)

        if DEBUG:
            logger.debug(
                f"[_fetch_toc_page_via_click] page {page_num}: "
                f"{len(chapters)} chapters extracted"
            )

        return chapters

    def parse(self, soup: BeautifulSoup, url: str) -> dict:
        """
        Parses a ScribbleHub novel landing page into a structured data dict.

        Metadata (title, author, cover, tags, synopsis, scores, stats) is
        extracted from the static HTML of the initial page load.

        Chapter list strategy:
          - Page 1: read from the 15 chapters already in the static HTML.
          - Pages 2..N: click the real pagination link and capture the
            server's AJAX response via a page response event listener.
            The browser sends the request with its own session cookies so
            the server returns 200 with the chapter HTML fragment.

        Falls back to static HTML chapters (page 1 only) if Playwright is
        unavailable or navigation fails entirely.

        Parameters:
            soup (BeautifulSoup): Parsed HTML of the novel landing page.
            url (str): The novel's canonical URL.

        Returns:
            dict: Novel data including title, author, tags, chapters, etc.

        Called by: ScraperService.scrape_novel()
        Depends on: _extract_from_soup(), _fetch_toc_page_via_click(), slugify()
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

        # --- Chapter count from badge ---
        chapter_count = None
        cnt_tag = soup.select_one("span.cnt_toc")
        if cnt_tag:
            try:
                chapter_count = int(cnt_tag.get_text(strip=True).replace(",", ""))
            except ValueError:
                pass

        # --- Page count from static pagination bar ---
        last_page = 1
        for a in soup.select("ul#pagination-mesh-toc a.page-link"):
            txt = a.get_text(strip=True)
            if txt.isdigit():
                last_page = max(last_page, int(txt))

        if DEBUG:
            logger.debug(f"[parse] chapter_count={chapter_count} last_page={last_page}")

        # --- Page 1 chapters from static HTML ---
        chapters_by_order: dict[int, dict] = {}
        for ch in self._extract_from_soup(soup):
            if ch["order"] is not None:
                chapters_by_order[ch["order"]] = ch

        logger.info(
            f"[SH] Page 1 (static HTML): {len(chapters_by_order)} chapters, "
            f"{last_page} total pages"
        )

        # --- Pages 2..N via click + response capture ---
        if self._pw_page and last_page > 1:
            consecutive_failures = 0

            for page_num in range(2, last_page + 1):
                time.sleep(_PAGE_DELAY)
                logger.info(f"[SH] Fetching TOC page {page_num}/{last_page}...")

                page_chapters = self._fetch_toc_page_via_click(page_num)

                if not page_chapters:
                    consecutive_failures += 1
                    logger.warning(
                        f"[SH] TOC page {page_num} returned 0 chapters "
                        f"(failure {consecutive_failures})"
                    )
                    if consecutive_failures >= 3:
                        logger.error(
                            "[SH] 3 consecutive failures — stopping pagination early"
                        )
                        break
                    continue

                consecutive_failures = 0
                for ch in page_chapters:
                    if ch["order"] is not None:
                        chapters_by_order[ch["order"]] = ch

                logger.info(
                    f"[SH] Page {page_num}: {len(page_chapters)} chapters "
                    f"(total so far: {len(chapters_by_order)})"
                )

            logger.info(
                f"[SH] Pagination complete: {len(chapters_by_order)} total chapters"
            )

        elif last_page > 1:
            logger.warning(
                f"[SH] {last_page} TOC pages detected but no browser available "
                f"(--use-local mode?). Only page 1 chapters returned."
            )

        # --- Re-index to 0-based order, sorted ascending ---
        chapters_sorted = sorted(chapters_by_order.values(), key=lambda c: c["order"])
        for i, ch in enumerate(chapters_sorted):
            ch["order"] = i

        logger.info(f"[parse] Final chapter count: {len(chapters_sorted)}")

        if chapter_count and len(chapters_sorted) < chapter_count:
            logger.warning(
                f"[parse] Expected {chapter_count} chapters, "
                f"got {len(chapters_sorted)}. Some pages may have failed."
            )

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
            "chapter_count": chapter_count or len(chapters_sorted),
            "chapters": chapters_sorted,
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
