"""
Quick test: Collect 5 chapters with 3s delay.
"""
import sys
import time
sys.path.insert(0, "/workspace/Novel_Processor")

from adapters.scribblehub import ScribbleHubAdapter
from core.network import NetworkClient

adapter = ScribbleHubAdapter()
network = NetworkClient()

LAST_CHAPTER_URL = "https://www.scribblehub.com/read/1857436-the-rusting-robots-and-revenge/chapter/2328763/"

import adapters.scribblehub as sh
sh._PAGE_DELAY = 3.0

print("Collecting 5 chapters with 3s delay...")
start = time.time()
chapters = adapter._fetch_all_chapters_via_prev_links(
    network_client=network,
    first_chapter_url=LAST_CHAPTER_URL,
    expected_count=5,
)
elapsed = time.time() - start

print(f"\nCollected {len(chapters)} chapters in {elapsed:.1f}s")
for ch in chapters:
    print(f"  [{ch['order']}] {ch['title'][:60]}")
