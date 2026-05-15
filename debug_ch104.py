"""
Debug: Check the Previous link on chapter 104.
"""
import sys
sys.path.insert(0, "/workspace/Novel_Processor")

from core.network import NetworkClient
from bs4 import BeautifulSoup

network = NetworkClient()

# Chapter 104 URL (the lowest we got)
url = "https://www.scribblehub.com/read/1857436-the-rusting-robots-and-revenge/chapter/2273868/"

print(f"Fetching chapter 104: {url}")
resp = network.get(url, timeout=30)
print(f"Status: {resp.status_code}")

soup = BeautifulSoup(resp.text, "html.parser")

# Check title
title = soup.select_one(".chapter-title")
print(f"Title: {title.get_text(strip=True) if title else 'NOT FOUND'}")

# Check all navigation links
print("\nAll navigation links:")
for a in soup.find_all("a", href=True):
    text = a.get_text(strip=True)
    href = a["href"]
    cls = " ".join(a.get("class", []))
    if "btn" in cls or "prev" in cls or "next" in cls or "nav" in cls.lower():
        print(f"  text='{text}' href='{href[:80]}' cls='{cls}'")

# Specifically check a.btn-prev
prev = soup.select_one("a.btn-prev")
if prev:
    print(f"\na.btn-prev: href='{prev.get('href')}' text='{prev.get_text(strip=True)}'")
else:
    print("\nNo a.btn-prev found!")

# Check if there's a disabled class
disabled = soup.select(".disabled")
print(f"\nDisabled elements: {len(disabled)}")
for el in disabled:
    print(f"  <{el.name}> cls='{' '.join(el.get('class',[]))}' text='{el.get_text(strip=True)[:50]}'")
