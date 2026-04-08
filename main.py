import argparse
import json
import os
from scraper_engine import scrape
from populate_metadata import populate_from_json


def main():
    parser = argparse.ArgumentParser(description="Multi-site novel scraper")
    parser.add_argument("url", help="Fiction landing page URL")
    parser.add_argument(
        "--out", default="output.json", help="Output JSON file (default: output.json)"
    )
    parser.add_argument(
        "--db", default="novels.db", help="Target SQLite database (default: novels.db)"
    )
    parser.add_argument(
        "--use-local", metavar="FILE", help="Use a local HTML file instead of fetching"
    )
    parser.add_argument(
        "--save-html",
        metavar="FILE",
        help="Save fetched HTML to this file for debugging",
    )
    args = parser.parse_args()

    # Run the Scraper
    result = scrape(args.url, use_local=args.use_local, save_html=args.save_html)

    # Save the results to JSON
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, ensure_ascii=False)

        print(f"\n[✓] Saved to {args.out}")
        print(f"    Title    : {result.get('title')}")
        print(f"    Author   : {result.get('author')}")
        print(f"    Status   : {result.get('status')}")
        print(f"    Tags     : {result.get('tags')}")
        print(
            f"    Chapters : {result.get('chapter_count')} total, {len(result.get('chapters', []))} fetched"
        )

    # check if the file exists to prevent errors
    if os.path.exists(args.out):
        print(f"\n[*] Syncing '{result.get('title')}' to database...")
        try:
            populate_from_json(json_path=args.out, db_path=args.db)
        except Exception as e:
            print(f"Database Error: {e}")
    else:
        print("Output file not found. Skipping database population.")


if __name__ == "__main__":
    main()
