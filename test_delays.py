"""
Test: Check if adding more delay avoids Cloudflare 403s.
"""
import time
from core.network import NetworkClient

network = NetworkClient()

# Test with increasing delays
delays = [2, 5, 10]
test_url = "https://www.scribblehub.com/read/1857436-the-rusting-robots-and-revenge/chapter/2328763/"

for delay in delays:
    print(f"\nTesting with {delay}s delay...")
    for i in range(5):
        try:
            resp = network.get(test_url, timeout=30)
            print(f"  Request {i+1}: HTTP {resp.status_code} ({len(resp.text)} chars)")
            if resp.status_code == 403:
                print(f"  BLOCKED after {i+1} requests")
                break
        except Exception as e:
            print(f"  Request {i+1}: ERROR {e}")
            break
        time.sleep(delay)
    else:
        print(f"  All 5 requests succeeded with {delay}s delay!")
