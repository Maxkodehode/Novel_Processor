# Knowledge: Methods

Proven techniques and patterns discovered during agent iterations.
ANY agent may APPEND to this file. Do not modify existing entries.
Format: `- [DATE] [ITERATION] — [technique name] — [description with code example if applicable]`

## ScribbleHub Chapter Loading

### Method: Next Chapter Link Following (RELIABLE — bypasses Cloudflare)
```python
# Start from first chapter URL (from li.toc_w:first-child a.toc_a)
# Or from the novel's TOC page, extract first chapter link

current_url = first_chapter_url
chapter_num = 0

while current_url:
    page.goto(current_url)
    page.wait_for_selector("#chp_raw", timeout=15000)
    
    # Extract chapter title and content
    title = page.query_selector("h1.text-title, .chapter-title")
    content = page.query_selector("#chp_raw")
    
    chapters.append({
        "order": chapter_num,
        "title": title.inner_text().strip() if title else f"Chapter {chapter_num + 1}",
        "url": current_url,
        "content": content.inner_html() if content else "",
    })
    
    # Find Next Chapter link
    next_link = page.query_selector("a.chp_next") or page.query_selector("a#c2")
    if next_link:
        current_url = next_link.get_attribute("href")
        chapter_num += 1
    else:
        current_url = None  # End of novel
```

**Why this works:** Standard `page.goto()` navigations look like normal user behavior. Cloudflare allows them because they include full headers, natural referrers, and gradual sequential timing.

### Method: `toc_fic_show_all()` fast path (UNRELIABLE — may be blocked by Cloudflare)
1. Call `toc_fic_show_all()` via `page.evaluate()`
2. Poll `li.toc_w` count until it stabilizes (max 10s, check every 500ms)
3. If count matches `span.cnt_toc` → extract all chapters from DOM, done
4. If count is less → fall back to Next Chapter links
5. If `toc_fic_show_all` is undefined → go straight to Next Chapter links
6. **If `toc_fic_show_all()` throws or times out → Cloudflare blocked it, use Next Chapter links**

## Playwright

- (add entries here as discovered)

## General Scraping

- (add entries here as discovered)
