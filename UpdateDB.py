from datetime import datetime, timedelta

import argparse

from Processing_Epub import get_db_connection
from scraper_engine import scrape, _parse_and_handle_cover


def check_all_novels():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Fetch all novels from the database
    cursor.execute("SELECT id, source_url FROM novels WHERE cover_path IS NULL")
    source = cursor.fetchall()

    _parse_and_handle_cover(source, id)

    parser = argparse.ArgumentParser(description="Novel scraper pipeline")
    parser.add_argument("--url", required=True, help="Novel landing page URL")

    args = parser.parse_args()
    save_html = "page.html" if args.debug else None
    data = scrape(
        url=args.url,
        use_local=args.use_local,
        save_html=save_html,
    )
    cover_url = data.get("cover_url")
    if cover_url:
        from scraper_engine import download_cover, save_cover_to_db

        slug = data.get("slug") or f"novel_{novel_id}"
        cover_path = download_cover(cover_url, novel_id, slug)
        if cover_path:
            save_cover_to_db(novel_id, cover_path)
    else:
        logger.warning("No cover URL found for this novel.")

    for novel in all_novels:
        # Unpack the data from the row
        n_id, title, source_url, last_updated_str = novel

        # 2. Convert the stored string date to a Python date object
        if last_updated_str is None:
            last_date = datetime.now() - timedelta(days=31)
        else:
            last_date = datetime.strptime(last_updated_str, "%Y-%m-%d %H:%M:%S")

        # 3. Check the 30-day rule

        if datetime.now() > last_date + timedelta(days=30):
            print(f"Checking for updates: {title}...")

            # Insert your Novel-Grabber / Hashing logic here
            # ...

            # 4. Update the 'last_updated' timestamp so it doesn't check again tomorrow
            today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "UPDATE novels SET last_updated = ? WHERE id = ?", (today, n_id)
            )
            conn.commit()
        else:
            print(f"Skipping {title}: Last check was less than 30 days ago.")

    conn.close()


if __name__ == "__main__":
    check_all_novels()
