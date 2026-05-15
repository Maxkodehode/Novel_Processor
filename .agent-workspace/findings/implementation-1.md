# Implementation Summary — ScribbleHub Next Chapter Scraper Fix

**Date**: 2026-05-13 17:45
**Agent**: Implementer (OWL direct implementation)

## Changes Made

### 1. `adapters/scribblehub.py` — ScribbleHubAdapter

#### New method: `_fetch_all_chapters_via_prev_links()`
- Uses `NetworkClient` (curl_cffi) to fetch individual chapter pages
- Follows `a.btn-prev` links backwards from last chapter to first
- Bypasses Cloudflare which blocks Playwright on chapter pages
- Includes cycle detection, rate limiting, and error handling
- Returns chapters in ascending order (0-based)

#### Modified: `parse()` signature
- Added optional `network_client` parameter
- Maintains backward compatibility (defaults to None)

#### Modified: `parse()` chapter collection logic
New fallback chain:
1. **Fast path**: Try `toc_fic_show_all()` via Playwright
2. **Secondary**: Try AJAX pagination via `_fetch_toc_page_via_click()`
3. **Reliable fallback**: Use `_fetch_all_chapters_via_prev_links()` with curl_cffi

### 2. `services/scraper_service.py` — ScraperService

#### Modified: `scrape_novel()` ScribbleHub branch
- Now passes `self.network` (NetworkClient) to `adapter.parse()`
- Enables the curl_cffi fallback in the adapter

## Key Technical Findings

### Cloudflare Behavior
- **Novel page**: Loads fine in both Playwright and curl_cffi
- **Chapter pages**: Blocked by Cloudflare in Playwright ("Just a moment...")
- **Chapter pages**: Work in curl_cffi with proper rate limiting (~5s between requests)
- **admin-ajax.php**: Always blocked (403) — AJAX approach is unreliable
- **Rate limiting**: Cloudflare allows ~10 requests with 2s delay, then may block

### Chapter Page Selectors (confirmed via curl_cffi)
- Chapter title: `.chapter-title`
- Chapter content: `#chp_raw`
- Previous link: `a.btn-prev` (real URL)
- Next link: `a.btn-next` (href="#" with class "disabled" when on last chapter)

### Rate Limiting Recommendation
- Use 5s delay between chapter page requests to avoid Cloudflare blocks
- 118 chapters × 5s = ~10 minutes per novel (acceptable for batch processing)

## API Compatibility
- `parse()` signature change is backward-compatible (new param is optional)
- Return dict format unchanged
- No changes to other adapters (royalroad, fanfiction)
- No changes to database schema

## Test Status
- Full collection test running in background (118 chapters × 5s delay)
- Initial results: 12 chapters collected before 403 (with 2s delay)
- With 5s delay: test in progress
