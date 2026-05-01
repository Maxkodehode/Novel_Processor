from core.network import NetworkClient
from curl_cffi import requests

# Set the URL that failed in your logs
URL = "https://www.royalroadcdn.com/public/covers-large/92144-the-legend-of-william-oh.jpg?time=1770708506"


def diagnose():
    client = NetworkClient(impersonate="chrome")
    print(f"--- Testing URL: {URL} ---")

    try:
        # We use curl_cffi directly here to inspect the raw response
        resp = requests.get(URL, impersonate="chrome")

        print(f"Status Code: {resp.status_code}")
        print(f"Content-Encoding Header: {resp.headers.get('Content-Encoding')}")
        print(f"Content-Type: {resp.headers.get('Content-Type')}")
        print(f"Server: {resp.headers.get('Server')}")
        print(f"Response Length: {len(resp.content)} bytes")

    except Exception as e:
        print(f"\nCaught Expected Error: {e}")
        print("\nDIAGNOSIS:")
        if "encoding type" in str(e).lower():
            print(
                "Confirmed: The server is sending a compression format (like 'br' or 'zstd')"
            )
            print("that your current curl_cffi/libcurl environment cannot decode.")


if __name__ == "__main__":
    diagnose()
