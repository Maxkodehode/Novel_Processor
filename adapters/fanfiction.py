import re

from bs4 import BeautifulSoup

from .base import BaseAdapter


class FanFictionAdapter(BaseAdapter):
    HOSTS = ["fanfiction.net"]

    def parse(self, soup, url: str) -> dict:
        class FanFictionAdapter(BaseAdapter):
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
