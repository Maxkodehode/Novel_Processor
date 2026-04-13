"""
populate_metadata.py — Insert or update novel metadata in the database.

Can be called as part of the pipeline (via main.py) or standalone
against a saved output.json for debugging:

    python populate_metadata.py --json output.json
"""

import argparse
import json
import logging
import sqlite3

logger = logging.getLogger(__name__)


def populate(data: dict, db_path: str = "novels.db") -> int | None:
    """
    Insert or update a novel and its chapters/tags from a parsed data dict.
    Returns the novel_id (int) on success, or None on failure.
    """
    slug = data.get("slug")
    if not slug:
        from utils import slugify

        slug = slugify(data["title"])
        logger.warning(f"No slug in data for '{data['title']}', derived: {slug}")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO novels (title, author, synopsis, source_url, slug, language)
            VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(title) DO UPDATE SET
                author       = excluded.author,
                                          synopsis     = excluded.synopsis,
                                          source_url   = excluded.source_url,
                                          slug         = excluded.slug,
                                          language     = excluded.language,
                                          last_updated = CURRENT_TIMESTAMP
            """,
            (
                data["title"],
                data.get("author"),
                data.get("synopsis"),
                data.get("url"),
                slug,
                data.get("language", "en"),
            ),
        )

        cursor.execute("SELECT id FROM novels WHERE title = ?", (data["title"],))
        row = cursor.fetchone()
        if not row:
            logger.error("Novel not found after insert.")
            return None
        novel_id = row[0]

        # Insert chapter placeholders
        chapters_inserted = 0
        for ch in data.get("chapters", []):
            cursor.execute(
                """
                INSERT INTO chapters (novel_id, chapter_title, chapter_hash, chapter_order, chapter_url)
                VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(chapter_url) DO UPDATE SET
                    chapter_title = excluded.chapter_title,
                                                    chapter_order = excluded.chapter_order
                """,
                (novel_id, ch["title"], "PENDING", ch["order"], ch["url"]),
            )
            if cursor.rowcount:
                chapters_inserted += 1

        # Insert tags and link them
        tags_linked = 0
        for tag_name in data.get("tags", []):
            cursor.execute(
                "INSERT INTO tags (name) VALUES (?) ON CONFLICT(name) DO NOTHING",
                (tag_name,),
            )
            cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
            tag_row = cursor.fetchone()
            if not tag_row:
                continue
            cursor.execute(
                """
                INSERT INTO novel_tags (novel_id, tag_id) VALUES (?, ?)
                    ON CONFLICT(novel_id, tag_id) DO NOTHING
                """,
                (novel_id, tag_row[0]),
            )
            tags_linked += 1

        conn.commit()

        logger.info(f"'{data['title']}' — novel_id={novel_id}, slug={slug}")
        logger.info(
            f"  Chapters : {chapters_inserted} inserted / {len(data.get('chapters', []))} total"
        )
        logger.info(f"  Tags     : {tags_linked} linked")

        return novel_id

    except Exception as e:
        logger.exception(f"populate() failed: {e}")
        conn.rollback()
        return None

    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )

    parser = argparse.ArgumentParser(description="Populate DB from a saved output.json")
    parser.add_argument("--json", default="output.json", help="Path to JSON file")
    parser.add_argument("--db", default="novels.db", help="Path to SQLite DB")
    args = parser.parse_args()

    with open(args.json, "r", encoding="utf-8") as f:
        data = json.load(f)

    novel_id = populate(data, db_path=args.db)
    if novel_id:
        print(f"Done. novel_id={novel_id}")
