"""
Test: Run the full chapter collection with longer delay.
"""
import sys
import time
sys.path.insert(0, "/workspace/Novel_Processor")

from adapters.scribblehub import ScribbleHubAdapter
from core.network import NetworkClient

# Temporarily increase the delay
import adapters.scribblehub as sh
original_delay = sh._PAGE_DELAY
sh._PAGE_DELAY = 5.0  # 5 seconds between requests

adapter = ScribbleHubAdapter()
network = NetworkClient()

LAST_CHAPTER_URL = "https://www.scribblehub.com/read/1857436-the-rusting-robots-and-revenge/chapter/2328763/"

print(f"Testing with {sh._PAGE_DELAY}s delay between chapters...")
print(f"Expected: 118 chapters")
print(f"Estimated time: {118 * sh._PAGE_DELAY / 60:.1f} minutes")
print()

start = time.time()
chapters = adapter._fetch_all_chapters_via_prev_links(
    network_client=network,
    first_chapter_url=LAST_CHAPTER_URL,
    expected_count=118,
)
elapsed = time.time() - start

print(f"\nResults: {len(chapters)} chapters in {elapsed:.1f}s")
if chapters:
    print(f"First: [{chapters[0]['order']}] {chapters[0]['title'][:60]}")
    print(f"Last:  [{chapters[-1]['order']}] {chapters[-1]['title'][:60]}")
    
    # Check contiguity
    orders = [ch["order"] for ch in chapters]
    if orders == list(range(len(chapters))):
        print(f"✓ Contiguous orders 0-{len(chapters)-1}")
    else:
        print(f"✗ Non-contiguous! Expected 0-{len(chapters)-1}, got {orders[:10]}...")

# Restore original delay
sh._PAGE_DELAY = original_delay
