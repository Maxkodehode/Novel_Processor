# Knowledge: ScribbleHub-Specific Intelligence

Project-specific knowledge about ScribbleHub's structure, behavior, and quirks.
ANY agent may APPEND to this file. Do not modify existing entries.

## DOM Structure

- Chapter list items: `li.toc_w` (each contains `a.toc_a` for title/URL)
- Chapter count badge: `span.cnt_toc`
- Pagination container: `ul#pagination-mesh-toc`
- Pagination links: `ul#pagination-mesh-toc a.page-link`
- Chapter content: `#chp_raw`
- "Show All" JS function: `toc_fic_show_all()` (global, defined in page JS)

## AJAX

- Endpoint: `https://www.scribblehub.com/wp-admin/admin-ajax.php`
- Action parameter: `tr_grabber`
- Pagination: `paged=N` parameter
- Response format: HTML fragment containing `li.toc_w` elements

## Behavior

- Initial page load: ~15 chapters in static HTML
- `toc_fic_show_all()`: Loads all chapters via AJAX, replaces/appends to `li.toc_w` container
- Pagination click: Fetches that page's chapters via AJAX
- The DOM is updated (not replaced) when chapters load — `li.toc_w` count increases

## Cloudflare Protection (CRITICAL)

ScribbleHub uses Cloudflare bot protection that blocks automated scraping:

- `admin-ajax.php` returns HTTP 403 — even with `route.continue_()`, Cloudflare detects automated browser behavior
- External JS files (e.g., `simplePagination` from CDN) fail to load
- `toc_fic_show_all()` internally calls `admin-ajax.php` → also blocked
- Only ~15 chapters exist in static HTML; everything else requires JS/AJAX which is blocked
- **Workaround:** Use "Next Chapter" link navigation (`page.goto()`) instead of AJAX

## Next Chapter Navigation

- Start at Chapter 1 URL (from `li.toc_w:first-child a.toc_a`)
- Each chapter page has a "Next Chapter" link: `a.chp_next`, `a#c2`, or `a:has-text("Next Chapter")`
- Chapter content is in `#chp_raw`
- Navigate: `page.goto(chapter_url)` → wait for `#chp_raw` → extract → find next link → repeat
- Stop when no "Next Chapter" link exists

## Test Novels

| Novel | URL | Expected Chapters |
|-------|-----|-------------------|
| Primary | https://www.scribblehub.com/series/1857436/ | 118 |
| Small | (to be populated by diagnostician) | ~15-30 |
| Medium | (to be populated by diagnostician) | ~50-80 |
| Large | (to be populated by diagnostician) | ~100+ |
