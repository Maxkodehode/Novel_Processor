# Knowledge: Gotchas

Things that DON'T work and why. Learned through failed iterations.
ANY agent may APPEND to this file. Do not modify existing entries.
Format: `- [DATE] [ITERATION] — [what was tried] — [why it failed] — [what to do instead]`

## ScribbleHub

- [2026-05-13] OWL initial — `route.fetch()` for `admin-ajax.php` — Returns HTTP 403 because Playwright's Node.js backend makes the fetch without browser session cookies — Use `page.on("response")` + `route.continue_()` instead
- [2026-05-13] OWL initial — `block_resources=True` (default) with ScribbleHub — Installs a competing `**/*` route handler that consumes route events before the adapter's `**/admin-ajax.php` handler can fire, causing 15s timeouts — Pass `block_resources=False` for ScribbleHub
- [2026-05-13] OWL diagnosis — `admin-ajax.php` blocked by Cloudflare (403) — Even with `route.continue_()`, Cloudflare detects automated browser behavior and returns 403. Affects ALL AJAX approaches: `toc_fic_show_all()`, pagination clicks, direct `admin-ajax.php` calls — Use Next Chapter link navigation (`page.goto()`) instead
- [2026-05-13] OWL diagnosis — External JS files blocked by Cloudflare — `simplePagination` and other CDN-loaded JS fail to load in automated contexts. Pagination bar renders but is non-functional — Do not rely on external JS; use Next Chapter links
- [2026-05-13] OWL diagnosis — `toc_fic_show_all()` blocked — Internally calls `admin-ajax.php` which Cloudflare blocks — Treat as unreliable; use as fast-path only with Next Chapter fallback
- [2026-05-13] OWL research — Playwright can't load ScribbleHub chapter pages — Cloudflare returns "Just a moment..." challenge page for any chapter URL accessed via Playwright — Use curl_cffi (NetworkClient) instead of Playwright for chapter pages
- [2026-05-13] OWL research — Chapter page navigation selectors — Previous: `a.btn-prev` (real URL), Next: `a.btn-next` (href="#" with class "disabled" when on last chapter) — Use `a.btn-prev` to chain backwards from last chapter to first
- [2026-05-13] OWL research — Chapter title selector — `.chapter-title` works (not h1.text-title) — Use `.chapter-title` for chapter name

## Playwright

- (add entries here as discovered)

## Pagination

- (add entries here as discovered)

## DOM Timing

- (add entries here as discovered)
