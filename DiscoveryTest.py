"""
novel_scraper/scraper.py

Multi-site novel metadata + chapter-list scraper.
Supports: Royal Road, ScribbleHub, FanFiction.net
Each site is a self-contained "adapter" — add new sites by subclassing BaseAdapter.

Usage:
    python scraper.py <url> [--out results.json] [--use-local debug.html]
"""

import json
import re
import argparse
import os
from abc import ABC, abstractmethod
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


# ---------------------------------------------------------------------------
# Browser / fetch helpers
# ---------------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# Base adapter
# ---------------------------------------------------------------------------


class BaseAdapter(ABC):
    """
    Subclass this for each site.  Implement `parse(soup, url)` to return
    a normalised dict that matches the common schema below.

    Common output schema
    --------------------
    {
        "site":         str,          # e.g. "royalroad"
        "url":          str,
        "title":        str | None,
        "author":       str | None,
        "cover_url":    str | None,
        "status":       str | None,   # "ONGOING" | "COMPLETED" | "HIATUS" | None
        "tags":         list[str],
        "synopsis":     str | None,
        "language":     str | None,
        "scores":       dict,         # site-specific score keys → float
        "stats":        dict,         # views, followers, favourites, etc.
        "chapter_count": int | None,
        "chapters": [
            {
                "id":         str | int | None,
                "order":      int,            # 0-based
                "title":      str,
                "url":        str,
                "published":  str | None,     # ISO-8601
            }
        ]
    }
    """

    # Subclasses set this to a list of hostname substrings, e.g. ["royalroad.com"]
    HOSTS: list[str] = []

    @classmethod
    def matches(cls, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return any(h in host for h in cls.HOSTS)

    @abstractmethod
    def parse(self, soup: BeautifulSoup, url: str) -> dict: ...

    # ---- shared helpers ----

    @staticmethod
    def _text(tag) -> str | None:
        return tag.get_text(strip=True) if tag else None

    @staticmethod
    def _abs(href: str, base: str) -> str:
        if href.startswith("http"):
            return href
        p = urlparse(base)
        return f"{p.scheme}://{p.netloc}{href}"


# ---------------------------------------------------------------------------
# Royal Road adapter
# ---------------------------------------------------------------------------


class RoyalRoadAdapter(BaseAdapter):
    HOSTS = ["royalroad.com"]

    def parse(self, soup: BeautifulSoup, url: str) -> dict:
        # --- Title & author ---
        title = self._text(soup.select_one("h1.font-white"))
        author_tag = soup.select_one("h4 a.font-white") or soup.select_one(
            "a[href^='/profile/']"
        )
        author = self._text(author_tag)

        # --- Cover ---
        cover = soup.select_one("img[data-type='cover']")
        cover_url = cover["src"] if cover else None

        # --- Tags ---
        tags = [self._text(a) for a in soup.select("a.fiction-tag")]

        # --- Status (from label spans) ---
        status = None
        for span in soup.select("span.label.label-default"):
            t = self._text(span).upper()
            if t in ("COMPLETED", "ONGOING", "HIATUS", "STUB"):
                status = t
                break

        # --- Synopsis ---
        syn_div = soup.select_one("div.description div.hidden-content")
        synopsis = syn_div.get_text(separator="\n", strip=True) if syn_div else None

        # --- Scores ---
        scores = {}
        for label in (
            "Overall Score",
            "Style Score",
            "Story Score",
            "Grammar Score",
            "Character Score",
        ):
            span = soup.find("span", attrs={"data-original-title": label})
            if span:
                m = re.search(r"([\d.]+)\s*/\s*5", span.get("data-content", ""))
                if m:
                    key = label.replace(" Score", "").lower()
                    scores[key] = float(m.group(1))
        meta = soup.find("meta", {"property": "books:rating:value"})
        if meta:
            scores["overall_meta"] = float(meta["content"])

        # --- Stats ---
        # The stats div has two columns: left=scores (star widgets), right=view counts.
        # We target only the right column to avoid star-widget label/value noise.
        stats = {}
        stats_div = soup.select_one("div.fiction-stats")
        if stats_div:
            cols = stats_div.select("div.col-sm-6")
            stat_col = cols[1] if len(cols) > 1 else stats_div
            lis = stat_col.select("li.bold.uppercase")
            # Pairs: label-li then value-li (alternating)
            for i in range(0, len(lis) - 1, 2):
                label = lis[i].get_text(strip=True).rstrip(" :")
                value = lis[i + 1].get_text(strip=True)
                if label and value:
                    key = label.lower().replace(" ", "_")
                    stats[key] = value

            # word count from tooltip
            icon = stats_div.select_one("i.popovers[data-content]")
            if icon:
                m = re.search(r"from\s+([\d,]+)\s+words", icon.get("data-content", ""))
                if m:
                    stats["word_count"] = m.group(1)

        # --- Chapter count label ---
        count_span = soup.select_one("span.label.label-default.pull-right")
        chapter_count = None
        if count_span:
            m = re.search(r"(\d+)\s+Chapters?", count_span.get_text())
            if m:
                chapter_count = int(m.group(1))

        # --- Full chapter list from embedded JSON (window.chapters = [...]) ---
        # RR injects ALL chapters into a <script> block - no pagination needed.
        chapters = []
        for script in soup.find_all("script"):
            text = script.string or ""
            m = re.search(r"window\.chapters\s*=\s*(\[.*?\]);", text, re.DOTALL)
            if m:
                try:
                    raw = json.loads(m.group(1))
                    for entry in raw:
                        chapters.append(
                            {
                                "id": entry.get("id"),
                                "order": entry.get("order", 0),
                                "title": entry.get("title", ""),
                                "url": self._abs(entry.get("url", ""), url),
                                "published": entry.get("date"),
                            }
                        )
                except json.JSONDecodeError:
                    pass
                break

        # Fallback: parse the visible table rows if the script block wasn't found
        if not chapters:
            for i, row in enumerate(soup.select("tr.chapter-row")):
                link = row.select_one("td a[href]")
                time_tag = row.select_one("time")
                if link:
                    chapters.append(
                        {
                            "id": None,
                            "order": i,
                            "title": self._text(link),
                            "url": self._abs(link["href"], url),
                            "published": time_tag["datetime"] if time_tag else None,
                        }
                    )

        return {
            "site": "royalroad",
            "url": url,
            "title": title,
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


# ---------------------------------------------------------------------------
# ScribbleHub adapter
# ---------------------------------------------------------------------------


class ScribbleHubAdapter(BaseAdapter):
    """
    ScribbleHub fiction page: https://www.scribblehub.com/series/<id>/<slug>/

    The TOC is paginated at ?toc=N in the HTML itself (15 chapters/page by default).
    We navigate Playwright through each page and scrape chapters from the DOM.
    No AJAX endpoint is used — it is protected by Cloudflare's managed challenge.

    Each li.toc_w carries an `order` attribute (descending from total down to 1),
    which we use directly so ordering is correct even if pages load out of sequence.
    """

    HOSTS = ["scribblehub.com"]

    # Playwright page reference — injected by scrape() for live fetches
    _pw_page = None

    def parse(self, soup: BeautifulSoup, url: str) -> dict:
        # ── Basic metadata ──────────────────────────────────────────────────
        title = self._text(soup.select_one("div.fic_title"))
        author = self._text(soup.select_one("span.auth_name_fic"))
        cover = soup.select_one("div.fic_image img")
        cover_url = cover["src"] if cover else None

        # Tags / genres
        tags = [self._text(a) for a in soup.select("a.fic_genre")]
        tags += [self._text(a) for a in soup.select("a.stag")]
        tags = [t for t in tags if t]

        # Status — SH uses span classes like ss-completed, ss-ongoing, ss-hiatus
        status = None
        status_tag = soup.select_one(
            "span.ss-completed, span.ss-ongoing, span.ss-hiatus"
        )
        if status_tag:
            status = status_tag.get_text(strip=True).upper()

        # Synopsis
        syn = soup.select_one("div.wi_fic_desc")
        synopsis = syn.get_text(separator="\n", strip=True) if syn else None

        # Stats (views, favourites, etc.)
        stats = {}
        for item in soup.select("div.widget_fic_similar li"):
            spans = item.select("span")
            if len(spans) >= 2:
                k = spans[0].get_text(strip=True).lower().replace(" ", "_").rstrip(":")
                v = spans[1].get_text(strip=True)
                stats[k] = v

        # Rating score
        scores = {}
        rating_tag = soup.select_one("span#ratig-count")
        if rating_tag:
            try:
                scores["overall"] = float(rating_tag.get_text(strip=True))
            except ValueError:
                pass

        # Story ID from URL
        story_id = None
        m = re.search(r"/series/(\d+)/", url)
        if m:
            story_id = m.group(1)

        # ── Chapter count ───────────────────────────────────────────────────
        # SH uses <span class="cnt_toc">  (class, NOT id)
        chapter_count = None
        cnt_tag = soup.select_one("span.cnt_toc")
        if cnt_tag:
            try:
                chapter_count = int(cnt_tag.get_text(strip=True).replace(",", ""))
            except ValueError:
                pass

        # ── Last TOC page number ────────────────────────────────────────────
        last_page = 1
        for a in soup.select("ul#pagination-mesh-toc a.page-link"):
            txt = a.get_text(strip=True)
            if txt.isdigit():
                last_page = max(last_page, int(txt))

        # ── Chapter scraping ────────────────────────────────────────────────
        # Parse page 1 chapters from the already-loaded soup
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

            # ── Step 1: Set display to 50 chapters/page via the dropdown ──────
            # This triggers toc_chapter() JS in-page — no navigation, no CF check.
            # With 50/page and 134 chapters we need 3 pages instead of 9.
            try:
                pw.select_option("select#show_chapters", value="50")
                # Wait for the TOC list to repopulate with more items
                pw.wait_for_function(
                    "document.querySelectorAll('li.toc_w').length > 15", timeout=10_000
                )
                # Re-read page 1 with 50 chapters and recalculate pagination
                page1_soup = BeautifulSoup(pw.content(), "html.parser")
                chapters_by_order.clear()
                _extract_chapters(page1_soup)

                # Recalculate last_page after the count change
                new_last = 1
                for a in page1_soup.select("ul#pagination-mesh-toc a.page-link"):
                    txt = a.get_text(strip=True)
                    if txt.isdigit():
                        new_last = max(new_last, int(txt))
                last_page = new_last
                print(f"    [SH] Display set to 50/page — {last_page} pages to fetch")
            except Exception as e:
                print(f"    [SH] Could not set display count: {e}")

            # ── Step 2: Click pagination links in-page (stays in JS session) ──
            # page.goto() triggers a full reload → Cloudflare challenge.
            # Clicking the <a> elements fires wi_getreleases_pagination() via JS
            # which swaps TOC content in-place without a navigation event.
            for page_num in range(2, last_page + 1):
                print(f"    [SH] TOC page {page_num}/{last_page} …")
                try:
                    # Find and click the page number link in the pagination bar
                    clicked = pw.evaluate(f"""
                        (() => {{
                            const links = document.querySelectorAll('ul#pagination-mesh-toc a.page-link');
                            for (const a of links) {{
                                if (a.textContent.trim() === '{page_num}') {{
                                    a.click();
                                    return true;
                                }}
                            }}
                            // If not visible (ellipsis hid it), find the next » arrow
                            const next = document.querySelector('ul#pagination-mesh-toc a.page-link.next');
                            if (next) {{ next.click(); return 'next'; }}
                            return false;
                        }})()
                    """)
                    if not clicked:
                        print(
                            f"    [SH] Page {page_num} link not found in pagination bar, stopping"
                        )
                        break

                    # Wait for TOC list to update — watch for the active page indicator
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
                    # Small settle wait for the list items to finish rendering
                    pw.wait_for_timeout(500)
                    page_soup = BeautifulSoup(pw.content(), "html.parser")
                    _extract_chapters(page_soup)

                except Exception as e:
                    print(f"    [SH] Warning: page {page_num} failed ({e}), skipping")
                    continue

        elif last_page > 1:
            print(
                f"[!] Warning: {chapter_count} chapters across {last_page} pages, "
                "but only page 1 loaded (--use-local mode). Run live to fetch all."
            )

        # Sort by SH order attribute (descending = newest first), then re-index 0-based
        # SH order goes from total down to 1; order=1 is chapter 1
        chapters = sorted(chapters_by_order.values(), key=lambda c: c["order"])
        for i, ch in enumerate(chapters):
            ch["order"] = i  # re-index to 0-based ascending

        return {
            "site": "scribblehub",
            "url": url,
            "title": title,
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


# ---------------------------------------------------------------------------
# FanFiction.net adapter
# ---------------------------------------------------------------------------


class FanFictionAdapter(BaseAdapter):
    """
    FanFiction.net story page:
      https://www.fanfiction.net/s/<story_id>/<chapter>/<slug>/

    FF.net injects a StoryParser JS object with all metadata and the full
    chapter list.  We parse that first; HTML is a fallback.
    """

    HOSTS = ["fanfiction.net", "www.fanfiction.net"]

    # Map FF.net genre IDs → names (subset; extend as needed)
    _GENRE_MAP = {
        "1": "Adventure",
        "2": "Angst",
        "3": "Comedy",
        "4": "Crime",
        "5": "Drama",
        "6": "Family",
        "7": "Fantasy",
        "8": "Friendship",
        "9": "General",
        "10": "Horror",
        "11": "Humor",
        "12": "Hurt/Comfort",
        "13": "Mystery",
        "14": "Parody",
        "15": "Poetry",
        "16": "Romance",
        "17": "Sci-Fi",
        "18": "Spiritual",
        "19": "Supernatural",
        "20": "Suspense",
        "21": "Tragedy",
        "22": "Western",
    }

    def parse(self, soup: BeautifulSoup, url: str) -> dict:
        # --- Extract embedded JS metadata ---
        # FF.net sets `var storyid = <N>;` in a script block on every story page.
        meta = {}
        for script in soup.find_all("script"):
            text = script.string or ""
            # Prefer the explicit `var storyid` declaration
            m = re.search(r"var\s+storyid\s*=\s*(\d+)", text)
            if m:
                meta["story_id"] = m.group(1)
                break
            # Fallback: bare `storyid = N` (inside object literals etc.)
            m = re.search(r"storyid\s*[=:]\s*(\d+)", text)
            if m and "story_id" not in meta:
                meta["story_id"] = m.group(1)

        # --- HTML fallback metadata from the #profile_top block ---
        profile = soup.select_one("div#profile_top")
        title = self._text(profile.select_one("b.xcontrast_txt") if profile else None)
        author_tag = profile.select_one("a.xcontrast_txt") if profile else None
        author = self._text(author_tag)

        cover = soup.select_one("img.cimage")
        cover_url = cover["src"] if cover else None
        if cover_url and not cover_url.startswith("http"):
            cover_url = "https:" + cover_url

        # Synopsis
        syn = profile.select_one("div.xcontrast_txt") if profile else None
        synopsis = self._text(syn)

        # Stats span — FF.net packs everything into one <span class="xgray xcontrast_txt">
        stats = {}
        scores = {}
        tags = []
        status = None
        language = None
        chapter_count = None

        stats_span = profile.select_one("span.xgray") if profile else None
        if stats_span:
            raw = stats_span.get_text(" ", strip=True)

            # Numeric stats via regex
            for pat, key in [
                (r"Words:\s*([\d,]+)", "words"),
                (r"Reviews:\s*([\d,]+)", "reviews"),
                (r"Favs:\s*([\d,]+)", "favourites"),
                (r"Follows:\s*([\d,]+)", "followers"),
                (r"Chapters:\s*(\d+)", "chapter_count_raw"),
            ]:
                m = re.search(pat, raw, re.I)
                if m:
                    stats[key] = m.group(1)

            m = re.search(r"Chapters:\s*(\d+)", raw, re.I)
            if m:
                chapter_count = int(m.group(1))

            # Rating — FF.net wraps it in <a>Fiction  T</a>, so grab from the link text
            rating_tag = stats_span.select_one("a[href*='fictionratings']")
            if rating_tag:
                # "Fiction  T" → "T"
                rating_text = rating_tag.get_text(strip=True).split()[-1]
                stats["rating"] = rating_text

            # Parse the dash-separated segments for language and genres.
            # Format: "Rated: Fiction T - English - Fantasy/Adventure - Characters..."
            # Strip the "Rated: ..." prefix first, then split on " - "
            rated_prefix = re.sub(r"^Rated:.*?-\s*", "", raw, count=1).strip()
            segments = [s.strip() for s in rated_prefix.split(" - ") if s.strip()]

            # First segment after Rated is language (plain word like "English")
            if (
                segments
                and re.match(r"^[A-Za-z][\w ]*$", segments[0])
                and ":" not in segments[0]
            ):
                language = segments[0]
                segments = segments[1:]

            # Next segment(s) before a known keyword are genres (contain "/" or single word genres)
            genre_segments = []
            for seg in segments:
                # Stop when we hit stats-like content ("Chapters:", character names with ".")
                if re.search(
                    r"Chapters:|Words:|Reviews:|Favs:|Follows:|Updated:|Published:|id:",
                    seg,
                    re.I,
                ):
                    break
                if re.match(r"^[A-Z][\w/& ]+$", seg) and "." not in seg:
                    genre_segments.append(seg)
                else:
                    break
            for gs in genre_segments:
                tags += [g.strip() for g in gs.split("/") if g.strip()]

            # Status
            if "Complete" in raw and "Updated" not in raw.split("Complete")[0]:
                status = "COMPLETED"
            elif "Updated" in raw or "In-Progress" in raw:
                status = "ONGOING"

        # --- Chapter list ---
        # FF.net uses a <select#chap_select> dropdown with all chapter names
        chapters = []
        # story_id from JS is most reliable; fall back to URL
        story_id = meta.get("story_id")
        if not story_id:
            m2 = re.search(r"/s/(\d+)/", url)
            story_id = m2.group(1) if m2 else None

        chap_select = soup.select_one("select#chap_select")
        if chap_select:
            for opt in chap_select.select("option"):
                idx = int(opt["value"])  # 1-based chapter number
                chapters.append(
                    {
                        "id": idx,
                        "order": idx - 1,
                        "title": opt.get_text(strip=True),
                        "url": f"https://www.fanfiction.net/s/{story_id}/{idx}/",
                        "published": None,  # FF.net doesn't expose per-chapter dates
                    }
                )
        elif chapter_count and story_id:
            # No select found (single-chapter fic or not rendered) — build URLs
            chapters = [
                {
                    "id": i + 1,
                    "order": i,
                    "title": f"Chapter {i + 1}",
                    "url": f"https://www.fanfiction.net/s/{story_id}/{i + 1}/",
                    "published": None,
                }
                for i in range(chapter_count)
            ]

        return {
            "site": "fanfiction",
            "url": url,
            "title": title,
            "author": author,
            "cover_url": cover_url,
            "status": status,
            "tags": tags,
            "synopsis": synopsis,
            "language": language,
            "scores": scores,
            "stats": stats,
            "chapter_count": chapter_count or len(chapters),
            "chapters": chapters,
        }


# ---------------------------------------------------------------------------
# Registry & dispatcher
# ---------------------------------------------------------------------------

ADAPTERS: list[type[BaseAdapter]] = [
    RoyalRoadAdapter,
    ScribbleHubAdapter,
    FanFictionAdapter,
]


def get_adapter(url: str) -> BaseAdapter:
    for cls in ADAPTERS:
        if cls.matches(url):
            return cls()
    raise ValueError(
        f"No adapter found for URL: {url}\n"
        f"Supported hosts: {[h for cls in ADAPTERS for h in cls.HOSTS]}"
    )


def scrape(
    url: str, use_local: str | None = None, save_html: str | None = None
) -> dict:
    """Main entry point. Returns the normalised metadata dict."""
    adapter = get_adapter(url)
    print(f"[*] Using adapter: {type(adapter).__name__}")

    if use_local and os.path.exists(use_local):
        # Local debug mode — no AJAX available
        print(f"[*] Reading local HTML: {use_local}")
        with open(use_local, "r", encoding="utf-8") as f:
            html = f.read()
        soup = BeautifulSoup(html, "html.parser")
        return adapter.parse(soup, url)

    # Live fetch — keep the browser open so adapters can make in-session AJAX calls
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=USER_AGENT)
        page = ctx.new_page()
        print(f"[*] Fetching {url} …")
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        # Wait for any key content element — avoids scraping a half-loaded page
        try:
            page.wait_for_selector(
                "li.toc_w, div.fiction-stats, div#profile_top", timeout=15_000
            )
        except Exception:
            pass  # proceed anyway; adapter will handle missing elements gracefully

        # Dismiss cookie banners
        for label in ("Accept", "Accept All", "I Agree", "OK"):
            try:
                btn = page.get_by_role("button", name=label)
                if btn.is_visible():
                    btn.click()
                    page.wait_for_timeout(1500)
                    break
            except Exception:
                pass

        html = page.content()
        if save_html:
            with open(save_html, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"[*] HTML saved to {save_html}")

        soup = BeautifulSoup(html, "html.parser")

        # Inject the live page into adapters that need in-session AJAX calls
        if hasattr(adapter, "_pw_page"):
            adapter._pw_page = page

        result = adapter.parse(soup, url)
        browser.close()
        return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Multi-site novel scraper")
    parser.add_argument("url", help="Fiction landing page URL")
    parser.add_argument(
        "--out", default="output.json", help="Output JSON file (default: output.json)"
    )
    parser.add_argument(
        "--use-local", metavar="FILE", help="Use a local HTML file instead of fetching"
    )
    parser.add_argument(
        "--save-html",
        metavar="FILE",
        help="Save fetched HTML to this file for debugging",
    )
    args = parser.parse_args()

    result = scrape(args.url, use_local=args.use_local, save_html=args.save_html)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, ensure_ascii=False)

    print(f"\n[✓] Saved to {args.out}")
    print(f"    Title    : {result.get('title')}")
    print(f"    Author   : {result.get('author')}")
    print(f"    Status   : {result.get('status')}")
    print(f"    Tags     : {result.get('tags')}")
    print(
        f"    Chapters : {result.get('chapter_count')} total, {len(result.get('chapters', []))} fetched"
    )


if __name__ == "__main__":
    main()
