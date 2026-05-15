"""
Combined diagnostic + research script for ScribbleHub chapter scraping.
Tests Cloudflare behavior and finds Next Chapter link selectors.
"""
import sys
import time
import json
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

TEST_URL = "https://www.scribblehub.com/series/1857436/"
# Known chapter page from our earlier diagnostics
CHAPTER_URL = "https://www.scribblehub.com/read/1857436-the-rusting-robots-and-revenge/chapter/2328763/"

findings = {}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080},
        locale="en-US",
        timezone_id="America/New_York",
    )
    
    # ===== DIAGNOSTIC: Novel page =====
    print("=" * 60)
    print("[DIAGNOSTIC] Loading novel page...")
    print("=" * 60)
    
    page = context.new_page()
    
    # Track network requests
    ajax_requests = []
    def on_req(req):
        if "admin-ajax" in req.url:
            ajax_requests.append(f"{req.method} {req.url}")
    def on_resp(resp):
        if "admin-ajax" in resp.url:
            ajax_requests.append(f"RESP {resp.status} {resp.url}")
    
    page.on("request", on_req)
    page.on("response", on_resp)
    
    page.goto(TEST_URL, wait_until="load", timeout=60000)
    time.sleep(3)
    
    # Count chapters in static HTML
    toc_count = page.evaluate("document.querySelectorAll('li.toc_w').length")
    badge = page.evaluate("document.querySelector('span.cnt_toc')?.textContent?.trim() || ''")
    print(f"  li.toc_w count: {toc_count}")
    print(f"  Chapter badge: {badge}")
    
    # Check JS globals
    js_state = page.evaluate("""JSON.stringify({
        toc_fic_show_all: typeof toc_fic_show_all,
        ajaxurl: typeof ajaxurl !== 'undefined' ? ajaxurl : 'NOT DEFINED',
        jQuery: typeof jQuery !== 'undefined' ? jQuery.fn.jquery : 'NOT LOADED',
        simplePagination: typeof jQuery !== 'undefined' && typeof jQuery.fn.simplePagination !== 'undefined',
    })""")
    print(f"  JS state: {js_state}")
    
    # Try calling toc_fic_show_all
    print("\n  Calling toc_fic_show_all()...")
    try:
        page.evaluate("toc_fic_show_all()")
        time.sleep(5)
        after_count = page.evaluate("document.querySelectorAll('li.toc_w').length")
        print(f"  Chapters after toc_fic_show_all(): {after_count}")
    except Exception as e:
        print(f"  toc_fic_show_all() error: {e}")
        after_count = toc_count
    
    # Check network log
    print(f"  AJAX network log: {ajax_requests}")
    
    findings["diagnostic"] = {
        "static_chapters": toc_count,
        "badge_count": badge,
        "js_state": json.loads(js_state),
        "after_toc_fic_show_all": after_count,
        "ajax_requests": ajax_requests,
    }
    
    # ===== RESEARCH: Chapter page =====
    print(f"\n{'='*60}")
    print("[RESEARCH] Loading chapter page...")
    print("=" * 60)
    
    page2 = context.new_page()
    page2.goto(CHAPTER_URL, wait_until="load", timeout=60000)
    time.sleep(3)
    
    # Find all possible Next Chapter selectors
    next_selectors = [
        "a.chp_next",
        "a#c2",
        "a#next_chapter",
        "a.next-chapter",
        "a[rel='next']",
        ".chapter-nav a:last-child",
        ".chapter-navigation a:last-child",
        "a:has-text('Next Chapter')",
        "a:has-text('Next')",
        ".chp_next",
        "#chp_next",
    ]
    
    found_selectors = {}
    for sel in next_selectors:
        try:
            el = page2.query_selector(sel)
            if el:
                text = el.inner_text()[:50]
                href = el.get_attribute("href") or ""
                found_selectors[sel] = {"text": text, "href": href}
                print(f"  FOUND: {sel} -> text='{text}' href='{href[:80]}'")
        except Exception as e:
            pass
    
    if not found_selectors:
        print("  No standard selectors found. Looking for any navigation links...")
        # Get all links in the chapter area
        all_links = page2.evaluate("""[...document.querySelectorAll('a[href]')]
            .filter(a => {
                const href = a.href || '';
                const text = (a.textContent || '').trim().toLowerCase();
                return href.includes('/chapter/') || 
                       text.includes('next') || 
                       text.includes('prev') ||
                       text.includes('chapter');
            })
            .map(a => ({href: a.href, text: (a.textContent || '').trim().slice(0,50), id: a.id, cls: a.className}))
            .slice(0, 20)
        """)
        for link in all_links:
            print(f"  Link: text='{link['text']}' href='{link['href'][:80]}' id='{link['id']}' cls='{link['cls']}'")
        found_selectors["all_nav_links"] = all_links
    
    # Also look for Previous Chapter
    prev_selectors = [
        "a.chp_prev",
        "a#c1",
        "a[rel='prev']",
        "a:has-text('Previous Chapter')",
        "a:has-text('Previous')",
    ]
    
    found_prev = {}
    for sel in prev_selectors:
        try:
            el = page2.query_selector(sel)
            if el:
                text = el.inner_text()[:50]
                href = el.get_attribute("href") or ""
                found_prev[sel] = {"text": text, "href": href}
                print(f"  PREV FOUND: {sel} -> text='{text}' href='{href[:80]}'")
        except:
            pass
    
    # Check chapter title
    title_selectors = ["h1.text-title", "h1.chapter-title", ".chapter-title", "h1"]
    for sel in title_selectors:
        el = page2.query_selector(sel)
        if el:
            print(f"  Chapter title ({sel}): {el.inner_text()[:80]}")
            break
    
    # Check chapter content
    content = page2.query_selector("#chp_raw")
    if content:
        text_len = len(content.inner_text())
        print(f"  Chapter content (#chp_raw): {text_len} chars")
    else:
        print("  No #chp_raw found!")
    
    findings["research"] = {
        "next_chapter_selectors": found_selectors,
        "prev_chapter_selectors": found_prev,
        "chapter_url_pattern": CHAPTER_URL,
    }
    
    # ===== RESEARCH: Find Chapter 1 URL =====
    print(f"\n{'='*60}")
    print("[RESEARCH] Finding Chapter 1 URL from novel page...")
    print("=" * 60)
    
    # Go back to novel page and find the first chapter link
    page.goto(TEST_URL, wait_until="load", timeout=60000)
    time.sleep(2)
    
    # Get all chapter links sorted by order attribute
    chapter_links = page.evaluate("""[...document.querySelectorAll('li.toc_w a.toc_a')]
        .map(a => {
            const li = a.closest('li.toc_w');
            return {
                href: a.href,
                title: a.textContent.trim(),
                order: li ? li.getAttribute('order') : null
            };
        })
        .sort((a, b) => parseInt(a.order) - parseInt(b.order))
    """)
    
    if chapter_links:
        print(f"  First chapter (lowest order): {chapter_links[0]}")
        print(f"  Last chapter (highest order): {chapter_links[-1]}")
        findings["first_chapter_url"] = chapter_links[0]["href"]
        findings["last_chapter_url"] = chapter_links[-1]["href"]
    
    context.close()
    browser.close()

# Write findings
print(f"\n{'='*60}")
print("WRITING FINDINGS")
print("=" * 60)

import os
os.makedirs("/workspace/Novel_Processor/.agent-workspace/findings", exist_ok=True)

with open("/workspace/Novel_Processor/.agent-workspace/findings/diagnosis-1.md", "w") as f:
    f.write("# Diagnosis 1 — ScribbleHub Scraper Failure\n\n")
    f.write(f"**Date**: {time.strftime('%Y-%m-%d %H:%M')}\n\n")
    f.write(f"## Static HTML Analysis\n")
    f.write(f"- `li.toc_w` count: {findings['diagnostic']['static_chapters']}\n")
    f.write(f"- Chapter badge (`span.cnt_toc`): {findings['diagnostic']['badge_count']}\n\n")
    f.write(f"## JS State\n")
    for k, v in findings['diagnostic']['js_state'].items():
        f.write(f"- `{k}`: {v}\n")
    f.write(f"\n## AJAX Test\n")
    f.write(f"- Chapters after `toc_fic_show_all()`: {findings['diagnostic']['after_toc_fic_show_all']}\n")
    f.write(f"- Network log: {findings['diagnostic']['ajax_requests']}\n\n")
    if findings['diagnostic']['after_toc_fic_show_all'] <= findings['diagnostic']['static_chapters']:
        f.write(f"**CONCLUSION**: `toc_fic_show_all()` did NOT load more chapters. AJAX is blocked.\n")
    else:
        f.write(f"**CONCLUSION**: `toc_fic_show_all()` loaded additional chapters.\n")

with open("/workspace/Novel_Processor/.agent-workspace/findings/research-1.md", "w") as f:
    f.write("# Research 1 — Chapter Page Navigation\n\n")
    f.write(f"**Date**: {time.strftime('%Y-%m-%d %H:%M')}\n\n")
    f.write(f"## Next Chapter Selectors Found\n")
    for sel, info in findings["research"]["next_chapter_selectors"].items():
        if isinstance(info, dict) and "text" in info:
            f.write(f"- `{sel}`: text='{info['text']}', href='{info['href']}'\n")
        else:
            f.write(f"- `{sel}`: {json.dumps(info)[:200]}\n")
    f.write(f"\n## Previous Chapter Selectors Found\n")
    for sel, info in findings["research"]["prev_chapter_selectors"].items():
        f.write(f"- `{sel}`: text='{info['text']}', href='{info['href']}'\n")
    if findings.get("first_chapter_url"):
        f.write(f"\n## Chapter 1 URL\n{findings['first_chapter_url']}\n")
    if findings.get("last_chapter_url"):
        f.write(f"\n## Last Chapter URL\n{findings['last_chapter_url']}\n")

print("Findings written to:")
print("  /workspace/Novel_Processor/.agent-workspace/findings/diagnosis-1.md")
print("  /workspace/Novel_Processor/.agent-workspace/findings/research-1.md")
print("\nDone!")
