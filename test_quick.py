"""
Quick test: Collect 20 chapters with 5s delay to verify the approach.
"""
import sys
import time
sys.path.insert(0, "/workspace/Novel_Processor")

from adapters.scribblehub import ScribbleHubAdapter
from core.network import NetworkClient

adapter = ScribbleHubAdapter()
network = NetworkClient()

LAST_CHAPTER_URL = "https://www.scribblehub.com/read/1857436-the-rusting-robots-and-revenge/chapter/2328763/"

# Monkey-patch delay
import adapters.scribblehub as sh
sh._PAGE_DELAY = 5.0

print("Collecting 20 chapters with 5s delay...")
start = time.time()
chapters = adapter._fetch_all_chapters_via_prev_links(
    network_client=network,
    first_chapter_url=LAST_CHAPTER_URL,
    expected_count=20,
)
elapsed = time.time() - start

print(f"\nCollected {len(chapters)} chapters in {elapsed:.1f}s")
if chapters:
    print(f"First: [{chapters[0]['order']}] {chapters[0]['title'][:60]}")
    print(f"Last:  [{chapters[-1]['order']}] {chapters[-1]['title'][:60]}")
    orders = [ch["order"] for ch in chapters]
    if orders == list(range(len(chapters))):
        print("✓ Contiguous")
    else:
        print(f"✗ Non-contiguous: {orders}")
