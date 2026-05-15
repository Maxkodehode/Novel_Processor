"""
Test: Check if requesting different chapter URLs triggers Cloudflare.
"""
import time
from core.network import NetworkClient

network = NetworkClient()

# Different chapter URLs (from our earlier diagnostics)
urls = [
    "https://www.scribblehub.com/read/1857436-the-rusting-robots-and-revenge/chapter/2328763/",  # ch 118
    "https://www.scribblehub.com/read/1857436-the-rusting-robots-and-revenge/chapter/2319836/",  # ch 117
    "https://www.scribblehub.com/read/1857436-the-rusting-robots-and-revenge/chapter/2318023/",  # ch 116
    "https://www.scribblehub.com/read/1857436-the-rusting-robots-and-revenge/chapter/2316265/",  # ch 115
    "https://www.scribblehub.com/read/1857436-the-rusting-robots-and-revenge/chapter/2308112/",  # ch 114
    "https://www.scribblehub.com/read/1857436-the-rusting-robots-and-revenge/chapter/2306852/",  # ch 113
    "https://www.scribblehub.com/read/1857436-the-rusting-robots-and-revenge/chapter/2305405/",  # ch 112
    "https://www.scribblehub.com/read/1857436-the-rusting-robots-and-revenge/chapter/2295984/",  # ch 111
    "https://www.scribblehub.com/read/1857436-the-rusting-robots-and-revenge/chapter/2295905/",  # ch 110
    "https://www.scribblehub.com/read/1857436-the-rusting-robots-and-revenge/chapter/2286535/",  # ch 109
]

print("Testing sequential different chapter URLs with 2s delay...")
for i, url in enumerate(urls):
    try:
        resp = network.get(url, timeout=30)
        status = resp.status_code
        length = len(resp.text)
        blocked = "BLOCKED" if status == 403 else "OK"
        print(f"  [{i+1}] {blocked} HTTP {status} ({length} chars) - ...{url[-40:]}")
        if status == 403:
            print(f"  Stopped after {i+1} requests")
            break
    except Exception as e:
        print(f"  [{i+1}] ERROR: {e}")
        break
    time.sleep(2)
else:
    print(f"\nAll {len(urls)} requests succeeded!")

print("\nNow testing with 5s delay...")
time.sleep(5)  # Cool down between tests

for i, url in enumerate(urls):
    try:
        resp = network.get(url, timeout=30)
        status = resp.status_code
        length = len(resp.text)
        blocked = "BLOCKED" if status == 403 else "OK"
        print(f"  [{i+1}] {blocked} HTTP {status} ({length} chars) - ...{url[-40:]}")
        if status == 403:
            print(f"  Stopped after {i+1} requests")
            break
    except Exception as e:
        print(f"  [{i+1}] ERROR: {e}")
        break
    time.sleep(5)
else:
    print(f"\nAll {len(urls)} requests succeeded with 5s delay!")
