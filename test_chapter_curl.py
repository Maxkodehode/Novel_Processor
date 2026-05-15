"""
Test if chapter pages work with curl_cffi vs Playwright.
"""
import time
from curl_cffi import requests as curl_requests

CHAPTER_URL = "https://www.scribblehub.com/read/1857436-the-rusting-robots-and-revenge/chapter/2328763/"

print("Testing chapter page with curl_cffi...")
resp = curl_requests.get(CHAPTER_URL, impersonate="chrome", timeout=30)
print(f"Status: {resp.status_code}")
print(f"Length: {len(resp.text)} chars")
print(f"Title preview: {resp.text[:200]}")

if "Just a moment" in resp.text or "cf-challenge" in resp.text or resp.status_code == 403:
    print("\nBLOCKED by Cloudflare (curl_cffi)")
else:
    print("\nSUCCESS - page loaded!")
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, "html.parser")
    
    # Check title
    for sel in ["h1.text-title", "h1.chapter-title", "h1"]:
        el = soup.select_one(sel)
        if el:
            print(f"Chapter title: {el.get_text(strip=True)[:80]}")
            break
    
    # Check content
    content = soup.select_one("#chp_raw")
    if content:
        print(f"Content (#chp_raw): {len(content.get_text())} chars")
    else:
        print("No #chp_raw found")
    
    # Check navigation
    links = soup.find_all("a", href=True)
    for a in links:
        text = a.get_text(strip=True).lower()
        href = a["href"]
        if "next" in text or "prev" in text or "chapter" in href:
            print(f"Nav: text='{a.get_text(strip=True)[:50]}' href='{href[:80]}'")
