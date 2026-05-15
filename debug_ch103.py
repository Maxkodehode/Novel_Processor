"""
Debug: Follow the Previous link from chapter 104.
"""
import sys
sys.path.insert(0, "/workspace/Novel_Processor")

from core.network import NetworkClient
from bs4 import BeautifulSoup

network = NetworkClient()

# Chapter 104's Previous link
url = "https://www.scribblehub.com/read/1857436-the-rusting-robots-and-revenge/chapter/2273593/"

print(f"Fetching: {url}")
resp = network.get(url, timeout=30)
print(f"Status: {resp.status_code}")
print(f"Length: {len(resp.text)}")

soup = BeautifulSoup(resp.text, "html.parser")
title = soup.select_one(".chapter-title")
print(f"Title: {title.get_text(strip=True) if title else 'NOT FOUND'}")

# Check if this is chapter 103
content = soup.select_one("#chp_raw")
if content:
    print(f"Content: {len(content.get_text())} chars")
else:
    print("No #chp_raw!")

# Check prev link
prev = soup.select_one("a.btn-prev")
if prev:
    print(f"Prev: href='{prev.get('href')}'")
else:
    print("No prev link")
