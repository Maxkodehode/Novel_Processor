"""
Debug: Run the collection with verbose logging.
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
sh.DEBUG = True  # Enable debug logging

# Enable logging
import logging
logging.basicConfig(level=logging.DEBUG, format="%(message)s")

print("Collecting chapters with debug logging...")
chapters = adapter._fetch_all_chapters_via_prev_links(
    network_client=network,
    first_chapter_url=LAST_CHAPTER_URL,
    expected_count=20,
)

print(f"\nTotal collected: {len(chapters)}")
