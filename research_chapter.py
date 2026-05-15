"""
Research script: Investigate ScribbleHub chapter page structure.
First get the actual chapter URLs from the novel page, then navigate to one.
"""
import sys
import time
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

TEST_URL = "https://www.scribblehub.com/series/1857436/"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080},
    )
    
    page = context.new_page()
    page.goto(TEST_URL, wait_until="load", timeout=60000)
    time.sleep(3)
    
    # Get all chapter links from the page
    links = page.evaluate("""[...document.querySelectorAll('li.toc_w a.toc_a, li.toc_w a')]
        .map(a => ({href: a.href, text: a.textContent.trim().slice(0,80)}))
    """)
    print(f"Found {len(links)} chapter links:")
    for l in links[:5]:
        print(f"  {l}")
    if len(links) > 5:
        print(f"  ... and {len(links)-5} more")
    
    if links:
        # Navigate to the first chapter
        first_chapter_url = links[0]["href"]
        print(f"\nNavigating to first chapter: {first_chapter_url}")
        
        page2 = context.new_page()
        page2.goto(first_chapter_url, wait_until="load", timeout=60000)
        time.sleep(3)
        
        print(f"  Page title: {page2.title()}")
        print(f"  Page URL: {page2.url}")
        
        # Get the full HTML to analyze
        html = page2.content()
        soup = BeautifulSoup(html, "html.parser")
        
        # Check for chapter title
        for sel in ["h1.text-title", "h1.chapter-title", ".chapter-title", "h1", ".fic_title"]:
            el = soup.select_one(sel)
            if el:
                print(f"  Chapter title ({sel}): {el.get_text(strip=True)[:80]}")
                break
        
        # Check for chapter content
        content = soup.select_one("#chp_raw")
        if content:
            print(f"  Chapter content (#chp_raw): {len(content.get_text())} chars")
        else:
            print(f"  No #chp_raw found!")
            # Look for any content area
            for sel in [".chapter-content", "#content", ".entry-content", "article", ".fic_content"]:
                el = soup.select_one(sel)
                if el:
                    print(f"  Found content area ({sel}): {len(el.get_text())} chars")
                    break
        
        # Find ALL links on the page that might be navigation
        all_links = soup.find_all("a", href=True)
        nav_links = []
        for a in all_links:
            href = a["href"]
            text = a.get_text(strip=True)
            if any(kw in href.lower() for kw in ["chapter", "next", "prev", "nav"]):
                nav_links.append({"href": href, "text": text[:50], "id": a.get("id", ""), "cls": " ".join(a.get("class", []))})
            elif any(kw in text.lower() for kw in ["next", "previous", "prev"]):
                nav_links.append({"href": href, "text": text[:50], "id": a.get("id", ""), "cls": " ".join(a.get("class", []))})
        
        print(f"\n  Navigation links found: {len(nav_links)}")
        for l in nav_links:
            print(f"    text='{l['text']}' href='{l['href'][:80]}' id='{l['id']}' cls='{l['cls']}'")
        
        # Also look for pagination/navigation divs
        for sel in [".chapter-nav", ".chapter-navigation", ".chp_nav", "#chp_nav", 
                     ".pagination", ".nav-links", ".post-navigation", ".fic_nav",
                     "[class*='nav']", "[class*='pagination']"]:
            els = soup.select(sel)
            if els:
                for el in els:
                    print(f"\n  Nav container ({sel}): {el.get_text(strip=True)[:200]}")
        
        # Save the HTML for manual inspection
        with open("/workspace/Novel_Processor/.agent-workspace/chapter_page_sample.html", "w") as f:
            f.write(html)
        print(f"\n  Full HTML saved to .agent-workspace/chapter_page_sample.html")
    
    context.close()
    browser.close()
