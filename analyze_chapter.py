"""
Analyze the chapter page HTML to find Next/Previous chapter links.
"""
from curl_cffi import requests as curl_requests
from bs4 import BeautifulSoup
import re

CHAPTER_URL = "https://www.scribblehub.com/read/1857436-the-rusting-robots-and-revenge/chapter/2328763/"

resp = curl_requests.get(CHAPTER_URL, impersonate="chrome", timeout=30)
soup = BeautifulSoup(resp.text, "html.parser")

print("=== Chapter Title ===")
for sel in ["h1.text-title", "h1.chapter-title", ".chapter-title", "h1", ".fic_title", "#chp_raw h1"]:
    el = soup.select_one(sel)
    if el:
        print(f"  ({sel}): {el.get_text(strip=True)[:100]}")
        break

print("\n=== All links with 'chapter' in href ===")
for a in soup.find_all("a", href=True):
    href = a["href"]
    if "chapter" in href.lower():
        text = a.get_text(strip=True)[:50]
        print(f"  text='{text}' href='{href}' id='{a.get('id','')}' cls='{a.get('class','')}')")

print("\n=== Links with text 'Next' or 'Previous' ===")
for a in soup.find_all("a", href=True):
    text = a.get_text(strip=True).lower()
    if text in ["next", "previous", "prev", "next chapter", "previous chapter"]:
        print(f"  text='{a.get_text(strip=True)}' href='{a['href']}' id='{a.get('id','')}' cls='{a.get('class','')}')")

print("\n=== Script tags with chapter navigation data ===")
for script in soup.find_all("script"):
    text = script.string or ""
    if "chapter" in text.lower() and ("next" in text.lower() or "prev" in text.lower() or "nav" in text.lower()):
        # Find the relevant section
        for keyword in ["next", "prev", "chapter_nav", "chp_nav"]:
            idx = text.lower().find(keyword)
            if idx >= 0:
                snippet = text[max(0,idx-50):idx+200]
                print(f"  Found '{keyword}': ...{snippet}...")
                break

print("\n=== Data attributes on navigation elements ===")
for el in soup.select("[data-chapter], [data-next], [data-prev], [data-url], [data-id]"):
    print(f"  <{el.name}> attrs={dict(el.attrs)} text='{el.get_text(strip=True)[:50]}'")

print("\n=== Look for onclick handlers ===")
for el in soup.find_all(onclick=True):
    print(f"  <{el.name}> onclick='{el['onclick'][:100]}' text='{el.get_text(strip=True)[:50]}'")

print("\n=== Chapter navigation area ===")
for sel in [".chapter-nav", ".chapter-navigation", ".chp_nav", "#chp_nav", 
             ".pagination", ".nav-links", ".post-navigation",
             "[class*='chapter'][class*='nav']", "[class*='chp']",
             ".fic_chapter_nav", ".chapter_pager", ".chapter_footer"]:
    els = soup.select(sel)
    if els:
        for el in els:
            print(f"  ({sel}): {el.get_text(strip=True)[:200]}")
            for a in el.find_all("a", href=True):
                print(f"    -> {a.get_text(strip=True)[:50]}: {a['href'][:80]}")

print("\n=== Full HTML around 'Next' text ===")
# Find text containing "Next" in the HTML
html_str = str(soup)
for match in re.finditer(r'Next|Previous|Prev', html_str):
    start = max(0, match.start() - 100)
    end = min(len(html_str), match.end() + 100)
    context = html_str[start:end]
    # Clean up for display
    context = context.replace('\n', ' ').replace('\r', ' ')
    print(f"  ...{context}...")
