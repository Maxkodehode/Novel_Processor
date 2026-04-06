import sqlite3
import httpx
import time


def worker():
    conn = sqlite3.connect("novels.db")
    cursor = conn.cursor()

    # Find chapters with no content
    # Note: Ensure you add a 'source_url' column to your chapters table
    # or pass it through another way.
    cursor.execute("SELECT id, chapter_title FROM chapters WHERE plain_content IS NULL")
    tasks = cursor.fetchall()

    with httpx.Client(timeout=15.0) as client:
        for ch_id, title in tasks:
            # Logic to get the URL based on the title/novel
            # (Best to store URL in the chapters table during Phase 1)
            print(f"Fetching content for: {title}")

            # ... scraping logic here ...

            # After scraping:
            # text_content = ...
            # ch_hash = hashlib.md5(text_content.encode()).hexdigest()

            # cursor.execute("UPDATE chapters SET plain_content = ?, chapter_hash = ? WHERE id = ?",
            #                (text_content, ch_hash, ch_id))
            # conn.commit()
            time.sleep(2)  # Be kind to the server

    conn.close()
