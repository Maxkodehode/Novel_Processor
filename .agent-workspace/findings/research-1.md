# Research 1 — Chapter Page Navigation (CORRECTED)

**Date**: 2026-05-13 17:35

## Key Finding: curl_cffi works, Playwright doesn't

- **Playwright**: Chapter pages return "Just a moment..." (Cloudflare challenge)
- **curl_cffi**: Chapter pages load fine (200, full HTML)

## Chapter Page Structure (via curl_cffi)

### Chapter Title
- Selector: `.chapter-title` — works, returns "Chapter 118: The Trashing of Gravengrad"

### Chapter Content
- Selector: `#chp_raw` — works, 18795 chars on test page

### Navigation Links
- **Previous Chapter**: `<a class="btn-wi btn-prev" href="...chapter/PREV_ID/">`
  - Full URL: `https://www.scribblehub.com/read/1857436-the-rusting-robots-and-revenge/chapter/2319836/`
  - Selector: `a.btn-prev` (first one, there are duplicates)
- **Next Chapter**: `<a class="btn-wi btn-next disabled" href="#">`
  - When on the LAST chapter (118), Next is disabled with `href="#"`
  - When on earlier chapters, Next would have a real URL
  - Selector: `a.btn-next`

### Navigation Pattern
The Previous link always has a real URL. The Next link is `href="#"` with class `disabled` when on the last chapter. For earlier chapters, the Next link would have a real chapter URL.

## Strategy for Chapter-by-Chapter Scraping

Since Playwright can't load chapter pages (Cloudflare), but curl_cffi can:

1. **Use curl_cffi (NetworkClient) to fetch chapter pages**, not Playwright
2. Start from the novel page (which works in Playwright) to get chapter URLs
3. For each chapter URL, use `NetworkClient.get()` to fetch the page HTML
4. Parse with BeautifulSoup to extract title, content, and next/prev links
5. Follow the chain

### Alternative: Use Playwright only for novel page, curl_cffi for chapters
- Playwright: Load novel page → extract all chapter URLs from `li.toc_w`
- curl_cffi: Fetch each chapter page → extract content + next link

### But wait — we only get 15 chapter URLs from the novel page!
The novel page only has 15 `li.toc_w` elements. We need ALL chapter URLs.

### Revised Strategy: Follow Previous links from the last chapter
1. From the novel page, get the LAST chapter URL (highest order, e.g., chapter 118)
2. Fetch that chapter page with curl_cffi
3. Extract the Previous chapter link
4. Follow it to chapter 117, extract its Previous link, etc.
5. Stop when there's no Previous link (chapter 1)
6. Collect all chapter URLs in reverse order, then reverse

This gives us all chapter URLs without needing AJAX or pagination.

### Even Better: Use the chapter ID pattern
Chapter URLs follow the pattern:
`/read/1857436-the-rusting-robots-and-revenge/chapter/CHAPTER_ID/`

The chapter IDs are sequential-ish but not contiguous. We need to follow the chain.

## Recommended Implementation

Modify `ScribbleHubAdapter.parse()` to:
1. Try `toc_fic_show_all()` first (fast path, may work sometimes)
2. If that fails, use curl_cffi to follow Previous chapter links from the last chapter
3. Collect all chapter URLs, then fetch each one for content

The key insight: **use curl_cffi for chapter pages, Playwright only for the novel page**.
