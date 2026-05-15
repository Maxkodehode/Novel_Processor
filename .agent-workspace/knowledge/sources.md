# Knowledge: Sources

Curated websites, documentation, and reference material discovered during agent iterations.
ANY agent may APPEND to this file. Do not modify existing entries.
Format: `- [DATE] [URL] — [what it contains] — discovered by [agent/iteration]`

## ScribbleHub

- [2026-05-13] https://www.scribblehub.com — Target website. Uses WordPress + custom JS for chapter loading. Key JS function: `toc_fic_show_all()`. AJAX endpoint: `admin-ajax.php` with `action=tr_grabber`. — discovered by OWL initial analysis

## Playwright

- [2026-05-13] https://playwright.dev/docs/api/class-page#page-event-response — `page.on("response")` event documentation. Use with `route.continue_()` instead of `route.fetch()` to preserve session cookies. — discovered by OWL initial analysis
- [2026-05-13] https://playwright.dev/docs/api/class-route#route-continue — `route.continue_()` docs. Does NOT carry browser session cookies when using `route.fetch()` — that's why `continue_()` is required for authenticated AJAX. — discovered by OWL initial analysis

## Web Scraping Patterns

- (add entries here as discovered)

## Python / Async

- (add entries here as discovered)
