"""
Full test: Collect all 118 chapters.
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
sh._PAGE_DELAY = 5.0

print("Collecting all 118 chapters with 5s delay + retry logic...")
print(f"Estimated time: ~{118 * 5 / 60:.0f} minutes minimum")
start = time.time()
chapters = adapter._fetch_all_chapters_via_prev_links(
    network_client=network,
    first_chapter_url=LAST_CHAPTER_URL,
    expected_count=118,
)
elapsed = time.time() - start

print(f"\n{'='*60}")
print(f"RESULTS")
print(f"{'='*60}")
print(f"Chapters collected: {len(chapters)}")
print(f"Time: {elapsed:.1f}s ({elapsed/60:.1f} min)")

if chapters:
    print(f"First: [{chapters[0]['order']}] {chapters[0]['title'][:60]}")
    print(f"Last:  [{chapters[-1]['order']}] {chapters[-1]['title'][:60]}")
    
    orders = [ch["order"] for ch in chapters]
    if orders == list(range(len(chapters))):
        print(f"✓ Contiguous orders 0-{len(chapters)-1}")
    else:
        print(f"✗ Non-contiguous!")
    
    urls = [ch["url"] for ch in chapters]
    if len(urls) == len(set(urls)):
        print(f"✓ No duplicate URLs")
    
    no_title = [ch for ch in chapters if not ch.get("title")]
    if not no_title:
        print(f"✓ All chapters have titles")

if len(chapters) == 118:
    print(f"\n✓✓✓ SUCCESS: All 118 chapters collected! ✓✓✓")
else:
    print(f"\n✗ Expected 118, got {len(chapters)}")
